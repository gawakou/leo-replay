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


def _validated_candidate_list(value: Any, *, key: str, annotation_index: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"orbit context annotation {annotation_index} {key} must be a list")

    candidates: list[dict[str, Any]] = []
    seen_norad_ids: set[str] = set()
    for candidate_index, candidate in enumerate(value, start=1):
        if not isinstance(candidate, dict):
            raise ValueError(
                f"orbit context annotation {annotation_index} {key}[{candidate_index}] must be an object"
            )
        norad_cat_id = candidate.get("norad_cat_id")
        if not isinstance(norad_cat_id, str) or not norad_cat_id.strip():
            raise ValueError(
                f"orbit context annotation {annotation_index} {key}[{candidate_index}] "
                "norad_cat_id must be a non-empty string"
            )
        normalized_id = norad_cat_id.strip()
        if normalized_id in seen_norad_ids:
            raise ValueError(
                f"orbit context annotation {annotation_index} {key} contains duplicate "
                f"norad_cat_id {normalized_id!r}"
            )
        seen_norad_ids.add(normalized_id)
        candidates.append(candidate)
    return candidates


def _validated_annotation(row: Any, index: int) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"orbit context annotation {index} must be an object")

    changed = row.get("candidate_set_changed")
    if type(changed) is not bool:
        raise ValueError(f"orbit context annotation {index} candidate_set_changed must be boolean")

    for phase in ("before", "during", "after"):
        key = f"candidate_satellites_{phase}"
        _validated_candidate_list(row.get(key), key=key, annotation_index=index)

    value = row.get("minimum_epoch_distance_sec")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"orbit context annotation {index} minimum_epoch_distance_sec must be numeric or null"
            )
        if not math.isfinite(float(value)):
            raise ValueError(
                f"orbit context annotation {index} minimum_epoch_distance_sec must be finite"
            )
        if float(value) < 0.0:
            raise ValueError(
                f"orbit context annotation {index} minimum_epoch_distance_sec must be nonnegative"
            )

    return row


def summarize_orbit_context_documents(documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    documents = list(documents)
    annotations: list[dict[str, Any]] = []
    events_per_evaluation: list[int] = []
    annotation_index = 0
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError("orbit context input must be an object")
        if document.get("annotation_type") != "event_orbit_context":
            raise ValueError("all inputs must have annotation_type='event_orbit_context'")
        rows = document.get("annotations")
        if not isinstance(rows, list):
            raise ValueError("orbit context input must contain an annotations list")
        events_per_evaluation.append(len(rows))
        for row in rows:
            annotations.append(_validated_annotation(row, annotation_index))
            annotation_index += 1

    changed = sum(1 for row in annotations if row["candidate_set_changed"])
    candidate_counts: dict[str, list[float]] = {"before": [], "during": [], "after": []}
    epoch_distances: list[float] = []
    for row in annotations:
        for phase in candidate_counts:
            candidates = row[f"candidate_satellites_{phase}"]
            candidate_counts[phase].append(float(len(candidates)))
        value = row.get("minimum_epoch_distance_sec")
        if value is not None:
            epoch_distances.append(float(value))

    event_count = len(annotations)
    return {
        "schema_version": "1.0",
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": len(documents),
        "event_count": event_count,
        "events_per_evaluation": events_per_evaluation,
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


def _validated_unique_input_paths(inputs: Iterable[Path]) -> list[Path]:
    paths = list(inputs)
    seen: set[Path] = set()
    for path in paths:
        canonical = path.resolve()
        if canonical in seen:
            raise ValueError(f"duplicate input path is not allowed: {path}")
        seen.add(canonical)
    return paths


def _reject_output_input_collision(inputs: Iterable[Path], output: Path | None) -> None:
    if output is None:
        return
    output_path = output.resolve()
    for input_path in inputs:
        if input_path.resolve() == output_path:
            raise ValueError(f"output path must differ from input path: {input_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate LEO-Replay event orbit-context annotations for paper reporting."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="event-orbit-context annotation JSON files")
    parser.add_argument("--output", type=Path, help="write summary JSON to this path")
    args = parser.parse_args(argv)

    inputs = _validated_unique_input_paths(args.inputs)
    _reject_output_input_collision(inputs, args.output)
    summary = summarize_orbit_context_files(inputs)
    rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())