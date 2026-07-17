from __future__ import annotations

import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .event_profile import load_document


@dataclass(frozen=True)
class PingSample:
    time_s: float
    rtt_ms: float | None
    timeout: bool


def _float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def load_ping(path: Path) -> list[PingSample]:
    samples: list[PingSample] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if "time_s" not in fields:
            raise ValueError(f"{path}: time_s column is required")
        for row in reader:
            timeout_raw = str(row.get("timeout", "0")).strip().lower()
            timeout = timeout_raw in {"1", "true", "yes", "timeout"}
            rtt_raw = str(row.get("rtt_ms", "")).strip()
            rtt = None if timeout or not rtt_raw else _float(rtt_raw)
            samples.append(PingSample(_float(row.get("time_s")), rtt, timeout))
    samples.sort(key=lambda x: x.time_s)
    return samples


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def baseline_threshold(samples: list[PingSample], start_sec: float, margin_sec: float) -> float:
    before = [
        s.rtt_ms
        for s in samples
        if s.rtt_ms is not None and max(0.0, start_sec - margin_sec) <= s.time_s < start_sec
    ]
    if len(before) < 3:
        before = [s.rtt_ms for s in samples if s.rtt_ms is not None and s.time_s < start_sec]
    values = [float(v) for v in before if v is not None]
    if not values:
        return 0.0
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations) if deviations else 0.0
    return median + max(10.0, 3.0 * 1.4826 * mad)


def summarize_window(
    samples: list[PingSample],
    *,
    event_start: float,
    event_end: float,
    search_margin_sec: float,
    threshold: float | None,
) -> dict[str, Any]:
    window_start = max(0.0, event_start - search_margin_sec)
    window_end = event_end + search_margin_sec
    points = [s for s in samples if window_start <= s.time_s <= window_end]
    if not points:
        return {"sample_count": 0, "detected": False}

    effective_threshold = threshold
    if effective_threshold is None:
        effective_threshold = baseline_threshold(samples, event_start, max(2.0, search_margin_sec * 2))

    abnormal = [s for s in points if s.timeout or (s.rtt_ms is not None and s.rtt_ms >= effective_threshold)]
    rtts = [float(s.rtt_ms) for s in points if s.rtt_ms is not None]
    event_rtts = [
        float(s.rtt_ms)
        for s in points
        if event_start <= s.time_s <= event_end and s.rtt_ms is not None
    ]
    event_points = [s for s in points if event_start <= s.time_s <= event_end]

    detected_start = abnormal[0].time_s if abnormal else None
    detected_end = abnormal[-1].time_s if abnormal else None
    detected_duration = (
        max(0.0, detected_end - detected_start) if detected_start is not None and detected_end is not None else None
    )
    peak_sample = max((s for s in points if s.rtt_ms is not None), key=lambda s: s.rtt_ms or 0.0, default=None)

    return {
        "sample_count": len(points),
        "event_sample_count": len(event_points),
        "detected": bool(abnormal),
        "threshold_ms": round(float(effective_threshold), 6),
        "detected_start_sec": None if detected_start is None else round(detected_start, 6),
        "detected_end_sec": None if detected_end is None else round(detected_end, 6),
        "detected_duration_sec": None if detected_duration is None else round(detected_duration, 6),
        "peak_rtt_ms": 0.0 if peak_sample is None else round(float(peak_sample.rtt_ms or 0.0), 6),
        "peak_time_sec": None if peak_sample is None else round(peak_sample.time_s, 6),
        "mean_rtt_ms": round(statistics.fmean(rtts), 6) if rtts else 0.0,
        "event_mean_rtt_ms": round(statistics.fmean(event_rtts), 6) if event_rtts else 0.0,
        "event_p95_rtt_ms": round(percentile(event_rtts, 0.95), 6) if event_rtts else 0.0,
        "timeout_ratio": round(sum(1 for s in event_points if s.timeout) / len(event_points), 6)
        if event_points
        else 0.0,
    }


def aligned_event_errors(
    measured: list[PingSample], replayed: list[PingSample], start: float, end: float, tolerance: float
) -> dict[str, float | int]:
    measured_values = [s for s in measured if start <= s.time_s <= end and s.rtt_ms is not None]
    replay_values = [s for s in replayed if start <= s.time_s <= end and s.rtt_ms is not None]
    diffs: list[float] = []
    for point in measured_values:
        candidates = [r for r in replay_values if abs(r.time_s - point.time_s) <= tolerance]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda r: abs(r.time_s - point.time_s))
        diffs.append(float(point.rtt_ms or 0.0) - float(nearest.rtt_ms or 0.0))
    if not diffs:
        return {"aligned_points": 0, "rtt_mae_ms": 0.0, "rtt_rmse_ms": 0.0}
    return {
        "aligned_points": len(diffs),
        "rtt_mae_ms": round(statistics.fmean(abs(v) for v in diffs), 6),
        "rtt_rmse_ms": round(math.sqrt(statistics.fmean(v * v for v in diffs)), 6),
    }


def evaluate_events(
    measured_path: Path,
    replayed_path: Path,
    events_path: Path,
    *,
    search_margin_sec: float = 0.5,
    align_tolerance_sec: float = 0.11,
    threshold_ms: float | None = None,
) -> dict[str, Any]:
    measured = load_ping(measured_path)
    replayed = load_ping(replayed_path)
    document = load_document(events_path)

    results: list[dict[str, Any]] = []
    for event in document["events"]:
        start = float(event["start_sec"])
        end = float(event["end_sec"])
        measured_summary = summarize_window(
            measured,
            event_start=start,
            event_end=end,
            search_margin_sec=search_margin_sec,
            threshold=threshold_ms,
        )
        replay_summary = summarize_window(
            replayed,
            event_start=start,
            event_end=end,
            search_margin_sec=search_margin_sec,
            threshold=threshold_ms,
        )
        errors = aligned_event_errors(
            measured,
            replayed,
            max(0.0, start - search_margin_sec),
            end + search_margin_sec,
            align_tolerance_sec,
        )

        def difference(key: str) -> float | None:
            left = measured_summary.get(key)
            right = replay_summary.get(key)
            if left is None or right is None:
                return None
            return round(float(right) - float(left), 6)

        results.append(
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "nominal_start_sec": start,
                "nominal_end_sec": end,
                "measured": measured_summary,
                "replayed": replay_summary,
                "errors": {
                    **errors,
                    "start_time_error_sec": difference("detected_start_sec"),
                    "end_time_error_sec": difference("detected_end_sec"),
                    "duration_error_sec": difference("detected_duration_sec"),
                    "peak_rtt_error_ms": difference("peak_rtt_ms"),
                    "peak_time_error_sec": difference("peak_time_sec"),
                    "event_mean_rtt_error_ms": difference("event_mean_rtt_ms"),
                    "timeout_ratio_error": difference("timeout_ratio"),
                },
            }
        )

    numeric_keys = [
        "rtt_mae_ms",
        "rtt_rmse_ms",
        "start_time_error_sec",
        "duration_error_sec",
        "peak_rtt_error_ms",
        "peak_time_error_sec",
    ]
    aggregate: dict[str, Any] = {"event_count": len(results)}
    for key in numeric_keys:
        values = [
            abs(float(row["errors"][key]))
            for row in results
            if row["errors"].get(key) is not None
        ]
        aggregate[f"mean_abs_{key}"] = round(statistics.fmean(values), 6) if values else None

    return {
        "schema_version": "1.0",
        "evaluation_type": "event_replay",
        "inputs": {
            "measured_ping": str(measured_path),
            "replayed_ping": str(replayed_path),
            "events": str(events_path),
        },
        "settings": {
            "search_margin_sec": search_margin_sec,
            "align_tolerance_sec": align_tolerance_sec,
            "threshold_ms": threshold_ms,
        },
        "aggregate": aggregate,
        "events": results,
    }
