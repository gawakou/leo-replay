from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from leo_replay import __version__

from .models import OrbitDataError, iso_utc, parse_utc, utc_now_iso


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def load_visibility_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])
    required = {"timestamp_utc", "satellite_name", "norad_cat_id", "elevation_deg", "visible"}
    missing = required.difference(fieldnames)
    if missing:
        raise OrbitDataError(f"visibility CSV is missing columns: {', '.join(sorted(missing))}")
    normalized = []
    for row in rows:
        if not _truthy(row.get("visible", True)):
            continue
        try:
            normalized.append(
                {
                    **row,
                    "timestamp": parse_utc(row["timestamp_utc"]),
                    "elevation": float(row["elevation_deg"]),
                    "epoch_distance": float(row.get("epoch_distance_sec") or 0.0),
                }
            )
        except (TypeError, ValueError) as exc:
            raise OrbitDataError(f"invalid visibility row: {row}: {exc}") from exc
    return normalized


def _candidate_summary(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["norad_cat_id"])].append(row)
    candidates = []
    for cat_id, values in grouped.items():
        best = max(values, key=lambda item: item["elevation"])
        candidates.append(
            {
                "norad_cat_id": cat_id,
                "satellite_name": best["satellite_name"],
                "object_id": best.get("object_id") or None,
                "max_elevation_deg": round(max(item["elevation"] for item in values), 6),
                "minimum_epoch_distance_sec": round(
                    min(item["epoch_distance"] for item in values), 6
                ),
            }
        )
    return sorted(candidates, key=lambda item: (-item["max_elevation_deg"], item["norad_cat_id"]))


def _window(rows: list[dict[str, Any]], start: datetime, end: datetime, *, include_end: bool) -> list[dict[str, Any]]:
    if include_end:
        return [row for row in rows if start <= row["timestamp"] <= end]
    return [row for row in rows if start <= row["timestamp"] < end]


def annotate_event_document(
    event_document: dict[str, Any],
    visibility_rows: list[dict[str, Any]],
    *,
    observation_start_utc: str,
    window_before_sec: float = 1.0,
    window_after_sec: float = 1.0,
    visibility_source: str | None = None,
    visibility_sha256: str | None = None,
) -> dict[str, Any]:
    if window_before_sec < 0 or window_after_sec < 0:
        raise ValueError("annotation windows must be >= 0")
    origin = parse_utc(observation_start_utc)
    events = event_document.get("events")
    if not isinstance(events, list):
        raise OrbitDataError("event document must contain an events array")

    annotations = []
    for event in events:
        try:
            start = origin + timedelta(seconds=float(event["start_sec"]))
            end = origin + timedelta(seconds=float(event["end_sec"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise OrbitDataError(f"invalid event timing: {event}: {exc}") from exc
        before_rows = _window(
            visibility_rows,
            start - timedelta(seconds=window_before_sec),
            start,
            include_end=False,
        )
        during_rows = _window(visibility_rows, start, end, include_end=True)
        after_rows = _window(
            visibility_rows,
            end,
            end + timedelta(seconds=window_after_sec),
            include_end=True,
        )
        before = _candidate_summary(before_rows)
        during = _candidate_summary(during_rows)
        after = _candidate_summary(after_rows)
        ids = lambda values: {item["norad_cat_id"] for item in values}
        all_rows = before_rows + during_rows + after_rows
        annotations.append(
            {
                "event_id": str(event.get("event_id", "")),
                "event_type": str(event.get("event_type", "unknown")),
                "event_start_utc": iso_utc(start),
                "event_end_utc": iso_utc(end),
                "candidate_satellites_before": before,
                "candidate_satellites_during": during,
                "candidate_satellites_after": after,
                "candidate_set_changed": ids(before) != ids(during) or ids(during) != ids(after),
                "minimum_epoch_distance_sec": (
                    round(min(row["epoch_distance"] for row in all_rows), 6) if all_rows else None
                ),
                "source_type": "DERIVED",
                "interpretation": "visible candidates; not an identification of the connected satellite",
            }
        )

    return {
        "schema_version": "1.0",
        "annotation_type": "event_orbit_context",
        "generated_at_utc": utc_now_iso(),
        "generator": f"leo-replay {__version__}",
        "metadata": {
            "observation_start_utc": iso_utc(origin),
            "window_before_sec": window_before_sec,
            "window_after_sec": window_after_sec,
            "visibility_source": visibility_source,
            "visibility_sha256": visibility_sha256,
            "event_count": len(annotations),
            "semantics": "candidate visibility only; no connected-satellite assertion",
        },
        "annotations": annotations,
    }
