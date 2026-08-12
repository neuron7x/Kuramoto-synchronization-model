"""Task 5 · CLI discoverability audit.

Every L2 analysis CLI under `scripts/run_l2_*.py` + the full-cycle
runner + the figure renderer must:

    - respond to `--help` with exit 0
    - accept `--data-dir` (where applicable) and `--output` flags
    - print a module-level docstring as `--help` header

Ensures the demo runbook is self-documenting: anyone can discover what
each script does without reading the source.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path.cwd()
_SCRIPTS = [
    "scripts/run_l2_killtest.py",
    "scripts/run_l2_attribution.py",
    "scripts/run_l2_purged_cv.py",
    "scripts/run_l2_spectral.py",
    "scripts/run_l2_hurst.py",
    "scripts/run_l2_regime_markov.py",
    "scripts/run_l2_robustness.py",
    "scripts/run_l2_transfer_entropy.py",
    "scripts/run_l2_conditional_te.py",
    "scripts/run_l2_walk_forward_summary.py",
    "scripts/run_l2_pnl.py",
    "scripts/run_l2_full_cycle.py",
    "scripts/render_l2_figures.py",
]


@pytest.mark.parametrize("script", _SCRIPTS)
def test_cli_help_exits_zero(script: str) -> None:
    path = Path(script)
    assert path.exists(), f"CLI script missing: {script}"
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(_REPO_ROOT), "PATH": ""},
        timeout=30,
    )
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}:\n{proc.stderr}"
    assert "usage:" in proc.stdout.lower(), f"{script} --help did not print usage"


@pytest.mark.parametrize(
    "script",
    [
        "scripts/run_l2_killtest.py",
        "scripts/run_l2_attribution.py",
        "scripts/run_l2_purged_cv.py",
        "scripts/run_l2_spectral.py",
        "scripts/run_l2_hurst.py",
        "scripts/run_l2_regime_markov.py",
        "scripts/run_l2_robustness.py",
        "scripts/run_l2_transfer_entropy.py",
        "scripts/run_l2_conditional_te.py",
        "scripts/run_l2_full_cycle.py",
    ],
)
def test_cli_exposes_data_dir_flag(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(_REPO_ROOT), "PATH": ""},
        timeout=30,
    )
    assert "--data-dir" in proc.stdout, f"{script} missing --data-dir flag"


@pytest.mark.parametrize(
    "script",
    [
        "scripts/run_l2_killtest.py",
        "scripts/run_l2_attribution.py",
        "scripts/run_l2_purged_cv.py",
        "scripts/run_l2_spectral.py",
        "scripts/run_l2_hurst.py",
        "scripts/run_l2_regime_markov.py",
        "scripts/run_l2_robustness.py",
        "scripts/run_l2_transfer_entropy.py",
        "scripts/run_l2_conditional_te.py",
        "scripts/run_l2_walk_forward_summary.py",
    ],
)
def test_cli_exposes_output_flag(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PYTHONPATH": str(_REPO_ROOT), "PATH": ""},
        timeout=30,
    )
    assert "--output" in proc.stdout, f"{script} missing --output flag"


@pytest.mark.parametrize("script", _SCRIPTS)
def test_cli_has_module_docstring(script: str) -> None:
    text = Path(script).read_text(encoding="utf-8")
    # Docstring starts with either """ on first code line or shortly after shebang
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[0].startswith("#!"), f"{script} missing shebang"
    doc_start = next(
        (i for i, line in enumerate(lines) if line.lstrip().startswith('"""')),
        -1,
    )
    assert doc_start != -1, f"{script} missing module docstring"
    assert doc_start <= 3, f"{script} docstring too far from top"
