from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
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


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _error_stats(values: list[float]) -> dict[str, float | int | None]:
    absolute = [abs(float(value)) for value in values]
    if not absolute:
        return {
            "count": 0,
            "mean_abs": None,
            "p50_abs": None,
            "p95_abs": None,
            "p99_abs": None,
            "max_abs": None,
        }
    return {
        "count": len(absolute),
        "mean_abs": _rounded(statistics.fmean(absolute)),
        "p50_abs": _rounded(percentile(absolute, 0.50)),
        "p95_abs": _rounded(percentile(absolute, 0.95)),
        "p99_abs": _rounded(percentile(absolute, 0.99)),
        "max_abs": _rounded(max(absolute)),
    }


def _strict_bool(value: Any, *, field: str, event_index: int) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"event {event_index} has invalid {field} {value!r}; expected boolean")
    return value


def _optional_finite_number(value: Any, *, field: str, event_index: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"event {event_index} has invalid {field} {value!r}; expected number or null")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"event {event_index} has non-finite {field} {value!r}")
    return numeric


def summarize_event_documents(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    documents = list(documents)
    events: list[dict[str, Any]] = []
    events_per_evaluation: list[int] = []
    for document_index, document in enumerate(documents, start=1):
        if document.get("evaluation_type") != "event_replay":
            raise ValueError("all inputs must have evaluation_type='event_replay'")
        rows = document.get("events")
        if not isinstance(rows, list):
            raise ValueError("event replay input must contain an events list")
        events_per_evaluation.append(len(rows))
        for row_index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(
                    f"event replay input {document_index} contains non-object event at index {row_index}"
                )
            events.append(row)

    normalized: list[dict[str, Any]] = []
    for event_index, row in enumerate(events, start=1):
        measured = row.get("measured")
        replayed = row.get("replayed")
        errors = row.get("errors")
        if not isinstance(measured, dict):
            raise ValueError(f"event {event_index} must contain a measured object")
        if not isinstance(replayed, dict):
            raise ValueError(f"event {event_index} must contain a replayed object")
        if not isinstance(errors, dict):
            raise ValueError(f"event {event_index} must contain an errors object")
        normalized.append(
            {
                "measured_detected": _strict_bool(
                    measured.get("detected"), field="measured.detected", event_index=event_index
                ),
                "replayed_detected": _strict_bool(
                    replayed.get("detected"), field="replayed.detected", event_index=event_index
                ),
                "errors": errors,
            }
        )

    reference_detected = sum(row["measured_detected"] for row in normalized)
    replay_detected = sum(row["replayed_detected"] for row in normalized)
    matched = sum(row["measured_detected"] and row["replayed_detected"] for row in normalized)
    missed = sum(row["measured_detected"] and not row["replayed_detected"] for row in normalized)
    spurious = sum(not row["measured_detected"] and row["replayed_detected"] for row in normalized)

    precision = matched / replay_detected if replay_detected else None
    recall = matched / reference_detected if reference_detected else None
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = 2.0 * precision * recall / (precision + recall)

    error_keys = (
        "start_time_error_sec",
        "end_time_error_sec",
        "duration_error_sec",
        "peak_time_error_sec",
        "peak_rtt_error_ms",
        "event_mean_rtt_error_ms",
        "timeout_ratio_error",
        "rtt_mae_ms",
        "rtt_rmse_ms",
    )
    error_summary: dict[str, Any] = {}
    for key in error_keys:
        values: list[float] = []
        for event_index, row in enumerate(normalized, start=1):
            numeric = _optional_finite_number(
                row["errors"].get(key), field=f"errors.{key}", event_index=event_index
            )
            if numeric is not None:
                values.append(numeric)
        error_summary[key] = _error_stats(values)

    return {
        "schema_version": "1.0",
        "summary_type": "repeated_event_replay",
        "evaluation_count": len(documents),
        "event_count": len(events),
        "events_per_evaluation": events_per_evaluation,
        "detection": {
            "reference_detected_count": reference_detected,
            "replay_detected_count": replay_detected,
            "matched_detected_count": matched,
            "missed_detected_count": missed,
            "spurious_detected_count": spurious,
            "precision": _rounded(precision),
            "recall": _rounded(recall),
            "f1": _rounded(f1),
        },
        "errors": error_summary,
    }


def summarize_event_files(paths: Iterable[Path]) -> dict[str, Any]:
    documents = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            documents.append(json.load(handle))
    return summarize_event_documents(documents)


def _reject_output_input_collision(inputs: Iterable[Path], output: Path | None) -> None:
    if output is None:
        return
    output_path = output.resolve()
    for input_path in inputs:
        if input_path.resolve() == output_path:
            raise ValueError(f"output path must differ from input path: {input_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate repeated LEO-Replay event-replay evaluations for paper reporting."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="event-replay evaluation JSON files")
    parser.add_argument("--output", type=Path, help="write summary JSON to this path")
    args = parser.parse_args(argv)

    _reject_output_input_collision(args.inputs, args.output)
    summary = summarize_event_files(args.inputs)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
