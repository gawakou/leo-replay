from pathlib import Path

import pytest

from leo_replay.visualization import VisualizationError
from leo_replay.visualization.server import serve_visualization_bundle


def test_server_refuses_remote_bind_without_opt_in(tmp_path: Path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    with pytest.raises(VisualizationError, match="non-loopback"):
        serve_visualization_bundle(tmp_path, host="0.0.0.0", port=0)


def test_server_requires_index(tmp_path: Path):
    with pytest.raises(VisualizationError, match="index.html"):
        serve_visualization_bundle(tmp_path, port=0)
