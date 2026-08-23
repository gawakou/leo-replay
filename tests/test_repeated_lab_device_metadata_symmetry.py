from pathlib import Path

import pytest

from leo_replay.repeated_lab import RepeatedLabError, _pair_skews


def _record(direction: str, applied_sec: float, device: str | None) -> dict[str, object]:
    return {
        "action": "timeseries_state",
        "event_id": None,
        "direction": direction,
        "planned_sec": 0.0,
        "applied_sec": applied_sec,
        "lateness_ms": applied_sec * 1000.0,
        "device": device,
    }


def test_pair_skews_accepts_device_metadata_on_both_directions() -> None:
    records = [
        _record("forward", 0.001, "veth-forward"),
        _record("reverse", 0.003, "veth-reverse"),
    ]

    assert _pair_skews(Path("profile-execution.jsonl"), records) == pytest.approx([2.0])


def test_pair_skews_accepts_legacy_pair_without_device_metadata() -> None:
    records = [
        _record("forward", 0.001, None),
        _record("reverse", 0.003, None),
    ]

    assert _pair_skews(Path("profile-execution.jsonl"), records) == pytest.approx([2.0])


@pytest.mark.parametrize(
    "forward_device,reverse_device",
    [
        ("veth-forward", None),
        (None, "veth-reverse"),
    ],
)
def test_pair_skews_rejects_asymmetric_device_metadata(
    forward_device: str | None, reverse_device: str | None
) -> None:
    records = [
        _record("forward", 0.001, forward_device),
        _record("reverse", 0.003, reverse_device),
    ]

    with pytest.raises(RepeatedLabError, match="asymmetric device metadata"):
        _pair_skews(Path("profile-execution.jsonl"), records)
