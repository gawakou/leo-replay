from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from leo_replay.paper_summary import PaperSummaryError, render_latex_macros


class PaperBundleError(ValueError):
    """Raised when VTCA paper summaries cannot be combined safely."""


def _number(document: dict[str, Any], *path: str) -> float:
    current: Any = document
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise PaperBundleError("missing summary field: " + ".".join(path))
        current = current[key]
    try:
        return float(current)
    except (TypeError, ValueError) as exc:
        raise PaperBundleError("non-numeric summary field: " + ".".join(path)) from exc


def _integer(document: dict[str, Any], *path: str) -> int:
    value = _number(document, *path)
    if not value.is_integer():
        raise PaperBundleError("non-integer summary field: " + ".".join(path))
    return int(value)


def _require_type(document: dict[str, Any], key: str, expected: str) -> None:
    actual = document.get(key)
    if actual != expected:
        raise PaperBundleError(f"expected {key}={expected!r}, got {actual!r}")


def render_paper_bundle_macros(
    lab_summary: dict[str, Any],
    event_summary: dict[str, Any],
    orbit_summary: dict[str, Any],
) -> str:
    """Render one stable macro file spanning all headline VTCA evaluation dimensions."""
    _require_type(event_summary, "summary_type", "repeated_event_replay")
    _require_type(orbit_summary, "summary_type", "repeated_event_orbit_context")

    try:
        lab_payload = render_latex_macros(lab_summary).rstrip("\n")
    except PaperSummaryError as exc:
        raise PaperBundleError(str(exc)) from exc

    values: list[tuple[str, str]] = [
        ("LeoEventEvaluations", str(_integer(event_summary, "evaluation_count"))),
        ("LeoEventCount", str(_integer(event_summary, "event_count"))),
        ("LeoEventPrecisionPct", f'{100.0 * _number(event_summary, "detection", "precision"):.1f}'),
        ("LeoEventRecallPct", f'{100.0 * _number(event_summary, "detection", "recall"):.1f}'),
        ("LeoEventFOnePct", f'{100.0 * _number(event_summary, "detection", "f1"):.1f}'),
        (
            "LeoEventStartErrorP95Sec",
            f'{_number(event_summary, "errors", "start_time_error_sec", "p95_abs"):.3f}',
        ),
        (
            "LeoEventDurationErrorP95Sec",
            f'{_number(event_summary, "errors", "duration_error_sec", "p95_abs"):.3f}',
        ),
        (
            "LeoEventRttMaeMeanMs",
            f'{_number(event_summary, "errors", "rtt_mae_ms", "mean_abs"):.2f}',
        ),
        ("LeoOrbitEvaluations", str(_integer(orbit_summary, "evaluation_count"))),
        ("LeoOrbitEventCount", str(_integer(orbit_summary, "event_count"))),
        (
            "LeoOrbitCandidateChangedPct",
            f'{100.0 * _number(orbit_summary, "candidate_set_changed_ratio"):.1f}',
        ),
        (
            "LeoOrbitCandidatesDuringMean",
            f'{_number(orbit_summary, "candidate_count", "during", "mean"):.2f}',
        ),
        (
            "LeoOrbitEpochDistanceP95Sec",
            f'{_number(orbit_summary, "minimum_epoch_distance_sec", "p95"):.1f}',
        ),
    ]
    lines = [
        lab_payload,
        "% Event replay and orbit-context macros generated from repeated summaries.",
        *[f"\\newcommand{{\\{name}}}{{{value}}}" for name, value in values],
    ]
    return "\n".join(lines) + "\n"


def _load_object(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperBundleError(f"cannot read {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PaperBundleError(f"summary root must be a JSON object: {path}")
    return document


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _validate_distinct_paths(
    lab_path: Path,
    event_path: Path,
    orbit_path: Path,
    output_path: Path,
    manifest_path: Path | None,
) -> None:
    """Reject path aliases that could overwrite paper inputs or generated artifacts."""
    named_paths: list[tuple[str, Path]] = [
        ("lab", lab_path),
        ("event", event_path),
        ("orbit", orbit_path),
        ("output", output_path),
    ]
    if manifest_path is not None:
        named_paths.append(("manifest", manifest_path))

    resolved: dict[Path, str] = {}
    for name, path in named_paths:
        canonical = path.expanduser().resolve(strict=False)
        previous = resolved.get(canonical)
        if previous is not None:
            raise PaperBundleError(
                f"paper bundle paths must be distinct: {previous} and {name} both resolve to {canonical}"
            )
        resolved[canonical] = name


def build_provenance_manifest(
    lab_path: Path,
    event_path: Path,
    orbit_path: Path,
    output_path: Path,
    output_payload: str,
) -> dict[str, Any]:
    """Describe the exact summary inputs and generated macro payload used for a paper result."""
    inputs: dict[str, dict[str, str]] = {}
    for name, path in (("lab", lab_path), ("event", event_path), ("orbit", orbit_path)):
        try:
            digest = _sha256_bytes(path.read_bytes())
        except OSError as exc:
            raise PaperBundleError(f"cannot hash {path}: {exc}") from exc
        inputs[name] = {"filename": path.name, "sha256": digest}

    return {
        "summary_type": "paper_bundle_provenance",
        "schema_version": 1,
        "inputs": inputs,
        "output": {
            "filename": output_path.name,
            "sha256": _sha256_bytes(output_payload.encode("utf-8")),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render one VTCA LaTeX macro file from lab, event, and orbit summaries."
    )
    parser.add_argument("--lab", required=True, type=Path, help="repeated lab summary JSON")
    parser.add_argument("--event", required=True, type=Path, help="repeated event replay summary JSON")
    parser.add_argument("--orbit", required=True, type=Path, help="repeated orbit context summary JSON")
    parser.add_argument("--output", required=True, type=Path, help="output LaTeX macro file")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="optional provenance JSON containing SHA-256 hashes of all inputs and the generated macro file",
    )
    args = parser.parse_args(argv)

    try:
        _validate_distinct_paths(args.lab, args.event, args.orbit, args.output, args.manifest)
        payload = render_paper_bundle_macros(
            _load_object(args.lab),
            _load_object(args.event),
            _load_object(args.orbit),
        )
        manifest = (
            build_provenance_manifest(args.lab, args.event, args.orbit, args.output, payload)
            if args.manifest is not None
            else None
        )
    except PaperBundleError as exc:
        parser.error(str(exc))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    if args.manifest is not None and manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
