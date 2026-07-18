from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_has_three_segmented_services_without_privileged():
    text = (ROOT / "labs/docker-bidirectional/compose.yaml").read_text(encoding="utf-8")
    assert "client:" in text
    assert "router:" in text
    assert "server:" in text
    assert "access_net:" in text
    assert "service_net:" in text
    assert "NET_ADMIN" in text
    assert "privileged:" not in text


def test_netns_setup_uses_two_veth_pairs_and_ip_forwarding():
    text = (ROOT / "labs/netns-bidirectional/setup.sh").read_text(encoding="utf-8")
    assert text.count("type veth peer") == 2
    assert "net.ipv4.ip_forward=1" in text


def test_lab_metric_wrapper_help():
    result = subprocess.run(
        ["python3", str(ROOT / "labs/common/verify_metrics.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "fixed" in result.stdout
    assert "profile" in result.stdout


def test_virtual_testbed_documentation_exists():
    assert (ROOT / "docs/VIRTUAL_TESTBED.md").is_file()
    assert (ROOT / "labs/docker-bidirectional/README.md").is_file()
    assert (ROOT / "labs/netns-bidirectional/README.md").is_file()
