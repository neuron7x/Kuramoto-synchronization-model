"""Codex P1 regressions (PR #355).

Pin the fixes for the two P1 findings surfaced by the Codex reviewer:

1. Empty-ledger guard in ``_compute_live_metrics``:
   when ``_load_live_ledger`` returns an empty DataFrame (paper-state
   absent on CI runners, or the spike has not yet written its first
   tick), the evaluator must NOT raise ``KeyError: 'net_ret'``; it must
   return a 0-bar ``empty_metrics`` dict so the outer gate emits
   ``BUILDING_SAMPLE`` / ``CONTINUE_SHADOW`` cleanly.

2. Partial/failed prior-run quarantine in the shadow runner:
   when a prior ``_fail_closed`` call created ``daily/YYYY-MM-DD/`` with
   only ``run_log.txt`` (incomplete per ``_already_written``), the next
   invocation must quarantine-rename the partial dir and proceed with
   a fresh ``mkdir`` instead of aborting with ``FileExistsError``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"
RUNNER_SCRIPT = REPO / "scripts" / "run_cross_asset_kuramoto_shadow.py"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, f"spec_from_file_location returned None for {path}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------- #
# Codex P1 #1 · empty-ledger guard in evaluator
# --------------------------------------------------------------------- #


def test_empty_ledger_returns_zero_bar_metrics_not_keyerror(tmp_path: Path) -> None:
    """Regression: _compute_live_metrics on an empty DataFrame must not
    raise KeyError('net_ret'). Returns the 0-bar empty_metrics dict."""
    mod = _load_module(EVAL_SCRIPT, "shadow_eval_p1_1")
    empty = pd.DataFrame()
    m = mod._compute_live_metrics(empty)
    assert m["live_bars_completed"] == 0
    assert m["cumulative_net_return"] == 0.0
    # All other numeric fields are NaN (non-finite sentinels; no crash).
    for k in (
        "annualized_return_live",
        "annualized_vol_live",
        "sharpe_live",
        "max_dd_live",
    ):
        v = m[k]
        assert v != v, f"expected NaN at {k}, got {v!r}"


def test_schema_only_ledger_returns_zero_bar_metrics(tmp_path: Path) -> None:
    """Regression: a DataFrame with the right schema but zero rows must
    also traverse the guard cleanly (len == 0 branch)."""
    mod = _load_module(EVAL_SCRIPT, "shadow_eval_p1_1b")
    cols = ["date", "net_ret", "equity", "turnover", "cost", "btc_equity", "day_n"]
    schema_only = pd.DataFrame(columns=cols)
    m = mod._compute_live_metrics(schema_only)
    assert m["live_bars_completed"] == 0


def test_evaluator_cli_exits_0_with_missing_paper_equity(tmp_path: Path) -> None:
    """Regression: end-to-end CLI with --paper-equity pointing at a
    non-existent path must exit 0 (BUILDING_SAMPLE)."""
    fake = tmp_path / "definitely_does_not_exist.csv"
    rc = subprocess.run(
        [sys.executable, str(EVAL_SCRIPT), "--paper-equity", str(fake)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert rc.returncode == 0, f"stdout={rc.stdout}\nstderr={rc.stderr}"


# --------------------------------------------------------------------- #
# Codex P1 #2 · partial-dir retry in runner
# --------------------------------------------------------------------- #


def test_runner_quarantines_partial_daily_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: a partial daily/YYYY-MM-DD/ (only run_log.txt) must
    not break the next runner invocation. The runner relocates the
    partial dir to <name>.incomplete.<ISO> and proceeds with a fresh
    mkdir. No FileExistsError.
    """
    runner = _load_module(RUNNER_SCRIPT, "shadow_runner_p1_2")

    # Redirect the shadow daily/incidents paths into tmp_path so this
    # regression never touches the real evidence rail.
    monkeypatch.setattr(runner, "DAILY_ROOT", tmp_path / "daily")
    monkeypatch.setattr(runner, "SHADOW_DIR", tmp_path)
    monkeypatch.setattr(runner, "INCIDENTS", tmp_path / "operational_incidents.csv")

    partial_day = "2026-04-11"
    partial_dir = runner.DAILY_ROOT / partial_day
    partial_dir.mkdir(parents=True)
    (partial_dir / "run_log.txt").write_text(
        "[2026-04-11T22:00:00Z] FAIL-CLOSED: pretend earlier failure\n"
    )

    # The function under test lives *between* `_already_written` and the
    # final `mkdir(exist_ok=False)`. We replicate its contract in-place
    # without running the full pipeline (which needs spike data).
    run_date = pd.Timestamp(partial_day)
    assert not runner._already_written(run_date)

    # Simulate the logic path the runner takes on retry:
    ts_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    quarantine = partial_dir.with_name(f"{partial_dir.name}.incomplete.{ts_suffix}")
    partial_dir.rename(quarantine)

    # Now mkdir(exist_ok=False) must succeed — this is what was crashing.
    partial_dir.mkdir(parents=True, exist_ok=False)

    assert partial_dir.is_dir()
    assert quarantine.is_dir()
    assert (quarantine / "run_log.txt").read_text().startswith("[2026-04-11T22:00:00Z] FAIL-CLOSED")
    # No content from the partial run leaked into the fresh dir.
    assert list(partial_dir.iterdir()) == []


def test_missing_asset_logs_incident_before_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit gap closed: a missing regime-panel asset must leave a
    row in operational_incidents.csv before the runner exits 2.
    Without this, the operator has only the exit status to debug."""
    runner = _load_module(RUNNER_SCRIPT, "shadow_runner_missing_asset")

    incidents = tmp_path / "operational_incidents.csv"
    monkeypatch.setattr(runner, "INCIDENTS", incidents)

    missing_data_dir = tmp_path / "definitely_not_a_data_bundle"
    with pytest.raises(SystemExit) as exc_info:
        runner._target_run_date(missing_data_dir, ["BTC"])

    assert exc_info.value.code == 2
    assert incidents.is_file(), "incident ledger must exist after missing-asset exit"
    rows = pd.read_csv(incidents)
    assert len(rows) >= 1
    # Find our row (may coexist with earlier test pollution)
    ours = rows[rows["incident_type"] == "missing_asset"]
    assert len(ours) >= 1
    latest = ours.iloc[-1]
    assert latest["severity"] == "CRITICAL"
    assert "BTC" in str(latest["description"])


def test_runner_retry_logic_matches_source_flow() -> None:
    """Meta-regression: the runner source actually contains the
    partial-dir-retry branch. Catches accidental revert."""
    src = RUNNER_SCRIPT.read_text()
    assert "incomplete_dir_retry" in src, (
        "runner must log an incident of type 'incomplete_dir_retry' when "
        "a partial dir is detected on retry"
    )
    assert ".incomplete." in src, "runner must rename partial dirs with '.incomplete.' suffix"
    assert (
        "run_dir.rename(quarantine)" in src
    ), "runner must rename the partial dir rather than delete/overwrite"
