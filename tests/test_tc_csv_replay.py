from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/replay/tc_csv_replay.py"
spec = spec_from_file_location("tc_csv_replay", SCRIPT)
assert spec and spec.loader
module = module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_profile_parse_and_command():
    states = module.read_csv_profile(str(ROOT / "examples/profile.example.csv"), None)
    assert len(states) == 6
    cmd = module.build_netem_cmd("eth-test", states[2])
    rendered = " ".join(cmd)
    assert "tc qdisc replace dev eth-test root netem" in rendered
    assert "delay" in cmd
    assert "loss" in cmd
    assert "rate" in cmd
