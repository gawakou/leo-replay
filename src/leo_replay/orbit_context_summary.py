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


def _stats(values: list[float]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    return {
        "count": len(finite),
        "mean": _rounded(statistics.fmean(finite)),
        "p50": _rounded(percentile(finite, 0.50)),
        "p95": _rounded(percentile(finite, 0.95)),
        "p99": _rounded(percentile(finite, 0.99)),
        "max": _rounded(max(finite)),
    }


def summarize_orbit_context_documents(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    documents = list(documents)
    annotations: list[dict[str, Any]] = []
    for document in documents:
        if document.get("annotation_type") != "event_orbit_context":
            raise ValueError("all inputs must have annotation_type='event_orbit_context'")
        rows = document.get("annotations")
        if not isinstance(rows, list):
            raise ValueError("orbit context input must contain an annotations list")
        annotations.extend(row for row in rows if isinstance(row, dict))

    changed = sum(bool(row.get("candidate_set_changed")) for row in annotations)
    candidate_counts: dict[str, list[float]] = {"before": [], "during": [], "after": []}
    epoch_distances: list[float] = []
    for row in annotations:
        for phase in candidate_counts:
            candidates = row.get(f"candidate_satellites_{phase}")
            if isinstance(candidates, list):
                candidate_counts[phase].append(float(len(candidates)))
        value = row.get("minimum_epoch_distance_sec")
        if value is not None:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                epoch_distances.append(abs(numeric))

    event_count = len(annotations)
    return {
        "schema_version": "1.0",
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": len(documents),
        "event_count": event_count,
        "candidate_set_changed_count": changed,
        "candidate_set_changed_ratio": _rounded(changed / event_count) if event_count else None,
        "candidate_count": {phase: _stats(values) for phase, values in candidate_counts.items()},
        "minimum_epoch_distance_sec": _stats(epoch_distances),
        "semantics": "candidate visibility only; no connected-satellite assertion",
    }


def summarize_orbit_context_files(paths: Iterable[Path]) -> dict[str, Any]:
    documents = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            documents.append(json.load(handle))
    return summarize_orbit_context_documents(documents)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate LEO-Replay event orbit-context annotations for paper reporting."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="event-orbit-context annotation JSON files")
    parser.add_argument("--output", type=Path, help="write summary JSON to this path")
    args = parser.parse_args(argv)

    summary = summarize_orbit_context_files(args.inputs)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
