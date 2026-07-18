import json
from pathlib import Path

from leo_replay.directional_profile import ConversionPolicy, directionalize_event_document
from leo_replay.event_profile import load_document, save_document, validate_document

ROOT = Path(__file__).resolve().parents[1]


def test_directional_event_extension_is_valid(tmp_path: Path):
    document = load_document(ROOT / "examples/events-v1.example.json")
    updated = directionalize_event_document(document, policy=ConversionPolicy())
    assert "directions" in updated["baseline"]
    assert "directions" in updated["events"][0]
    # 45 ms base + 25 ms spike is split equally between two directions.
    assert updated["events"][0]["directions"]["forward"]["delay_ms"] == 35.0
    assert not validate_document(updated)
    output = tmp_path / "directional-events.json"
    save_document(output, updated)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["metadata"]["directionalization"]["loss_policy"] == "equivalent"
