from __future__ import annotations

import json
from pathlib import Path

import pytest

from leo_replay.orbit.models import parse_utc
from leo_replay.orbit.selection import (
    HistoricalSelectionError,
    SelectionPolicy,
    build_observation_times,
    load_historical_elements,
    select_historical_elements,
)
from leo_replay.orbit.snapshot import SnapshotPart, write_snapshot

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "examples/orbit/iss-history.example.json"
OBSERVATION = parse_utc("2024-05-06T19:55:00Z")


def test_compare_selects_latest_available_and_nearest_epoch():
    collection = load_historical_elements(HISTORY)
    document = select_historical_elements(
        collection,
        [OBSERVATION],
        SelectionPolicy(mode="compare", position_warning_km=0.1),
    )
    satellite = document["observations"][0]["satellites"][0]
    assert satellite["causal"]["gp_id"] == 1002
    assert satellite["retrospective"]["gp_id"] == 1003
    assert satellite["causal"]["creation_date_utc"] == "2024-05-06T19:45:00.000000Z"
    assert satellite["retrospective"]["absolute_epoch_distance_sec"] == 60.0
    assert satellite["comparison"]["same_element"] is False
    assert satellite["comparison"]["causal_retrospective_position_delta_km"] > 0
    assert satellite["causal"]["position_at_observation"]["subpoint_latitude_deg"] is not None
    assert document["summary"]["causal_selected"] == 1
    assert document["summary"]["retrospective_selected"] == 1


def test_element_fields_are_optional_and_explicit():
    collection = load_historical_elements(HISTORY)
    compact = select_historical_elements(
        collection, [OBSERVATION], SelectionPolicy(mode="causal")
    )
    compact_selection = compact["observations"][0]["satellites"][0]["causal"]
    assert "element_fields" not in compact_selection
    portable = select_historical_elements(
        collection,
        [OBSERVATION],
        SelectionPolicy(mode="causal", include_element_fields=True),
    )
    portable_selection = portable["observations"][0]["satellites"][0]["causal"]
    assert portable_selection["element_fields"]["GP_ID"] == 1002


def test_availability_lag_changes_causal_selection():
    collection = load_historical_elements(HISTORY)
    document = select_historical_elements(
        collection,
        [OBSERVATION],
        SelectionPolicy(mode="causal", availability_lag_sec=900.0),
    )
    satellite = document["observations"][0]["satellites"][0]
    assert satellite["causal"]["gp_id"] == 1001
    assert satellite["retrospective"] is None
    assert document["observations"][0]["causal_knowledge_cutoff_utc"] == (
        "2024-05-06T19:40:00.000000Z"
    )


def test_missing_creation_date_is_explicit(tmp_path):
    rows = json.loads(HISTORY.read_text(encoding="utf-8"))
    rows[0].pop("CREATION_DATE")
    path = tmp_path / "history.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    collection = load_historical_elements(path)
    document = select_historical_elements(
        collection,
        [OBSERVATION],
        SelectionPolicy(mode="causal", missing_creation_date_policy="exclude"),
    )
    flags = document["observations"][0]["satellites"][0]["flags"]
    assert "records_missing_creation_date" in flags
    with pytest.raises(HistoricalSelectionError, match="no CREATION_DATE"):
        select_historical_elements(
            collection,
            [OBSERVATION],
            SelectionPolicy(mode="causal", missing_creation_date_policy="error"),
        )


def test_time_range_generation_and_input_exclusion():
    values = build_observation_times(
        start="2024-05-06T19:55:00Z", duration_sec=2.0, step_sec=1.0
    )
    assert len(values) == 3
    with pytest.raises(HistoricalSelectionError, match="either"):
        build_observation_times(
            times=["2024-05-06T19:55:00Z"],
            start="2024-05-06T19:55:00Z",
            duration_sec=1.0,
            step_sec=1.0,
        )


def test_verified_snapshot_directory_is_accepted(tmp_path):
    snapshot = tmp_path / "snapshot"
    write_snapshot(
        snapshot,
        provider="space-track",
        request={"provider": "space-track", "class": "gp_history", "format": "json"},
        output_format="json",
        parts=[SnapshotPart(HISTORY.read_bytes(), {}, "fixture://history")],
    )
    collection = load_historical_elements(snapshot)
    assert collection.provider == "space-track"
    assert collection.request_fingerprint is not None
    assert collection.snapshot_manifest_sha256 is not None
    assert len(collection.records) == 4
