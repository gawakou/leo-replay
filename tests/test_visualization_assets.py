from importlib.resources import files
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_visualization_assets_are_packaged_and_offline():
    assets = files("leo_replay.visualization.assets")
    for name in ("index.template.html", "style.css", "app.js", "world-land.geojson", "NOTICE.txt"):
        assert assets.joinpath(name).is_file()
    json.loads(assets.joinpath("world-land.geojson").read_text(encoding="utf-8"))
    template = assets.joinpath("index.template.html").read_text(encoding="utf-8")
    javascript = assets.joinpath("app.js").read_text(encoding="utf-8")
    assert "https://" not in template
    assert "http://" not in template
    assert "fetch(" not in javascript


def test_visualization_schema_and_docs_exist():
    json.loads((ROOT / "schemas/visualization-bundle-v1.schema.json").read_text(encoding="utf-8"))
    json.loads((ROOT / "examples/visualization/events.example.json").read_text(encoding="utf-8"))
    assert (ROOT / "docs/SYNCHRONIZED_VISUALIZATION.md").is_file()
    assert (ROOT / "docs/V0.4.3_IMPLEMENTATION.md").is_file()
    assert (ROOT / "THIRD_PARTY_NOTICES.md").is_file()
