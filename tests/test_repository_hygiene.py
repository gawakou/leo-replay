from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = [re.compile(r"/home/ogawa"), re.compile(r"192\.168\.1\.2"),
             re.compile(r"192\.168\.2\.2"), re.compile(r"debug=True")]


def test_no_environment_specific_defaults_in_active_code():
    targets = [ROOT / "scripts", ROOT / "dashboard", ROOT / "config", ROOT / "labs"]
    findings = []
    for base in targets:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN:
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not findings, findings
