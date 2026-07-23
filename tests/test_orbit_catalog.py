from pathlib import Path

import pytest

from leo_replay.orbit import ObserverSite, OrbitDataError, load_catalog
from leo_replay.orbit.models import sha256_file
from leo_replay.orbit.provenance import create_source_manifest

ROOT = Path(__file__).resolve().parents[1]
ORBIT = ROOT / "examples/orbit"


@pytest.mark.parametrize(
    ("filename", "expected_format"),
    [
        ("iss-omm.example.json", "omm-json"),
        ("iss-omm.example.csv", "omm-csv"),
        ("iss-tle.example.tle", "tle"),
    ],
)
def test_load_supported_orbit_formats(filename, expected_format):
    path = ORBIT / filename
    catalog = load_catalog(path)
    assert catalog.source_format == expected_format
    assert len(catalog.satellites) == 1
    satellite = catalog.satellites[0]
    assert satellite.name == "ISS (ZARYA)"
    assert satellite.norad_cat_id == "25544"
    assert satellite.epoch_utc.startswith("2024-05-06T19:53:04")


def test_catalog_selects_by_name_and_catalog_id():
    catalog = load_catalog(ORBIT / "iss-omm.example.json")
    assert len(catalog.select(["ISS"]).satellites) == 1
    assert len(catalog.select(["25544"]).satellites) == 1
    with pytest.raises(OrbitDataError):
        catalog.select(["does-not-exist"])


def test_source_manifest_records_hash_and_epoch():
    path = ORBIT / "iss-omm.example.json"
    catalog = load_catalog(path)
    manifest = create_source_manifest(
        catalog,
        source_name="offline fixture",
        retrieved_at_utc="2024-05-07T00:00:00Z",
    )
    assert manifest["schema_version"] == "1.0"
    assert manifest["satellite_count"] == 1
    assert manifest["source"]["sha256"] == sha256_file(path)
    assert manifest["source"]["retrieved_at_utc"] == "2024-05-07T00:00:00.000000Z"


def test_observer_site_validation():
    site = ObserverSite.load(ORBIT / "observer-hiroshima.example.json")
    assert site.site_id == "hiroshima-example"
    assert site.latitude_deg == 34.4
    with pytest.raises(OrbitDataError):
        ObserverSite("bad", "Bad", 91.0, 0.0).validate()
