from pathlib import Path
import csv

from leo_replay.orbit import ObserverSite, compute_visibility, load_catalog, write_visibility_csv

ROOT = Path(__file__).resolve().parents[1]
ORBIT = ROOT / "examples/orbit"


def test_visibility_calculation_is_offline_and_finite(tmp_path):
    catalog = load_catalog(ORBIT / "iss-omm.example.json")
    site = ObserverSite.load(ORBIT / "observer-hiroshima.example.json")
    result = compute_visibility(
        catalog,
        site,
        start_utc="2024-05-06T19:53:05Z",
        duration_sec=2.0,
        step_sec=1.0,
        minimum_elevation_deg=-90.0,
        only_visible=False,
    )
    assert len(result.rows) == 3
    assert result.metadata["sample_count"] == 3
    assert result.metadata["propagation_error_count"] == 0
    assert result.metadata["stale_row_count"] == 0
    assert all(isinstance(row["elevation_deg"], float) for row in result.rows)
    assert all(row["norad_cat_id"] == "25544" for row in result.rows)

    output = tmp_path / "visibility.csv"
    write_visibility_csv(output, result.rows)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 3
    assert rows[0]["site_id"] == "hiroshima-example"


def test_visibility_flags_stale_elements():
    catalog = load_catalog(ORBIT / "iss-omm.example.json")
    site = ObserverSite.load(ORBIT / "observer-hiroshima.example.json")
    result = compute_visibility(
        catalog,
        site,
        start_utc="2024-06-06T19:53:05Z",
        duration_sec=0.0,
        step_sec=1.0,
        minimum_elevation_deg=-90.0,
        only_visible=False,
        stale_after_days=14.0,
    )
    assert result.rows[0]["stale_element"] is True
    assert result.metadata["stale_row_count"] == 1


def test_only_visible_can_produce_header_only_csv(tmp_path):
    catalog = load_catalog(ORBIT / "iss-omm.example.json")
    site = ObserverSite.load(ORBIT / "observer-hiroshima.example.json")
    result = compute_visibility(
        catalog,
        site,
        start_utc="2024-05-06T19:53:05Z",
        duration_sec=0.0,
        step_sec=1.0,
        minimum_elevation_deg=90.0,
        only_visible=True,
    )
    assert result.rows == ()
    output = tmp_path / "empty.csv"
    write_visibility_csv(output, result.rows)
    assert output.read_text(encoding="utf-8").startswith("timestamp_utc,")
