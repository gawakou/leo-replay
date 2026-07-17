import csv
import json
from pathlib import Path

import pytest

from leo_replay.directional_profile import (
    ConversionPolicy,
    DirectionalProfileError,
    LinkCondition,
    directionalize_condition,
    end_to_end_loss_pct,
    read_directional_csv,
    write_directional_csv,
)


def test_legacy_profile_is_split_without_changing_end_to_end_loss(tmp_path: Path):
    source = tmp_path / "legacy.csv"
    source.write_text(
        "sec,delay_ms,jitter_ms,loss_pct,rate_mbit,note\n"
        "0,40,8,10,100,handover\n",
        encoding="utf-8",
    )
    policy = ConversionPolicy(reverse_default_rate_mbit=260.0)
    states = read_directional_csv(source, policy=policy)
    assert len(states) == 1
    state = states[0]
    assert state.forward.delay_ms == pytest.approx(20.0)
    assert state.reverse.delay_ms == pytest.approx(20.0)
    assert state.forward.jitter_ms == pytest.approx(4.0)
    assert state.reverse.jitter_ms == pytest.approx(4.0)
    assert state.forward.rate_mbit == pytest.approx(100.0)
    assert state.reverse.rate_mbit == pytest.approx(260.0)
    assert end_to_end_loss_pct(state.forward.loss_pct, state.reverse.loss_pct) == pytest.approx(10.0)


def test_directional_alias_columns_are_supported(tmp_path: Path):
    source = tmp_path / "directional.csv"
    source.write_text(
        "sec,delay_up_ms,jitter_up_ms,loss_up_pct,rate_up_mbit,"
        "delay_down_ms,jitter_down_ms,loss_down_pct,rate_down_mbit\n"
        "0,10,1,2,50,20,2,3,80\n",
        encoding="utf-8",
    )
    state = read_directional_csv(source)[0]
    assert state.forward.delay_ms == pytest.approx(10.0)
    assert state.reverse.delay_ms == pytest.approx(20.0)
    assert state.forward.rate_mbit == pytest.approx(50.0)
    assert state.reverse.rate_mbit == pytest.approx(80.0)


def test_directional_writer_uses_canonical_columns(tmp_path: Path):
    source = tmp_path / "legacy.csv"
    source.write_text("sec,delay_ms,jitter_ms,loss_pct,rate_mbit\n0,20,2,0,100\n")
    states = read_directional_csv(source)
    output = tmp_path / "directional.csv"
    write_directional_csv(output, states)
    with output.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    assert "forward_delay_ms" in row
    assert "reverse_delay_ms" in row
    assert float(row["forward_delay_ms"]) == pytest.approx(10.0)


def test_incomplete_directional_row_is_rejected(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("sec,forward_delay_ms\n0,10\n", encoding="utf-8")
    with pytest.raises(DirectionalProfileError):
        read_directional_csv(source)


def test_mirror_policy():
    forward, reverse = directionalize_condition(
        LinkCondition(delay_ms=25, jitter_ms=3, loss_pct=5, rate_mbit=70),
        ConversionPolicy(
            delay_policy="mirror",
            jitter_policy="mirror",
            loss_policy="mirror",
            rate_policy="mirror",
        ),
    )
    assert forward == reverse
