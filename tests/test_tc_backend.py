from leo_replay.directional_profile import LinkCondition
from leo_replay.tc_backend import build_netem_command


def test_build_netem_command_contains_all_directional_parameters():
    command = build_netem_command(
        "eth-test",
        LinkCondition(
            delay_ms=12,
            jitter_ms=2,
            loss_pct=1.5,
            rate_mbit=80,
            reorder_pct=0.5,
            correlation_pct=10,
        ),
    )
    rendered = " ".join(command)
    assert "tc qdisc replace dev eth-test root netem" in rendered
    assert "delay 12.000000ms 2.000000ms 10.000%" in rendered
    assert "loss 1.500000% 10.000%" in rendered
    assert "rate 80.000000mbit" in rendered
    assert "reorder 0.500000% 10.000%" in rendered
