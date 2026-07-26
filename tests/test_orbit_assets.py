from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_orbit_schemas_and_examples_are_valid_json():
    paths = [
        ROOT / "schemas/observer-site-v1.schema.json",
        ROOT / "schemas/orbit-source-v1.schema.json",
        ROOT / "schemas/visibility-profile-v1.schema.json",
        ROOT / "schemas/event-orbit-annotation-v1.schema.json",
        ROOT / "schemas/orbit-snapshot-v1.schema.json",
        ROOT / "schemas/historical-element-selection-v1.schema.json",
        ROOT / "examples/orbit/observer-hiroshima.example.json",
        ROOT / "examples/orbit/iss-omm.example.json",
        ROOT / "examples/orbit/iss-history.example.json",
    ]
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))


def test_orbit_documentation_exists():
    assert (ROOT / "docs/ORBIT_CONTEXT.md").is_file()
    assert (ROOT / "docs/V0.4.0_IMPLEMENTATION.md").is_file()
    assert (ROOT / "docs/ORBIT_ACQUISITION.md").is_file()
    assert (ROOT / "docs/V0.4.1_IMPLEMENTATION.md").is_file()
    assert (ROOT / "docs/HISTORICAL_ELEMENT_SELECTION.md").is_file()
    assert (ROOT / "docs/V0.4.2_IMPLEMENTATION.md").is_file()
