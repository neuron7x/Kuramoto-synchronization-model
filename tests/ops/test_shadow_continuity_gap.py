"""Continuity gate · the shadow evaluator must detect missing-bar gaps,
log them as ``gap_detected`` incidents (idempotently), and fail the
deployment gate closed when the validation sample is discontinuous.

Bars are business-day-clocked, so weekends are never gaps; a single
missing business day is a probable holiday (WARNING); two or more dropped
business days are a continuity breach (CRITICAL) — the failure mode a
power/network outage during the 22:00 UTC run window produces.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"
RUNNER_SCRIPT = REPO / "scripts" / "run_cross_asset_kuramoto_shadow.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def evaluator():
    return _load("shadow_eval_continuity", EVAL_SCRIPT)


def _ledger(dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates)})


# --- gap detection ---------------------------------------------------- #


def test_consecutive_business_days_have_no_gap(evaluator) -> None:
    # 2026-06-17 Wed, 18 Thu, 19 Fri — fully consecutive trading days.
    gaps = evaluator._detect_ledger_gaps(_ledger(["2026-06-17", "2026-06-18", "2026-06-19"]))
    assert gaps == []


def test_weekend_is_not_a_gap(evaluator) -> None:
    # Fri 2026-06-19 -> Mon 2026-06-22: the weekend must not register.
    gaps = evaluator._detect_ledger_gaps(_ledger(["2026-06-19", "2026-06-22"]))
    assert gaps == []


def test_single_missing_business_day_is_warning(evaluator) -> None:
    # Wed 2026-06-17 -> Fri 2026-06-19 drops Thu: one business day → holiday-grade WARNING.
    gaps = evaluator._detect_ledger_gaps(_ledger(["2026-06-17", "2026-06-19"]))
    assert len(gaps) == 1
    assert gaps[0]["missing_bdays"] == 1
    assert gaps[0]["severity"] == "WARNING"


def test_multiple_missing_business_days_are_critical(evaluator) -> None:
    # Tue 2026-06-16 -> Fri 2026-06-19 drops Wed+Thu: two business days → CRITICAL.
    gaps = evaluator._detect_ledger_gaps(_ledger(["2026-06-16", "2026-06-19"]))
    assert len(gaps) == 1
    assert gaps[0]["missing_bdays"] == 2
    assert gaps[0]["severity"] == "CRITICAL"


def test_continuity_summary_flags_breach_only_on_critical(evaluator) -> None:
    clean = evaluator._continuity_summary(_ledger(["2026-06-17", "2026-06-18", "2026-06-19"]))
    assert clean["continuity_breach"] is False
    assert clean["total_missing_bdays"] == 0

    holiday = evaluator._continuity_summary(_ledger(["2026-06-17", "2026-06-19"]))
    assert holiday["continuity_breach"] is False
    assert holiday["n_gaps"] == 1
    assert holiday["max_gap_bdays"] == 1

    outage = evaluator._continuity_summary(_ledger(["2026-06-16", "2026-06-19"]))
    assert outage["continuity_breach"] is True
    assert outage["n_critical_gaps"] == 1
    assert outage["max_gap_bdays"] == 2


def test_empty_or_single_row_ledger_is_quiet(evaluator) -> None:
    assert evaluator._detect_ledger_gaps(pd.DataFrame()) == []
    assert evaluator._detect_ledger_gaps(_ledger(["2026-06-19"])) == []


# --- gate fail-closed ------------------------------------------------- #


def test_gate_fails_closed_on_continuity_breach(evaluator) -> None:
    metrics = {"max_dd_live": 0.05, "sharpe_live": 1.2}
    # Without a breach this exact state is a deploy candidate at 90 bars.
    status, gate = evaluator._decide_status_and_gate(
        bars=90,
        metrics=metrics,
        env_pos="p25_p75",
        op_unsafe=False,
        inv_fail=False,
        sub_p05_streak=0,
        continuity_breach=False,
    )
    assert (status, gate) == ("WITHIN_EXPECTATION", "DEPLOYMENT_CANDIDATE_PENDING_OWNER")

    # A continuity breach must override that to a hard no-deploy.
    status_b, gate_b = evaluator._decide_status_and_gate(
        bars=90,
        metrics=metrics,
        env_pos="p25_p75",
        op_unsafe=False,
        inv_fail=False,
        sub_p05_streak=0,
        continuity_breach=True,
    )
    assert status_b == "OPERATIONALLY_UNSAFE"
    assert gate_b == "NO_DEPLOY"
    assert gate_b != "DEPLOYMENT_CANDIDATE_PENDING_OWNER"


# --- incident logging ------------------------------------------------- #


def test_gap_incident_logged_and_idempotent(evaluator, tmp_path, monkeypatch) -> None:
    fake = tmp_path / "operational_incidents.csv"
    monkeypatch.setattr(evaluator, "OPS_INCIDENTS", fake)
    outage = _ledger(["2026-06-16", "2026-06-19"])

    assert evaluator._log_ledger_gaps(outage) == 1
    df = pd.read_csv(fake)
    assert len(df) == 1
    assert set(df.columns) == set(evaluator.OPS_INCIDENT_COLUMNS)
    assert df.iloc[0]["incident_type"] == "gap_detected"
    assert df.iloc[0]["severity"] == "CRITICAL"

    # Second pass on the same ledger logs nothing — append-only stays stable.
    assert evaluator._log_ledger_gaps(outage) == 0
    assert len(pd.read_csv(fake)) == 1


def test_clean_ledger_logs_no_incident(evaluator, tmp_path, monkeypatch) -> None:
    fake = tmp_path / "operational_incidents.csv"
    monkeypatch.setattr(evaluator, "OPS_INCIDENTS", fake)
    clean = _ledger(["2026-06-17", "2026-06-18", "2026-06-19"])
    assert evaluator._log_ledger_gaps(clean) == 0
    assert not fake.exists()


# --- schema drift guard ----------------------------------------------- #


def test_incident_schema_matches_runner(evaluator) -> None:
    runner = _load("shadow_runner_continuity", RUNNER_SCRIPT)
    assert tuple(evaluator.OPS_INCIDENT_COLUMNS) == tuple(runner.INCIDENT_COLUMNS)
