from pathlib import Path
import csv

from leo_replay.orbit.annotation import annotate_event_document, load_visibility_rows
from leo_replay.orbit.visibility import VISIBILITY_FIELDS, write_visibility_csv


def visibility_row(timestamp, cat_id, name, elevation):
    return {
        "timestamp_utc": timestamp,
        "site_id": "test-site",
        "satellite_name": name,
        "norad_cat_id": cat_id,
        "object_id": "",
        "elevation_deg": elevation,
        "azimuth_deg": 180.0,
        "slant_range_km": 700.0,
        "visible": True,
        "element_epoch_utc": "2024-05-06T00:00:00Z",
        "epoch_distance_sec": 10.0,
        "stale_element": False,
        "propagation_error": "",
    }


def test_event_annotation_tracks_candidate_set_changes(tmp_path):
    path = tmp_path / "visibility.csv"
    write_visibility_csv(
        path,
        [
            visibility_row("2024-05-06T00:00:01.500000Z", "A", "SAT-A", 30.0),
            visibility_row("2024-05-06T00:00:02.000000Z", "A", "SAT-A", 35.0),
            visibility_row("2024-05-06T00:00:02.100000Z", "B", "SAT-B", 40.0),
            visibility_row("2024-05-06T00:00:03.000000Z", "B", "SAT-B", 45.0),
        ],
    )
    rows = load_visibility_rows(path)
    document = {
        "events": [
            {
                "event_id": "EV-1",
                "event_type": "handover_candidate",
                "start_sec": 2.0,
                "end_sec": 2.2,
            }
        ]
    }
    output = annotate_event_document(
        document,
        rows,
        observation_start_utc="2024-05-06T00:00:00Z",
        window_before_sec=1.0,
        window_after_sec=1.0,
    )
    annotation = output["annotations"][0]
    assert [item["norad_cat_id"] for item in annotation["candidate_satellites_before"]] == ["A"]
    assert {item["norad_cat_id"] for item in annotation["candidate_satellites_during"]} == {"A", "B"}
    assert [item["norad_cat_id"] for item in annotation["candidate_satellites_after"]] == ["B"]
    assert annotation["candidate_set_changed"] is True
    assert "not an identification" in annotation["interpretation"]


def test_header_only_visibility_produces_empty_candidates(tmp_path):
    path = tmp_path / "visibility.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=VISIBILITY_FIELDS).writeheader()
    rows = load_visibility_rows(path)
    output = annotate_event_document(
        {"events": [{"event_id": "EV-1", "start_sec": 0, "end_sec": 1}]},
        rows,
        observation_start_utc="2024-05-06T00:00:00Z",
    )
    annotation = output["annotations"][0]
    assert annotation["candidate_satellites_during"] == []
    assert annotation["minimum_epoch_distance_sec"] is None
