"""Flat-schema headline metrics consolidation.

Downstream tooling (dashboards, warehouses, external review) needs one
ingestion-friendly JSON file with every key number from the 10-axis +
5-ablation/stress stack — not 16 variable-structure artifacts.

This module reads the existing results/L2_*.json files and emits a
single flat dictionary with snake_case keys. Every top-level key is
primitive (float / int / str / bool) — no nested structures, no lists.
Consumers can dump it into a tabular row without parsing.

Schema stability: keys present here are a promise to downstream; adding
is fine, removing breaks the contract (enforced by schema-registry
test). Use `None` when an artifact is absent rather than omitting the
key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _safe_float(payload: dict[str, Any] | None, *keys: str) -> float | None:
    """Navigate nested dict by keys; return float or None on missing."""
    if payload is None:
        return None
    cur: Any = payload
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if cur is None:
        return None
    try:
        return float(cur)
    except (TypeError, ValueError):
        return None


def _safe_str(payload: dict[str, Any] | None, *keys: str) -> str | None:
    if payload is None:
        return None
    cur: Any = payload
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if cur is None:
        return None
    return str(cur)


def _safe_int(payload: dict[str, Any] | None, *keys: str) -> int | None:
    if payload is None:
        return None
    cur: Any = payload
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if cur is None:
        return None
    try:
        return int(cur)
    except (TypeError, ValueError):
        return None


def build_headline_metrics(results_dir: Path) -> dict[str, Any]:
    """Collect every key number into one flat primitive-valued dict."""
    killtest = _load(results_dir / "L2_KILLTEST_VERDICT.json")
    robustness = _load(results_dir / "L2_ROBUSTNESS.json")
    cv = _load(results_dir / "L2_PURGED_CV.json")
    spectral = _load(results_dir / "L2_SPECTRAL.json")
    hurst = _load(results_dir / "L2_HURST.json")
    te = _load(results_dir / "L2_TRANSFER_ENTROPY.json")
    cte = _load(results_dir / "L2_CONDITIONAL_TE.json")
    wf = _load(results_dir / "L2_WALK_FORWARD_SUMMARY.json")
    cond = _load(results_dir / "L2_REGIME_CONDITIONAL_IC.json")
    hyperparam = _load(results_dir / "L2_ABLATION_SENSITIVITY.json")
    symbol = _load(results_dir / "L2_SYMBOL_ABLATION.json")
    hold = _load(results_dir / "L2_HOLD_ABLATION.json")
    slippage = _load(results_dir / "L2_SLIPPAGE_STRESS.json")
    fee = _load(results_dir / "L2_FEE_STRESS.json")

    # Bracket rows in cond artifact: find HIGH_VOL / LOW_VOL cells
    def _regime_ic(name: str) -> float | None:
        if cond is None:
            return None
        for cell in cond.get("cells", []):
            if cell.get("regime") == name:
                val = cell.get("ic")
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return None
        return None

    out: dict[str, Any] = {
        # --- Kill test -----------------------------------------------------
        "kill_test_verdict": _safe_str(killtest, "verdict"),
        "ic_pooled": _safe_float(killtest, "ic_signal"),
        "ic_residual": _safe_float(killtest, "residual_ic"),
        "residual_p_value": _safe_float(killtest, "residual_ic_pvalue"),
        "n_rows": _safe_int(killtest, "n_samples"),
        "n_symbols": _safe_int(killtest, "n_symbols"),
        # --- Bootstrap CI --------------------------------------------------
        "bootstrap_ci_lo_95": _safe_float(robustness, "bootstrap", "ci_lo_95"),
        "bootstrap_ci_hi_95": _safe_float(robustness, "bootstrap", "ci_hi_95"),
        "bootstrap_significant_at_95": (
            robustness["bootstrap"]["significant_at_95"]
            if robustness is not None and "bootstrap" in robustness
            else None
        ),
        # --- Deflated Sharpe ----------------------------------------------
        "deflated_sharpe": _safe_float(robustness, "deflated_sharpe", "deflated_sharpe"),
        "probability_sharpe_is_real": _safe_float(
            robustness, "deflated_sharpe", "probability_sharpe_is_real"
        ),
        # --- Purged K-fold CV ---------------------------------------------
        "purged_cv_mean_ic": _safe_float(cv, "ic_mean"),
        "purged_cv_median_ic": _safe_float(cv, "ic_median"),
        "purged_cv_n_folds": _safe_int(cv, "k"),
        # --- Mutual information -------------------------------------------
        "mutual_information_nats": _safe_float(
            robustness, "mutual_information", "mutual_information_nats"
        ),
        "mutual_information_bits": _safe_float(
            robustness, "mutual_information", "mutual_information_bits"
        ),
        # --- Spectral ------------------------------------------------------
        "spectral_beta": _safe_float(spectral, "redness_slope_beta"),
        "spectral_regime_verdict": _safe_str(spectral, "regime_verdict"),
        "spectral_dominant_period_sec": _safe_float(spectral, "dominant_period_sec"),
        # --- DFA Hurst ----------------------------------------------------
        "hurst_exponent": _safe_float(hurst, "report", "hurst_exponent"),
        "hurst_r_squared": _safe_float(hurst, "report", "r_squared"),
        "hurst_verdict": _safe_str(hurst, "report", "verdict"),
        # --- Transfer entropy ---------------------------------------------
        "te_bidirectional_count": (
            int(te["verdict_counts"].get("BIDIRECTIONAL", 0))
            if te is not None and "verdict_counts" in te
            else None
        ),
        "te_n_pairs": _safe_int(te, "n_pairs"),
        # --- Conditional TE -----------------------------------------------
        "cte_private_flow_count": (
            int(cte["verdict_counts"].get("PRIVATE_FLOW", 0))
            if cte is not None and "verdict_counts" in cte
            else None
        ),
        "cte_n_pairs": _safe_int(cte, "n_pairs"),
        "cte_conditioner": _safe_str(cte, "conditioner"),
        # --- Walk-forward -------------------------------------------------
        "walk_forward_verdict": _safe_str(wf, "verdict"),
        "walk_forward_fraction_positive": _safe_float(wf, "fraction_positive"),
        "walk_forward_ic_median": _safe_float(wf, "ic_median"),
        "walk_forward_ic_std": _safe_float(wf, "ic_std"),
        # --- Regime-conditional IC ----------------------------------------
        "regime_conditional_verdict": _safe_str(cond, "verdict"),
        "regime_conditional_ratio_high_over_low": _safe_float(cond, "abs_ratio_high_over_low"),
        "ic_high_vol": _regime_ic("HIGH_VOL"),
        "ic_low_vol": _regime_ic("LOW_VOL"),
        # --- Ablation verdicts --------------------------------------------
        "ablation_hyperparam_verdict": _safe_str(hyperparam, "verdict"),
        "ablation_hyperparam_max_rel_drift": _safe_float(hyperparam, "max_relative_drift"),
        "ablation_symbol_verdict": _safe_str(symbol, "verdict"),
        "ablation_symbol_min_ic": _safe_float(symbol, "min_ic"),
        "ablation_hold_verdict": _safe_str(hold, "verdict"),
        "ablation_slippage_verdict": _safe_str(slippage, "verdict"),
        "ablation_slippage_max_viable_bp": _safe_float(slippage, "max_slippage_still_viable_bp"),
        "ablation_fee_verdict": _safe_str(fee, "verdict"),
        "ablation_fee_max_viable_bp": _safe_float(fee, "max_viable_taker_fee_bp"),
    }
    return out


def write_headline_metrics(results_dir: Path, output_path: Path) -> Path:
    metrics = build_headline_metrics(results_dir)
    body = json.dumps(metrics, indent=2, sort_keys=True, default=str) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body, encoding="utf-8")
    return output_path
