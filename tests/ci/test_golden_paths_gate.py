"""ENV-011 teeth: golden-path gate must FIRE on a NEW dangling `make` citation."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "ci" / "check_golden_paths.py"


def _run() -> int:
    return subprocess.run([sys.executable, str(GATE)], capture_output=True, cwd=ROOT).returncode


def test_green_on_baseline():
    assert _run() == 0


def test_fires_on_new_dangling(tmp_path):
    doc = ROOT / "docs" / "_golden_probe.md"
    try:
        doc.write_text("Run `make totally-fake-zzz-target` please.\n")
        assert _run() == 1
    finally:
        doc.unlink(missing_ok=True)
    assert _run() == 0
