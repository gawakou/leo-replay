from __future__ import annotations

import pytest

from leo_replay.paper_bundle import PaperBundleError, _validate_event_orbit_alignment


def test_event_orbit_alignment_accepts_matching_event_counts() -> None:
    _validate_event_orbit_alignment({"event_count": 90}, {"event_count": 90})


def test_event_orbit_alignment_rejects_mismatched_event_counts() -> None:
    with pytest.raises(PaperBundleError, match="same number of events"):
        _validate_event_orbit_alignment({"event_count": 90}, {"event_count": 89})
