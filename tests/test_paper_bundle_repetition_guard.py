from __future__ import annotations

import pytest

from leo_replay.paper_bundle import PaperBundleError, render_paper_bundle_macros


def test_paper_bundle_rejects_three_run_smoke_summary() -> None:
    lab = {"fixed_runs": 3, "profile_runs": 3}
    event = {
        "summary_type": "repeated_event_replay",
        "evaluation_count": 3,
    }
    orbit = {
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": 3,
    }

    with pytest.raises(PaperBundleError, match="requires exactly 30 repetitions"):
        render_paper_bundle_macros(lab, event, orbit)


def test_paper_bundle_allows_explicit_nonpaper_repetition_override() -> None:
    lab = {"fixed_runs": 3, "profile_runs": 3}
    event = {
        "summary_type": "repeated_event_replay",
        "evaluation_count": 3,
    }
    orbit = {
        "summary_type": "repeated_event_orbit_context",
        "evaluation_count": 3,
    }

    with pytest.raises(PaperBundleError, match="missing summary field"):
        render_paper_bundle_macros(lab, event, orbit, expected_repetitions=3)
