"""SEC-016 teeth: the security-regression gate must FIRE on a new dangerous primitive."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "ci" / "check_security_regression.py"


def _run() -> int:
    return subprocess.run([sys.executable, str(GATE)], capture_output=True, cwd=ROOT).returncode


def test_gate_green_on_baseline():
    assert _run() == 0


def test_gate_fires_on_new_os_system(tmp_path, monkeypatch):
    # inject a new os.system site under a first-party tree, assert RED, then clean up
    probe = ROOT / "geosync" / "_sec_probe_pkg"
    probe.mkdir(exist_ok=True)
    f = probe / "evil.py"
    try:
        f.write_text("import os\ndef go():\n    os.system('echo x')\n")
        assert _run() == 1
    finally:
        f.unlink(missing_ok=True)
        probe.rmdir()
    assert _run() == 0
