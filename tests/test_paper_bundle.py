from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from leo_replay.paper_bundle import (
    PaperBundleError,
    build_provenance_manifest,
    render_paper_bundle_macros,
)


def _lab_summary() -> dict[str, object]:
    return {
        "fixed_runs": 30,
        "profile_runs": 30,
        "fixed": {
            "rtt_delta_ms": {
                "mean": 50.125,
                "standard_deviation": 1.25,
                "mean_ci95_half_width": 0.45,
            },
            "forward_realization_ratio": {
                "mean": 0.925,
                "standard_deviation": 0.012,
                "mean_ci95_half_width": 0.004,
            },
            "reverse_realization_ratio": {
                "mean": 0.91,
                "standard_deviation": 0.015,
                "mean_ci95_half_width": 0.005,
            },
            "reverse_forward_ratio": {"mean": 3.0049},
        },
        "execution": {
            "absolute_lateness_ms": {
                "mean": 2.345,
                "standard_deviation": 0.75,
                "mean_ci95_half_width": 0.27,
                "p95": 5.678,
                "p99": 8.901,
            },
            "forward_absolute_lateness_ms": {"p95": 4.321},
            "reverse_absolute_lateness_ms": {"p95": 6.543},
            "forward_reverse_skew_ms": {
                "mean": 1.234,
                "standard_deviation": 0.42,
                "mean_ci95_half_width": 0.15,
                "p95": 2.345,
                "p99": 3.456,
            },
            "run_mean_absolute_lateness_ms": {
                "mean": 2.111,
                "standard_deviation": 0.333,
                "mean_ci95_half_width": 0.119,
            },
            "run_p95_absolute_lateness_ms": {
                "mean": 5.432,
                "standard_deviation": 0.654,
                "mean_ci95_half_width": 0.234,
            },
            "run_forward_mean_absolute_lateness_ms": {"mean": 1.987},
            "run_reverse_mean_absolute_lateness_ms": {"mean": 2.235},
            "run_mean_forward_reverse_skew_ms": {
                "mean": 1.101,
                "standard_deviation": 0.222,
                "mean_ci95_half_width": 0.079,
            },
        },
    }


def _event_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_replay",
        "evaluation_count": 30,
        "event_count": 90,
        "detection": {"precision": 0.98, "recall": 0.97, "f1": 0.9749},
        "errors": {
            "start_time_error_sec": {"p95_abs": 0.1234},
            "duration_error_sec": {"p95_abs": 0.4567},
            "rtt_mae_ms": {"mean_abs": 3.219},
        },
    }


def _orbit_summary() -> dict[str, object]:
    return {
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": 30,
        "event_count": 90,
        "candidate_set_changed_ratio": 0.6111,
        "candidate_count": {"during": {"mean": 4.25}},
        "minimum_epoch_distance_sec": {"p95": 7200.0},
    }


def test_render_paper_bundle_macros() -> None:
    payload = render_paper_bundle_macros(_lab_summary(), _event_summary(), _orbit_summary())

    assert "\\newcommand{\\LeoFixedRuns}{30}" in payload
    assert "\\newcommand{\\LeoRttDeltaSdMs}{1.25}" in payload
    assert "\\newcommand{\\LeoRttDeltaCi95HalfWidthMs}{0.45}" in payload
    assert "\\newcommand{\\LeoLatenessCi95HalfWidthMs}{0.27}" in payload
    assert "\\newcommand{\\LeoDirectionSkewSdMs}{0.42}" in payload
    assert "\\newcommand{\\LeoRunLatenessMeanMs}{2.11}" in payload
    assert "\\newcommand{\\LeoRunLatenessCi95HalfWidthMs}{0.12}" in payload
    assert "\\newcommand{\\LeoRunDirectionSkewCi95HalfWidthMs}{0.08}" in payload
    assert "\\newcommand{\\LeoEventEvaluations}{30}" in payload
    assert "\\newcommand{\\LeoEventFOnePct}{97.5}" in payload
    assert "\\newcommand{\\LeoEventStartErrorP95Sec}{0.123}" in payload
    assert "\\newcommand{\\LeoOrbitCandidateChangedPct}{61.1}" in payload
    assert "\\newcommand{\\LeoOrbitCandidatesDuringMean}{4.25}" in payload


def test_render_paper_bundle_rejects_wrong_summary_type() -> None:
    event = _event_summary()
    event["summary_type"] = "other"

    with pytest.raises(PaperBundleError, match="repeated_event_replay"):
        render_paper_bundle_macros(_lab_summary(), event, _orbit_summary())


def test_render_paper_bundle_rejects_missing_metric() -> None:
    orbit = _orbit_summary()
    orbit.pop("candidate_set_changed_ratio")

    with pytest.raises(PaperBundleError, match="candidate_set_changed_ratio"):
        render_paper_bundle_macros(_lab_summary(), _event_summary(), orbit)


def _write_json(path: Path, document: dict[str, object]) -> None:
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")


def test_build_provenance_manifest_hashes_exact_inputs_and_output(tmp_path: Path) -> None:
    lab_path = tmp_path / "lab.json"
    event_path = tmp_path / "event.json"
    orbit_path = tmp_path / "orbit.json"
    output_path = tmp_path / "paper-metrics.tex"
    _write_json(lab_path, _lab_summary())
    _write_json(event_path, _event_summary())
    _write_json(orbit_path, _orbit_summary())
    payload = render_paper_bundle_macros(_lab_summary(), _event_summary(), _orbit_summary())

    manifest = build_provenance_manifest(lab_path, event_path, orbit_path, output_path, payload)

    assert manifest["summary_type"] == "paper_bundle_provenance"
    assert manifest["schema_version"] == 1
    assert manifest["inputs"]["lab"]["filename"] == "lab.json"
    assert manifest["inputs"]["lab"]["sha256"] == hashlib.sha256(lab_path.read_bytes()).hexdigest()
    assert manifest["inputs"]["event"]["sha256"] == hashlib.sha256(event_path.read_bytes()).hexdigest()
    assert manifest["inputs"]["orbit"]["sha256"] == hashlib.sha256(orbit_path.read_bytes()).hexdigest()
    assert manifest["output"]["filename"] == "paper-metrics.tex"
    assert manifest["output"]["sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()
