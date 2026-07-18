#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from leo_replay.lab_metrics import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
