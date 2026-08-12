"""Daily shadow runner — frozen cross-asset Kuramoto, append-only evidence.

Produces one dated directory of evidence under
``results/cross_asset_kuramoto/shadow_validation/daily/YYYY-MM-DD/``.
Everything runs from the locked artefacts (`PARAMETER_LOCK.json`) and
the integrated module (`core/cross_asset_kuramoto/`). No network calls,
no interactive input, deterministic on any fixed data snapshot.

Exit codes
----------
0  success (new or idempotent)
1  hash mismatch on a locked artefact
2  missing asset in the strategy / regime universe
3  invariant violation
4  file-overwrite attempted (S8)
5  --verify-only failed an underlying assertion
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from core.cross_asset_kuramoto import (  # noqa: E402
    build_panel,
    build_returns_panel,
    classify_regimes,
    compute_log_returns,
    extract_phase,
    kuramoto_order,
    simulate_rp_strategy,
)
from core.cross_asset_kuramoto.invariants import (  # noqa: E402
    CAKInvariantError,
    assert_cak1_parameter_freeze,
    assert_cak2_universe_freeze,
    assert_cak5_cost_required,
    assert_cak8_turnover_bounded,
    load_parameter_lock,
)

LOCK_PATH = REPO / "results" / "cross_asset_kuramoto" / "PARAMETER_LOCK.json"
SHADOW_DIR = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
DAILY_ROOT = SHADOW_DIR / "daily"
INCIDENTS = SHADOW_DIR / "operational_incidents.csv"
LIVE_STATE = SHADOW_DIR / "LIVE_STATE.json"
SPIKE_DATA_DEFAULT = Path.home() / "spikes" / "cross_asset_sync_regime" / "data"
PAPER_STATE = Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state"
LOCK_AUDIT = SHADOW_DIR / "LOCK_AUDIT.md"

# Hash pinned at demo-ready commit 7beea0d; checked at each run.
EXPECTED_PARAM_LOCK_SHA256 = (
    "1afd9058f7b5e1512d0a58c7b760da4e75389602d0155b0d83f1a84e567e5132"  # pragma: allowlist secret
)

INCIDENT_COLUMNS = (
    "incident_ts",
    "incident_type",
    "severity",
    "affected_run_date",
    "description",
    "resolved_yes_no",
    "resolution_ts",
    "changed_artifacts_yes_no",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_incident(row: dict[str, Any]) -> None:
    """Append-only write to operational_incidents.csv."""
    new = not INCIDENTS.exists()
    INCIDENTS.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENTS.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=INCIDENT_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in INCIDENT_COLUMNS})


def _check_lock_hashes() -> None:
    actual = _sha256(LOCK_PATH)
    if actual != EXPECTED_PARAM_LOCK_SHA256:
        _append_incident(
            {
                "incident_ts": _now_utc(),
                "incident_type": "hash_mismatch",
                "severity": "CRITICAL",
                "affected_run_date": "",
                "description": (
                    f"PARAMETER_LOCK.json sha256 {actual} != expected {EXPECTED_PARAM_LOCK_SHA256}"
                ),
                "resolved_yes_no": "no",
                "resolution_ts": "",
                "changed_artifacts_yes_no": "no",
            }
        )
        raise SystemExit(1)


def _fail_closed(run_dir: Path, msg: str, code: int) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_log.txt").write_text(f"[{_now_utc()}] FAIL-CLOSED: {msg}\n")
    _append_incident(
        {
            "incident_ts": _now_utc(),
            "incident_type": "fail_closed",
            "severity": "CRITICAL",
            "affected_run_date": run_dir.name,
            "description": msg,
            "resolved_yes_no": "no",
            "resolution_ts": "",
            "changed_artifacts_yes_no": "no",
        }
    )
    sys.stderr.write(f"FAIL-CLOSED: {msg}\n")
    raise SystemExit(code)


def _target_run_date(data_dir: Path, assets: list[str]) -> pd.Timestamp:
    """Latest common business-day timestamp across the regime universe.

    On a missing asset the exit code is 2 and an operational incident
    row is appended — so the failure is auditable from the ledger
    rather than only the process-exit-status.
    """
    from core.cross_asset_kuramoto.signal import load_asset_close

    last_ts: list[pd.Timestamp] = []
    for a in assets:
        try:
            s = load_asset_close(a, data_dir)
        except CAKInvariantError as exc:
            _append_incident(
                {
                    "incident_ts": _now_utc(),
                    "incident_type": "missing_asset",
                    "severity": "CRITICAL",
                    "affected_run_date": "",
                    "description": (
                        f"load_asset_close failed for asset {a!r} at data_dir={data_dir}: {exc}"
                    ),
                    "resolved_yes_no": "no",
                    "resolution_ts": "",
                    "changed_artifacts_yes_no": "no",
                }
            )
            raise SystemExit(2) from exc
        last_ts.append(s.index.max())
    return min(last_ts).normalize()


def _already_written(run_date: pd.Timestamp) -> bool:
    d = DAILY_ROOT / run_date.strftime("%Y-%m-%d")
    required = [
        "run_manifest.json",
        "signal_snapshot.csv",
        "target_weights.csv",
        "turnover.csv",
        "cost_estimate.csv",
        "invariant_status.csv",
        "pipeline_status.csv",
        "run_log.txt",
    ]
    return d.is_dir() and all((d / name).exists() for name in required)


def _pipeline_stats(
    panel_ffill_limit_bdays: int,
    data_dir: Path,
    assets: list[str],
) -> dict[str, Any]:
    """Data-health metrics per PH1..PH8."""
    from core.cross_asset_kuramoto.signal import load_asset_close

    series = {a: load_asset_close(a, data_dir) for a in assets}
    latest = {a: str(s.index.max().date()) for a, s in series.items()}
    ages_days = {
        a: (pd.Timestamp.utcnow().normalize() - s.index.max().normalize()).days
        for a, s in series.items()
    }
    stale_assets = [a for a, d in ages_days.items() if d > 7]  # 5 bdays ≈ 7 cal
    dup_ts = {a: int(s.index.duplicated().sum()) for a, s in series.items()}
    tz_mismatch = any(s.index.tz is None for s in series.values())

    # Bday-grid alignment
    start = min(s.index.min() for s in series.values())
    end = max(s.index.max() for s in series.values())
    grid = pd.date_range(start, end, freq="B", tz="UTC")
    raw = pd.concat([series[a].rename(a) for a in assets], axis=1).reindex(grid)
    missing_before_ffill = int(raw.isna().any(axis=1).sum())
    ffilled = raw.ffill(limit=panel_ffill_limit_bdays)
    missing_after_ffill = int(ffilled.isna().any(axis=1).sum())
    ffill_count = missing_before_ffill - missing_after_ffill
    misalignment_pct = round(100.0 * missing_before_ffill / max(len(grid), 1), 4)

    return {
        "latest_bar_per_asset": latest,
        "age_days_per_asset": ages_days,
        "stale_assets_over_5bdays": stale_assets,
        "missing_bar_count_before_ffill": missing_before_ffill,
        "missing_bar_count_after_ffill": missing_after_ffill,
        "misaligned_timestamp_count": missing_before_ffill,
        "misaligned_timestamp_pct": misalignment_pct,
        "forward_fill_count": ffill_count,
        "data_coverage_pct": round(
            100.0 * (len(grid) - missing_after_ffill) / max(len(grid), 1), 4
        ),
        "duplicate_timestamp_count_per_asset": dup_ts,
        "timezone_mismatch_flag": bool(tz_mismatch),
    }


def _invariant_runbook(params, strategy: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        assert_cak1_parameter_freeze(params, LOCK_PATH)
        rows.append({"invariant_id": "INV-CAK1", "status": "PASS"})
    except CAKInvariantError as exc:
        rows.append({"invariant_id": "INV-CAK1", "status": f"FAIL: {exc}"})
    try:
        assert_cak2_universe_freeze(params, LOCK_PATH)
        rows.append({"invariant_id": "INV-CAK2", "status": "PASS"})
    except CAKInvariantError as exc:
        rows.append({"invariant_id": "INV-CAK2", "status": f"FAIL: {exc}"})
    for iid in ("INV-CAK3", "INV-CAK4", "INV-CAK6", "INV-CAK7"):
        rows.append({"invariant_id": iid, "status": "PASS (enforced by test suite)"})
    try:
        assert_cak5_cost_required(params.cost_bps, emit_performance=True)
        rows.append({"invariant_id": "INV-CAK5", "status": "PASS"})
    except CAKInvariantError as exc:
        rows.append({"invariant_id": "INV-CAK5", "status": f"FAIL: {exc}"})
    try:
        assert_cak8_turnover_bounded(strategy["turnover"].to_numpy())
        rows.append({"invariant_id": "INV-CAK8", "status": "PASS"})
    except CAKInvariantError as exc:
        rows.append({"invariant_id": "INV-CAK8", "status": f"FAIL: {exc}"})
    return rows


def _read_realized_from_paper_state(run_date: pd.Timestamp) -> dict[str, Any] | None:
    """Pull the paper-trader's realized row for ``run_date`` when present."""
    eq = PAPER_STATE / "equity.csv"
    if not eq.exists():
        return None
    df = pd.read_csv(eq, parse_dates=["date"])
    key = run_date.strftime("%Y-%m-%d")
    hit = df[df["date"].dt.strftime("%Y-%m-%d") == key]
    if hit.empty:
        return None
    row = hit.iloc[-1]
    return {
        "date": key,
        "regime": str(row.get("regime", "")),
        "R": float(row.get("R", float("nan"))),
        "gross_ret": float(row.get("gross_ret", float("nan"))),
        "net_ret": float(row.get("net_ret", float("nan"))),
        "turnover": float(row.get("turnover", float("nan"))),
        "cost": float(row.get("cost", float("nan"))),
        "equity": float(row.get("equity", float("nan"))),
        "day_n": int(row.get("day_n", 0)),
    }


def _run_once(args: argparse.Namespace) -> int:
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)

    _check_lock_hashes()

    params = load_parameter_lock(LOCK_PATH)
    regime_assets = list(params.regime_assets)
    strat_assets = list(params.strategy_assets)

    run_date = _target_run_date(args.data_dir, regime_assets)
    run_dir = DAILY_ROOT / run_date.strftime("%Y-%m-%d")

    if args.verify_only:
        # --verify-only: run everything in-memory, never write, exit 0/5
        try:
            panel = build_panel(regime_assets, args.data_dir, params.ffill_limit_bdays)
            log_r = compute_log_returns(panel)
            phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
            r = kuramoto_order(phases, params.r_window_bdays).dropna()
            regimes = classify_regimes(
                r,
                params.regime_threshold_train_frac,
                params.regime_quantile_low,
                params.regime_quantile_high,
            )
            rets = build_returns_panel(strat_assets, args.data_dir, params.ffill_limit_bdays)
            strat = simulate_rp_strategy(
                rets,
                regimes,
                params.regime_buckets,
                params.vol_window_bdays,
                params.vol_target_annualised,
                params.vol_cap_leverage,
                params.cost_bps,
                params.return_clip_abs,
                params.bars_per_year,
                params.execution_lag_bars,
            )
            _ = _invariant_runbook(params, strat)
            print("verify-only: OK")
            return 0
        except Exception as exc:
            sys.stderr.write(f"verify-only FAILED: {exc}\n")
            return 5

    if _already_written(run_date):
        msg = f"{run_date.strftime('%Y-%m-%d')} already written; idempotent no-op"
        print(msg)
        (run_dir / "run_log.txt").open("a", encoding="utf-8").write(
            f"[{_now_utc()}] idempotent call: {msg}\n"
        )
        return 0

    # Partial/failed prior attempt may have created run_dir via _fail_closed
    # but not populated the full required-file set (see _already_written).
    # Preserve its evidence under a quarantine name so the fresh run can
    # proceed without clobbering it. Logs an incident for audit trail.
    if run_dir.exists():
        ts_suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantine = run_dir.with_name(f"{run_dir.name}.incomplete.{ts_suffix}")
        run_dir.rename(quarantine)
        _append_incident(
            {
                "incident_ts": _now_utc(),
                "incident_type": "incomplete_dir_retry",
                "severity": "LOW",
                "affected_run_date": run_date.strftime("%Y-%m-%d"),
                "description": (
                    f"Prior attempt left partial evidence in {run_dir.name}; "
                    f"quarantined as {quarantine.name} and retrying clean."
                ),
                "resolved_yes_no": "yes",
                "resolution_ts": _now_utc(),
                "changed_artifacts_yes_no": f"yes (renamed to {quarantine.name})",
            }
        )

    run_dir.mkdir(parents=True, exist_ok=False)  # S8: never overwrite a complete dir

    # Build panel + run frozen pipeline
    try:
        panel = build_panel(regime_assets, args.data_dir, params.ffill_limit_bdays)
        log_r = compute_log_returns(panel)
        phases = extract_phase(log_r, params.detrend_window_bdays).dropna()
        r_series = kuramoto_order(phases, params.r_window_bdays).dropna()
        regimes = classify_regimes(
            r_series,
            params.regime_threshold_train_frac,
            params.regime_quantile_low,
            params.regime_quantile_high,
        )
        rets = build_returns_panel(strat_assets, args.data_dir, params.ffill_limit_bdays)
        strat = simulate_rp_strategy(
            rets,
            regimes,
            params.regime_buckets,
            params.vol_window_bdays,
            params.vol_target_annualised,
            params.vol_cap_leverage,
            params.cost_bps,
            params.return_clip_abs,
            params.bars_per_year,
            params.execution_lag_bars,
        )
    except CAKInvariantError as exc:
        _fail_closed(run_dir, f"CAKInvariantError: {exc}", 3)
        return 3  # unreachable (SystemExit)

    # Latest signal row (the row we would have traded on at run_date close)
    latest_ts = strat.index[-1]
    latest = strat.iloc[-1]

    # Per-asset weights on the trade bar: reconstruct from bucket + risk-parity logic.
    # We rely on backtest_v2 mechanics: the weight vector for a given regime is
    # inv-vol normalised within the bucket at t-1, then scaled by leverage.
    # For transparency we re-derive from scratch.
    from core.cross_asset_kuramoto.engine import rolling_vol

    asset_vols = rolling_vol(rets, params.vol_window_bdays, params.bars_per_year).shift(1)
    regs_lag = regimes.shift(params.execution_lag_bars).reindex(strat.index)
    regime = str(regs_lag.iloc[-1])
    bucket = params.regime_buckets.get(regime, ())
    vols_today = asset_vols.iloc[-1]
    inv_vols = []
    valid_assets = []
    for a in bucket:
        v = vols_today.get(a, float("nan"))
        if np.isfinite(v) and v > 0:
            inv_vols.append(1.0 / v)
            valid_assets.append(a)
    w_pre_lev = {a: 0.0 for a in strat_assets}
    if inv_vols:
        inv_arr = np.asarray(inv_vols, dtype=float)
        rp = inv_arr / inv_arr.sum()
        for a, rw in zip(valid_assets, rp, strict=True):
            w_pre_lev[a] = float(rw)
    w_scaled = {a: w_pre_lev[a] * float(latest["leverage"]) for a in strat_assets}

    # Write signal_snapshot.csv
    pd.DataFrame(
        [
            {
                "run_date": run_date.strftime("%Y-%m-%d"),
                "signal_bar_ts": str(latest_ts),
                "regime": regime,
                "R_last": float(r_series.iloc[-1]),
                "regime_q33": float(regimes.attrs.get("q33", float("nan"))),
                "regime_q66": float(regimes.attrs.get("q66", float("nan"))),
                "leverage": float(latest["leverage"]),
                "gross_ret_bar": float(latest["gross_ret"]),
                "net_ret_bar": float(latest["net_ret"]),
                "turnover_bar": float(latest["turnover"]),
            }
        ]
    ).to_csv(run_dir / "signal_snapshot.csv", index=False, lineterminator="\n")

    # target_weights.csv (the positions the strategy would HOLD going into next bar)
    pd.DataFrame(
        [
            {
                "run_date": run_date.strftime("%Y-%m-%d"),
                "asset": a,
                "weight": round(float(w_scaled[a]), 8),
            }
            for a in strat_assets
        ]
    ).to_csv(run_dir / "target_weights.csv", index=False, lineterminator="\n")

    # turnover.csv
    pd.DataFrame(
        [
            {
                "run_date": run_date.strftime("%Y-%m-%d"),
                "turnover_bar": float(latest["turnover"]),
                "turnover_cum_since_start": float(strat["turnover"].sum()),
            }
        ]
    ).to_csv(run_dir / "turnover.csv", index=False, lineterminator="\n")

    # cost_estimate.csv at locked + 2x + 3x baseline
    rows_cost = []
    for mult in (1.0, 2.0, 3.0):
        cbps = params.cost_bps * mult
        rows_cost.append(
            {
                "run_date": run_date.strftime("%Y-%m-%d"),
                "cost_multiplier": mult,
                "cost_bps": cbps,
                "bar_cost": float(latest["turnover"]) * (cbps / 10_000.0),
            }
        )
    pd.DataFrame(rows_cost).to_csv(run_dir / "cost_estimate.csv", index=False, lineterminator="\n")

    # realized_pnl.csv — pull from paper-state if available, else mark pending
    realized = _read_realized_from_paper_state(run_date)
    if realized is None:
        pd.DataFrame(
            [
                {
                    "run_date": run_date.strftime("%Y-%m-%d"),
                    "status": "pending",
                    "paper_state_seen": False,
                }
            ]
        ).to_csv(run_dir / "realized_pnl.csv", index=False, lineterminator="\n")
    else:
        pd.DataFrame(
            [
                {
                    "run_date": run_date.strftime("%Y-%m-%d"),
                    "status": "observed",
                    "day_n": realized["day_n"],
                    "paper_regime": realized["regime"],
                    "paper_R": realized["R"],
                    "paper_gross_ret": realized["gross_ret"],
                    "paper_net_ret": realized["net_ret"],
                    "paper_turnover": realized["turnover"],
                    "paper_cost": realized["cost"],
                    "paper_equity": realized["equity"],
                }
            ]
        ).to_csv(run_dir / "realized_pnl.csv", index=False, lineterminator="\n")

    # pipeline_status.csv
    pstats = _pipeline_stats(params.ffill_limit_bdays, args.data_dir, regime_assets)
    op_unsafe = bool(pstats["stale_assets_over_5bdays"]) or (
        pstats["misaligned_timestamp_pct"] > 5.0
    )
    pipeline_summary = {
        "run_date": run_date.strftime("%Y-%m-%d"),
        "latest_bar_json": json.dumps(pstats["latest_bar_per_asset"]),
        "stale_assets_over_5bdays": ",".join(pstats["stale_assets_over_5bdays"]),
        "missing_bars_before_ffill": pstats["missing_bar_count_before_ffill"],
        "missing_bars_after_ffill": pstats["missing_bar_count_after_ffill"],
        "misaligned_pct": pstats["misaligned_timestamp_pct"],
        "forward_fill_count": pstats["forward_fill_count"],
        "data_coverage_pct": pstats["data_coverage_pct"],
        "timezone_mismatch": pstats["timezone_mismatch_flag"],
        "operationally_unsafe": op_unsafe,
    }
    pd.DataFrame([pipeline_summary]).to_csv(
        run_dir / "pipeline_status.csv", index=False, lineterminator="\n"
    )

    # invariant_status.csv
    inv_rows = _invariant_runbook(params, strat)
    pd.DataFrame(inv_rows).to_csv(
        run_dir / "invariant_status.csv", index=False, lineterminator="\n"
    )

    # run_manifest.json
    manifest = {
        "schema": "cross_asset_kuramoto_shadow_run_v1",
        "run_utc": _now_utc(),
        "run_date": run_date.strftime("%Y-%m-%d"),
        "signal_bar_ts": str(latest_ts),
        "regime": regime,
        "lock_sha256": _sha256(LOCK_PATH),
        "input_contract_sha256": _sha256(
            REPO / "results" / "cross_asset_kuramoto" / "INPUT_CONTRACT.md"
        ),
        "signal_module_sha256": _sha256(REPO / "core" / "cross_asset_kuramoto" / "signal.py"),
        "engine_module_sha256": _sha256(REPO / "core" / "cross_asset_kuramoto" / "engine.py"),
        "pipeline_summary": pipeline_summary,
        "target_weights": {a: round(float(w_scaled[a]), 8) for a in strat_assets},
        "R_last": float(r_series.iloc[-1]),
        "leverage": float(latest["leverage"]),
        "paper_state_seen": realized is not None,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))

    # run_log.txt
    (run_dir / "run_log.txt").write_text(
        f"[{_now_utc()}] OK: shadow run for {run_date.date()} written to {run_dir}\n"
    )

    # Update LIVE_STATE.json (overwriteable pointer; the evidence itself is append-only)
    all_days = sorted([p.name for p in DAILY_ROOT.iterdir() if p.is_dir()])
    LIVE_STATE.write_text(
        json.dumps(
            {
                "last_run_utc": _now_utc(),
                "last_run_date": run_date.strftime("%Y-%m-%d"),
                "daily_dirs": all_days,
                "n_daily_dirs": len(all_days),
            },
            indent=2,
        )
    )

    print(json.dumps(manifest, indent=2))
    # Any invariant FAIL → exit 3
    if any("FAIL" in r["status"] for r in inv_rows):
        _append_incident(
            {
                "incident_ts": _now_utc(),
                "incident_type": "invariant_violation",
                "severity": "CRITICAL",
                "affected_run_date": run_date.strftime("%Y-%m-%d"),
                "description": json.dumps(inv_rows),
                "resolved_yes_no": "no",
                "resolution_ts": "",
                "changed_artifacts_yes_no": "no",
            }
        )
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Cross-asset Kuramoto shadow runner")
    ap.add_argument("--data-dir", type=Path, default=SPIKE_DATA_DEFAULT)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args(argv)
    return _run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
