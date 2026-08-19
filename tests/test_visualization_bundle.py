from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from leo_replay.visualization import VisualizationError, build_visualization_bundle


def write_fixture(tmp_path: Path) -> dict[str, Path]:
    selection = {
        "schema_version": "1.0",
        "selection_type": "historical_orbit_element_selection",
        "generated_at_utc": "2026-07-26T00:00:00Z",
        "generator": "test",
        "source": {"path": "history.json", "format": "omm-json", "sha256": "0" * 64, "record_count": 2},
        "policy": {"mode": "compare"},
        "summary": {},
        "observations": [],
    }
    for index, second in enumerate((0, 30)):
        selection["observations"].append(
            {
                "observation_time_utc": f"2026-07-26T00:00:{second:02d}Z",
                "causal_knowledge_cutoff_utc": f"2026-07-26T00:00:{second:02d}Z",
                "satellites": [
                    {
                        "norad_cat_id": "25544",
                        "object_name": "ISS (ZARYA)",
                        "available_record_count": 2,
                        "causal": {
                            "epoch_utc": "2026-07-25T23:50:00Z",
                            "creation_date_utc": "2026-07-25T23:55:00Z",
                            "absolute_epoch_distance_sec": 600 + second,
                            "stale_element": False,
                            "record_fingerprint": "a" * 64,
                            "position_at_observation": {
                                "gcrs_km": [1, 2, 3],
                                "subpoint_latitude_deg": 34.0 + index,
                                "subpoint_longitude_deg": 132.0 + index,
                                "height_km": 550.0,
                                "propagation_error": "",
                            },
                        },
                        "retrospective": {
                            "epoch_utc": "2026-07-26T00:00:00Z",
                            "creation_date_utc": "2026-07-26T00:05:00Z",
                            "absolute_epoch_distance_sec": second,
                            "stale_element": False,
                            "record_fingerprint": "b" * 64,
                            "position_at_observation": {
                                "gcrs_km": [1.1, 2.1, 3.1],
                                "subpoint_latitude_deg": 34.1 + index,
                                "subpoint_longitude_deg": 132.2 + index,
                                "height_km": 551.0,
                                "propagation_error": "",
                            },
                        },
                        "comparison": {"causal_retrospective_position_delta_km": 12.5 + index},
                        "bracketing_element_sensitivity": {},
                        "flags": ["position_selection_sensitivity_warning"] if index else [],
                    }
                ],
            }
        )
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")

    site_path = tmp_path / "site.json"
    site_path.write_text(
        json.dumps(
            {
                "site_id": "hiroshima-test",
                "name": "Hiroshima test site",
                "latitude_deg": 34.4,
                "longitude_deg": 132.7,
                "elevation_m": 30,
            }
        ),
        encoding="utf-8",
    )

    profile_path = tmp_path / "profile.csv"
    with profile_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sec", "delay_ms", "rtt_ms", "loss_pct", "rate_mbit", "note"],
        )
        writer.writeheader()
        writer.writerow({"sec": 0, "delay_ms": 15, "rtt_ms": 30, "loss_pct": 0, "rate_mbit": 100, "note": "normal"})
        writer.writerow({"sec": 30, "delay_ms": 40, "rtt_ms": 80, "loss_pct": 2, "rate_mbit": 40, "note": "degraded"})

    visibility_path = tmp_path / "visibility.csv"
    with visibility_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "timestamp_utc", "satellite_name", "norad_cat_id", "visible",
                "elevation_deg", "azimuth_deg", "slant_range_km", "stale_element",
                "propagation_error",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": "2026-07-26T00:00:00Z",
                "satellite_name": "ISS (ZARYA)",
                "norad_cat_id": "25544",
                "visible": "true",
                "elevation_deg": 45,
                "azimuth_deg": 120,
                "slant_range_km": 900,
                "stale_element": "false",
                "propagation_error": "",
            }
        )

    events_path = tmp_path / "events.json"
    events_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "profile_type": "event",
                "metadata": {},
                "baseline": {},
                "events": [
                    {
                        "event_id": "EV-1",
                        "event_type": "handover_suspected",
                        "start_sec": 20,
                        "end_sec": 40,
                        "duration_sec": 20,
                        "severity": 2,
                        "confidence": 0.8,
                        "source_type": "DERIVED",
                        "parameters": {"rate_mbit": 40, "delay_ms": 40, "jitter_ms": 5, "loss_pct": 2, "spike_ms": 0},
                        "observations": {},
                        "calibration": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return {
        "selection": selection_path,
        "site": site_path,
        "profile": profile_path,
        "visibility": visibility_path,
        "events": events_path,
    }


def test_build_self_contained_visualization_bundle(tmp_path: Path):
    source = write_fixture(tmp_path)
    output = tmp_path / "bundle"
    result = build_visualization_bundle(
        selection_path=source["selection"],
        site_path=source["site"],
        profile_path=source["profile"],
        visibility_path=source["visibility"],
        events_path=source["events"],
        output_dir=output,
        title="Test orbit comparison",
    )

    assert result["status"] == "built"
    assert result["frames"] == 2
    assert result["satellites"] == 1
    document = json.loads((output / "data.json").read_text(encoding="utf-8"))
    assert document["visualization_type"] == "orbit_communication_timeline"
    assert document["source"]["selection"]["path"] == "selection.json"
    assert str(tmp_path) not in (output / "data.json").read_text(encoding="utf-8")
    assert document["frames"][0]["communication"]["rtt_ms"] == 30.0
    assert document["frames"][0]["satellites"][0]["visibility"]["visible"] is True
    assert document["frames"][1]["events"][0]["event_type"] == "handover_suspected"
    assert document["summary"]["maximum_causal_retrospective_position_delta_km"] == 13.5

    index = (output / "index.html").read_text(encoding="utf-8")
    assert "Test orbit comparison" in index
    assert "orbit_communication_timeline" in index
    assert "https://" not in index
    assert 'src="http' not in index
    assert 'href="http' not in index
    assert "Natural Earth" not in index  # notice is kept outside the browser payload

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = output / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]


def test_bundle_refuses_nonempty_output_without_force(tmp_path: Path):
    source = write_fixture(tmp_path)
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "existing.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(VisualizationError, match="not empty"):
        build_visualization_bundle(
            selection_path=source["selection"],
            site_path=source["site"],
            output_dir=output,
        )
    build_visualization_bundle(
        selection_path=source["selection"],
        site_path=source["site"],
        output_dir=output,
        force=True,
    )
    assert not (output / "existing.txt").exists()
