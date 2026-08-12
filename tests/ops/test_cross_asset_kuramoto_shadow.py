"""T1–T4 · shadow runner contract tests."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "run_cross_asset_kuramoto_shadow.py"
SHADOW = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
DAILY = SHADOW / "daily"
SPIKE_DATA = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"

REQUIRED_DAILY_FILES = (
    "run_manifest.json",
    "signal_snapshot.csv",
    "target_weights.csv",
    "turnover.csv",
    "cost_estimate.csv",
    "realized_pnl.csv",
    "invariant_status.csv",
    "pipeline_status.csv",
    "run_log.txt",
)


def _run_runner(*extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *extra],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )


@pytest.mark.skipif(not SPIKE_DATA.is_dir(), reason="spike data required for runner")
def test_verify_only_exits_0() -> None:
    rc = _run_runner("--verify-only")
    assert rc.returncode == 0, rc.stderr


@pytest.mark.skipif(not SPIKE_DATA.is_dir(), reason="spike data required for runner")
def test_daily_run_creates_all_required_files() -> None:
    # This uses whatever the latest data snapshot gives us; if the directory
    # already exists the runner is idempotent (exit 0, no overwrite).
    rc = _run_runner()
    assert rc.returncode == 0, rc.stderr
    # latest daily dir exists and is populated
    dirs = sorted(p for p in DAILY.iterdir() if p.is_dir())
    assert dirs, "no daily directories created"
    latest = dirs[-1]
    for name in REQUIRED_DAILY_FILES:
        assert (latest / name).exists(), f"missing {name}"


@pytest.mark.skipif(not SPIKE_DATA.is_dir(), reason="spike data required for runner")
def test_daily_runner_is_idempotent() -> None:
    dirs_before = sorted(p.name for p in DAILY.iterdir() if p.is_dir())
    rc = _run_runner()
    assert rc.returncode == 0
    dirs_after = sorted(p.name for p in DAILY.iterdir() if p.is_dir())
    # No new dirs spawned, no dirs removed (append-only).
    assert dirs_after == dirs_before or (
        len(dirs_after) == len(dirs_before) + 1 and set(dirs_before).issubset(set(dirs_after))
    )


@pytest.mark.skipif(not SPIKE_DATA.is_dir(), reason="spike data required for runner")
def test_daily_runner_never_overwrites_existing_artifact(tmp_path: Path) -> None:
    """If a daily dir exists with required files, re-running must not modify them."""
    dirs = sorted(p for p in DAILY.iterdir() if p.is_dir())
    if not dirs:
        pytest.skip("no daily dir yet; skip overwrite check")
    latest = dirs[-1]
    manifest = latest / "run_manifest.json"
    assert manifest.exists()
    before = manifest.read_bytes()
    rc = _run_runner()
    assert rc.returncode == 0
    after = manifest.read_bytes()
    assert before == after, "run_manifest.json was overwritten on idempotent re-run"


def test_runner_module_imports_from_core_only() -> None:
    """AST scan: runner must not import from backtest/execution/strategies."""
    import ast

    text = RUNNER.read_text()
    tree = ast.parse(text)
    forbidden = {"backtest", "execution", "strategies"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            assert root not in forbidden, f"forbidden import from {node.module}"
        elif isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                assert root not in forbidden, f"forbidden import {a.name}"
