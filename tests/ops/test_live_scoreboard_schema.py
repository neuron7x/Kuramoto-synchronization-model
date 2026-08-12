"""T5, T7 · scoreboard schema + gate vocabulary enforcement."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SHADOW = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
SCOREBOARD = SHADOW / "live_scoreboard.csv"
EVAL_SCRIPT = REPO / "scripts" / "evaluate_cross_asset_kuramoto_shadow.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("shadow_eval", EVAL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_scoreboard_has_required_columns_when_present() -> None:
    if not SCOREBOARD.exists():
        pytest.skip("scoreboard not yet written")
    df = pd.read_csv(SCOREBOARD)
    expected = set(_load_module().SCOREBOARD_COLUMNS)
    assert set(df.columns) == expected


def test_scoreboard_labels_are_in_vocabulary() -> None:
    if not SCOREBOARD.exists():
        pytest.skip("scoreboard not yet written")
    mod = _load_module()
    df = pd.read_csv(SCOREBOARD)
    for label in df["status_label"].astype(str):
        assert label in mod.STATUS_VOCAB, f"status_label {label!r} not in vocab"
    for gate in df["gate_decision"].astype(str):
        assert gate in mod.GATE_VOCAB, f"gate_decision {gate!r} not in vocab"


def test_scoreboard_appends_not_overwrites() -> None:
    if not SCOREBOARD.exists():
        pytest.skip("scoreboard not yet written")
    df_before = pd.read_csv(SCOREBOARD)
    import subprocess

    rc = subprocess.run([sys.executable, str(EVAL_SCRIPT)], cwd=str(REPO), capture_output=True)
    assert rc.returncode == 0
    df_after = pd.read_csv(SCOREBOARD)
    assert (
        len(df_after) == len(df_before) + 1
    ), f"expected one appended row, got {len(df_after) - len(df_before)}"


def test_gate_engine_emits_only_allowed_combinations() -> None:
    mod = _load_module()
    # Sweep synthetic scenarios
    cases = [
        # (bars, env_pos, op_unsafe, inv_fail, streak, dd_live, expected_status, expected_gate)
        (0, "n/a", False, False, 0, 0.0, "BUILDING_SAMPLE", "CONTINUE_SHADOW"),
        (25, "p25_p75", False, False, 0, 0.05, "WITHIN_EXPECTATION", "CONTINUE_SHADOW"),
        (25, "p05_p25", False, False, 0, 0.05, "UNDERWATCH", "CONTINUE_SHADOW"),
        (25, "below_p05", False, False, 21, 0.05, "OUTSIDE_EXPECTATION", "ESCALATE_REVIEW"),
        (65, "below_p05", False, False, 21, 0.05, "OUTSIDE_EXPECTATION", "NO_DEPLOY"),
        (
            90,
            "p25_p75",
            False,
            False,
            0,
            0.05,
            "WITHIN_EXPECTATION",
            "DEPLOYMENT_CANDIDATE_PENDING_OWNER",
        ),
        (25, "p25_p75", True, False, 0, 0.05, "OPERATIONALLY_UNSAFE", "ESCALATE_REVIEW"),
        (25, "p25_p75", False, True, 0, 0.05, "OPERATIONALLY_UNSAFE", "ESCALATE_REVIEW"),
        (25, "p25_p75", False, False, 0, 0.30, "OUTSIDE_EXPECTATION", "ESCALATE_REVIEW"),
    ]
    for bars, env_pos, op, inv, streak, dd, exp_s, exp_g in cases:
        metrics = {"max_dd_live": dd, "sharpe_live": 1.0}
        status, gate = mod._decide_status_and_gate(bars, metrics, env_pos, op, inv, streak)
        assert status == exp_s, f"case bars={bars} env={env_pos} op={op}: got {status}"
        assert gate == exp_g, f"case bars={bars} env={env_pos} op={op}: got {gate}"
        assert status in mod.STATUS_VOCAB
        assert gate in mod.GATE_VOCAB
