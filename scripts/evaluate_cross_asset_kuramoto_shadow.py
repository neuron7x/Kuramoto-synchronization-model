"""Shadow evaluator — aggregates daily evidence + paper-state into the
live scoreboard and the drift/envelope engine.

Deterministic, offline, append-only on the scoreboard and on the
predictive envelope. No signal logic is re-run here; this module only
consumes the shadow runner's output and the spike paper-trader's
append-only evidence ledger.
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

SHADOW_DIR = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
DAILY_ROOT = SHADOW_DIR / "daily"
LIVE_SCOREBOARD = SHADOW_DIR / "live_scoreboard.csv"
PREDICTIVE_ENVELOPE = SHADOW_DIR / "predictive_envelope.csv"
DRIFT_NOTE = SHADOW_DIR / "DRIFT_NOTE.md"
LIVE_STATE = SHADOW_DIR / "LIVE_STATE.json"
LEDGER_CONTINUITY_AUDIT = SHADOW_DIR / "LEDGER_CONTINUITY_AUDIT.json"
OPS_INCIDENTS = SHADOW_DIR / "operational_incidents.csv"
PAPER_EQUITY = Path.home() / "spikes" / "cross_asset_sync_regime" / "paper_state" / "equity.csv"
DEMO_EQUITY = REPO / "results" / "cross_asset_kuramoto" / "demo" / "equity_curve.csv"

ENVELOPE_SEED = 20260422
ENVELOPE_BLOCK_LEN = 20
ENVELOPE_N_PATHS = 500
ENVELOPE_HORIZON_BARS = 90
BARS_PER_YEAR = 252.0
DEMO_MAX_DD = 0.1676  # from risk_metrics.csv
DD_GATE_MULT = 1.5  # G4 · 1.5x demo OOS max DD
# Continuity gate. Bars are business-day-clocked (FX/BTC common business
# day). One missing business day between consecutive ledger rows is
# tolerated as a probable market holiday; two or more is a continuity
# breach (e.g. a power/network outage dropped live bars from the sample).
GAP_HOLIDAY_TOLERANCE_BDAYS = 1

# operational_incidents.csv schema — MUST stay identical to the runner's
# INCIDENT_COLUMNS so the single append-only ledger keeps one schema. A
# drift guard test asserts this equality.
OPS_INCIDENT_COLUMNS = (
    "incident_ts",
    "incident_type",
    "severity",
    "affected_run_date",
    "description",
    "resolved_yes_no",
    "resolution_ts",
    "changed_artifacts_yes_no",
)

# Ledger-continuity guard (enforces ACCEPTANCE_GATES.md G1
# "daily run success rate = 100%"). The live bar count must advance one
# evaluation at a time: across consecutive evaluation dates it must be
# non-decreasing (no counter reset) and must not jump by more than
# MAX_BAR_STEP business days at once (a larger jump means the daily evaluator
# did not run on the skipped bars — the 90-bar verdict would then be computed
# over a ledger with an un-evaluated hole). MAX_BAR_STEP allows a short
# catch-up after a holiday/outage while still flagging multi-week stalls.
MAX_BAR_STEP = 5

SCOREBOARD_COLUMNS = (
    "eval_date",
    "live_bars_completed",
    "cumulative_net_return",
    "annualized_return_live",
    "annualized_vol_live",
    "sharpe_live",
    "max_dd_live",
    "turnover_ann_live",
    "hit_rate_live",
    "avg_win_live",
    "avg_loss_live",
    "cost_drag_bps_live",
    "benchmark_cum_return",
    "benchmark_sharpe_live",
    "relative_return_vs_benchmark",
    "predictive_envelope_quantile",
    "status_label",
    "gate_decision",
)

STATUS_VOCAB = {
    "BUILDING_SAMPLE",
    "WITHIN_EXPECTATION",
    "UNDERWATCH",
    "OUTSIDE_EXPECTATION",
    "OPERATIONALLY_UNSAFE",
}
GATE_VOCAB = {
    "CONTINUE_SHADOW",
    "ESCALATE_REVIEW",
    "NO_DEPLOY",
    "DEPLOYMENT_CANDIDATE_PENDING_OWNER",
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------- #
# Predictive envelope
# --------------------------------------------------------------------- #


def _demo_oos_log_returns() -> np.ndarray:
    df = pd.read_csv(DEMO_EQUITY)
    # equity_curve.csv has strategy_cumret on exp-scale; take log diff
    cum = df["strategy_cumret"].to_numpy()
    log = np.log(np.maximum(cum, 1e-12))
    r = np.diff(log)
    return r[np.isfinite(r)]


def _build_envelope(
    oos: np.ndarray,
    n_paths: int,
    block_len: int,
    horizon: int,
    seed: int,
) -> pd.DataFrame:
    """Block-bootstrap cumulative log-return paths.

    Returns a DataFrame with columns ``p05 p25 p50 p75 p95`` and one
    row per forward bar index (0-based) up to ``horizon``.
    """
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(horizon / block_len))
    n = len(oos)
    if n < block_len:
        raise ValueError(f"insufficient OOS bars ({n}) for block length {block_len}")
    sims = np.zeros((n_paths, horizon))
    for i in range(n_paths):
        pieces: list[np.ndarray] = []
        for _ in range(nb):
            start = int(rng.integers(0, n - block_len + 1))
            pieces.append(oos[start : start + block_len])
        path = np.concatenate(pieces)[:horizon]
        sims[i] = np.cumsum(path)
    q = np.quantile(sims, [0.05, 0.25, 0.50, 0.75, 0.95], axis=0)
    out = pd.DataFrame(
        {
            "forward_bar": np.arange(1, horizon + 1),
            "p05": q[0],
            "p25": q[1],
            "p50": q[2],
            "p75": q[3],
            "p95": q[4],
        }
    )
    return out


def _write_envelope_if_missing(envelope: pd.DataFrame) -> None:
    if PREDICTIVE_ENVELOPE.exists():
        # append-only: do not overwrite existing envelope
        return
    envelope.to_csv(PREDICTIVE_ENVELOPE, index=False, lineterminator="\n")


def _write_drift_note(oos_len: int) -> None:
    if DRIFT_NOTE.exists():
        return
    DRIFT_NOTE.write_text(
        "# Shadow validation · Drift / envelope method\n\n"
        "## Method\n\n"
        f"Block-bootstrap of the demo-ready OOS integrated log-return\n"
        f"series ({oos_len} bars; sourced read-only from "
        "`results/cross_asset_kuramoto/demo/equity_curve.csv`). No new\n"
        "backtest is run; the OOS stream is the already-validated one.\n\n"
        "## Parameters (locked)\n\n"
        f"- seed = `{ENVELOPE_SEED}`\n"
        f"- block length = **{ENVELOPE_BLOCK_LEN}** bars (≈ one\n"
        "  trading-month block; chosen once and frozen)\n"
        f"- number of bootstrap paths = **{ENVELOPE_N_PATHS}**\n"
        f"- forward horizon = **{ENVELOPE_HORIZON_BARS}** bars\n"
        "- quantiles reported: p05, p25, p50, p75, p95\n\n"
        "## Why this is descriptive, not optimisation\n\n"
        "1. No parameter of the strategy is changed, selected, or varied.\n"
        "2. The envelope is a non-parametric summary of the **validated**\n"
        "   OOS return distribution with its own short-range structure\n"
        "   preserved by block sampling.\n"
        "3. The envelope is used only to label the live cumulative path\n"
        "   relative to historical expectation. It has no feedback loop\n"
        "   into signal generation.\n\n"
        "## Reproducibility\n\n"
        "Given the same demo OOS stream, the same seed, the same block\n"
        "length, and the same number of paths, the envelope is\n"
        "bit-identical across runs. The test suite asserts this.\n"
    )


# --------------------------------------------------------------------- #
# Live scoreboard
# --------------------------------------------------------------------- #


def _load_live_ledger(paper_equity: Path) -> pd.DataFrame:
    """Read the spike paper-trader's append-only equity.csv ledger."""
    if not paper_equity.exists():
        return pd.DataFrame()
    df = pd.read_csv(paper_equity, parse_dates=["date"])
    if df.empty:
        return df
    # Deduplicate by date: keep the LAST row per date (idempotent re-ticks)
    df = df.sort_values(["date", "day_n"]).drop_duplicates("date", keep="last")
    df = df.reset_index(drop=True)
    return df


def _detect_ledger_gaps(live: pd.DataFrame) -> list[dict[str, Any]]:
    """Detect missing business-day bars in the append-only equity ledger.

    Between two consecutive ledger rows the expected step is exactly one
    business day. A larger step means one or more bars were never ingested
    (e.g. a power or network outage during the 22:00 UTC run window). Each
    gap is reported with the count of absent business days and a severity:
    a single missing business day is a probable market holiday (WARNING);
    two or more is a continuity breach (CRITICAL).
    """
    if live.empty or "date" not in live.columns or len(live) < 2:
        return []
    dates = pd.to_datetime(live["date"]).dt.normalize().to_numpy(dtype="datetime64[D]")
    gaps: list[dict[str, Any]] = []
    for prev, curr in zip(dates[:-1], dates[1:]):
        missing = int(np.busday_count(prev, curr)) - 1
        if missing > 0:
            gaps.append(
                {
                    "prev_date": str(prev),
                    "curr_date": str(curr),
                    "missing_bdays": missing,
                    "severity": (
                        "WARNING" if missing <= GAP_HOLIDAY_TOLERANCE_BDAYS else "CRITICAL"
                    ),
                }
            )
    return gaps


def _continuity_summary(live: pd.DataFrame) -> dict[str, Any]:
    """Summarise continuity of the full shadow-validation sample.

    ``continuity_breach`` is True when the sample contains at least one
    CRITICAL gap — i.e. a stretch of two or more business days that the
    paper-trader never wrote. A breach corrupts the i.i.d.-over-the-clock
    assumption the predictive envelope rests on, so the gate must fail
    closed on it (see :func:`_decide_status_and_gate`).
    """
    gaps = _detect_ledger_gaps(live)
    breaches = [g for g in gaps if g["severity"] == "CRITICAL"]
    return {
        "continuity_breach": bool(breaches),
        "n_gaps": len(gaps),
        "n_critical_gaps": len(breaches),
        "max_gap_bdays": max((int(g["missing_bdays"]) for g in gaps), default=0),
        "total_missing_bdays": sum(int(g["missing_bdays"]) for g in gaps),
    }


def _append_incident(row: dict[str, Any]) -> None:
    """Append-only write to operational_incidents.csv (shared with the runner)."""
    new = not OPS_INCIDENTS.exists()
    OPS_INCIDENTS.parent.mkdir(parents=True, exist_ok=True)
    with OPS_INCIDENTS.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OPS_INCIDENT_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in OPS_INCIDENT_COLUMNS})


def _gap_description(gap: dict[str, Any]) -> str:
    """Deterministic, idempotent signature for a gap incident."""
    return (
        f"missing-bar gap {gap['prev_date']}->{gap['curr_date']}: "
        f"{gap['missing_bdays']} business day(s) absent from ledger"
    )


def _already_logged_gaps() -> set[str]:
    """Descriptions of gap_detected incidents already in the ledger."""
    if not OPS_INCIDENTS.exists():
        return set()
    df = pd.read_csv(OPS_INCIDENTS)
    if "incident_type" not in df.columns or "description" not in df.columns:
        return set()
    sub = df[df["incident_type"].astype(str) == "gap_detected"]
    return set(sub["description"].astype(str))


def _log_ledger_gaps(live: pd.DataFrame) -> int:
    """Append a gap_detected incident for each not-yet-logged gap.

    Idempotent: a gap whose deterministic signature is already in the
    ledger is skipped, so re-running the daily evaluator never grows the
    incident ledger with duplicates. Returns the number of new rows.
    """
    gaps = _detect_ledger_gaps(live)
    if not gaps:
        return 0
    seen = _already_logged_gaps()
    written = 0
    for gap in gaps:
        descr = _gap_description(gap)
        if descr in seen:
            continue
        _append_incident(
            {
                "incident_ts": _now_utc(),
                "incident_type": "gap_detected",
                "severity": gap["severity"],
                "affected_run_date": gap["curr_date"],
                "description": descr,
                "resolved_yes_no": "no",
                "resolution_ts": "",
                "changed_artifacts_yes_no": "no",
            }
        )
        written += 1
    return written


def _load_pipeline_status_for_latest() -> dict[str, Any]:
    """Pull the most recent daily run's pipeline_status.csv."""
    if not DAILY_ROOT.is_dir():
        return {}
    dirs = sorted([p for p in DAILY_ROOT.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not dirs:
        return {}
    ps = dirs[-1] / "pipeline_status.csv"
    if not ps.is_file():
        return {}
    return pd.read_csv(ps).iloc[0].to_dict()


def _compute_live_metrics(live: pd.DataFrame) -> dict[str, Any]:
    empty_metrics: dict[str, Any] = {
        "live_bars_completed": 0,
        "cumulative_net_return": 0.0,
        "annualized_return_live": float("nan"),
        "annualized_vol_live": float("nan"),
        "sharpe_live": float("nan"),
        "max_dd_live": float("nan"),
        "turnover_ann_live": float("nan"),
        "hit_rate_live": float("nan"),
        "avg_win_live": float("nan"),
        "avg_loss_live": float("nan"),
        "cost_drag_bps_live": float("nan"),
    }
    # Guard against an empty or schema-less ledger (paper-state absent on
    # CI runners, or the spike has not yet written its first tick).
    if live.empty or "net_ret" not in live.columns:
        return empty_metrics
    r = live["net_ret"].astype(float).to_numpy()
    n = int(len(r))
    if n == 0:
        return empty_metrics
    ann_ret = float(np.mean(r) * BARS_PER_YEAR)
    ann_vol = float(np.std(r, ddof=1) * np.sqrt(BARS_PER_YEAR)) if n > 1 else float("nan")
    sharpe = ann_ret / ann_vol if ann_vol and ann_vol > 0 else float("nan")
    eq = live["equity"].astype(float).to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = 1.0 - eq / peak
    max_dd = float(dd.max())
    tov = live["turnover"].astype(float).to_numpy()
    tov_ann = float(np.mean(tov) * BARS_PER_YEAR) if n > 0 else float("nan")
    wins = r[r > 0]
    losses = r[r < 0]
    hit = float((r > 0).mean())
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    cost = live["cost"].astype(float).to_numpy()
    cost_drag_ann_bps = float(np.mean(cost) * BARS_PER_YEAR * 10_000.0)
    return {
        "live_bars_completed": n,
        "cumulative_net_return": float(np.exp(r.sum()) - 1.0),
        "annualized_return_live": ann_ret,
        "annualized_vol_live": ann_vol,
        "sharpe_live": sharpe,
        "max_dd_live": max_dd,
        "turnover_ann_live": tov_ann,
        "hit_rate_live": hit,
        "avg_win_live": avg_win,
        "avg_loss_live": avg_loss,
        "cost_drag_bps_live": cost_drag_ann_bps,
    }


def _envelope_position(live_cum_log: float, bar_n: int, envelope: pd.DataFrame) -> str:
    """Label live cumulative log-return against the envelope at ``bar_n``."""
    row = envelope[envelope["forward_bar"] == bar_n]
    if row.empty:
        return "out_of_horizon"
    p5 = float(row["p05"].iloc[0])
    p25 = float(row["p25"].iloc[0])
    p75 = float(row["p75"].iloc[0])
    p95 = float(row["p95"].iloc[0])
    if live_cum_log < p5:
        return "below_p05"
    if live_cum_log < p25:
        return "p05_p25"
    if live_cum_log <= p75:
        return "p25_p75"
    if live_cum_log <= p95:
        return "p75_p95"
    return "above_p95"


def _benchmark_cum(live: pd.DataFrame) -> tuple[float, float]:
    """Equal-weight buy-and-hold benchmark cum-return and Sharpe from equity ledger.

    The paper-state equity.csv includes a ``btc_equity`` column as the
    spike's built-in BTC benchmark; we use that (not a re-computation)
    to stay read-only."""
    if "btc_equity" not in live.columns or live.empty:
        return float("nan"), float("nan")
    btc_eq = live["btc_equity"].astype(float).to_numpy()
    btc_cum = float(btc_eq[-1] - 1.0)
    btc_ret = np.diff(np.log(np.maximum(btc_eq, 1e-12)))
    if len(btc_ret) < 2:
        return btc_cum, float("nan")
    mu = btc_ret.mean() * BARS_PER_YEAR
    sd = btc_ret.std(ddof=1) * np.sqrt(BARS_PER_YEAR)
    sh = mu / sd if sd > 0 else float("nan")
    return btc_cum, sh


# --------------------------------------------------------------------- #
# Gate engine
# --------------------------------------------------------------------- #


def _latest_pipeline_unsafe() -> bool:
    ps = _load_pipeline_status_for_latest()
    return bool(ps.get("operationally_unsafe", False))


def _any_invariant_fail() -> bool:
    if not DAILY_ROOT.is_dir():
        return False
    for d in DAILY_ROOT.iterdir():
        inv = d / "invariant_status.csv"
        if not inv.exists():
            continue
        df = pd.read_csv(inv)
        if (df["status"].astype(str).str.contains("FAIL")).any():
            return True
    return False


def _envelope_sub_p05_streak(board: pd.DataFrame) -> int:
    """Trailing run of evaluation rows where envelope position is below_p05."""
    if board.empty:
        return 0
    tail = board["predictive_envelope_quantile"].astype(str).tolist()
    n = 0
    for s in reversed(tail):
        if s == "below_p05":
            n += 1
        else:
            break
    return n


def audit_ledger_continuity(board: pd.DataFrame) -> tuple[bool, list[str]]:
    """Fail-closed continuity audit of the live scoreboard ledger (G1).

    Returns ``(ok, violations)``. The verdict cannot reach a deployment
    candidate while the ledger is discontinuous: a gap, a reset, or a conflict
    means the "daily run success rate = 100%" gate (``ACCEPTANCE_GATES.md`` G1)
    was breached and the bar count overstates the number of *actually
    evaluated* bars.

    Checks (on the rows already on disk, before the current evaluation):

    * **monotone** — ``live_bars_completed`` is non-decreasing across evaluation
      dates (a counter reset is a writer/data fault);
    * **no stall** — consecutive evaluation dates advance the bar count by at
      most ``MAX_BAR_STEP`` (a larger jump means un-evaluated bars, e.g. a
      multi-week daily-runner stall);
    * **consistent** — the same ``(eval_date, live_bars_completed)`` never
      carries conflicting metric values (duplicate appends must be idempotent).
    """
    violations: list[str] = []
    if board.empty or "live_bars_completed" not in board.columns:
        return True, violations
    df = board.copy()
    df["live_bars_completed"] = pd.to_numeric(df["live_bars_completed"], errors="coerce")
    df = df.dropna(subset=["live_bars_completed", "eval_date"])
    if df.empty:
        return True, violations

    # Conflicting duplicates: same (date, bar) carrying differing metrics.
    metric_cols = [c for c in SCOREBOARD_COLUMNS if c not in ("eval_date", "live_bars_completed")]
    for (date, bar), grp in df.groupby(["eval_date", "live_bars_completed"]):
        if len(grp[metric_cols].drop_duplicates()) > 1:
            violations.append(
                f"conflicting rows for eval_date={date} bar={int(bar)}: duplicate "
                f"appends are not idempotent (distinct metric tuples for one bar)"
            )

    # Per-date bar count (max if a date was re-evaluated), in chronological order
    # (ISO eval_date strings sort chronologically).
    per_date = df.groupby("eval_date")["live_bars_completed"].max().sort_index()
    prev_date: str | None = None
    prev_bar: int | None = None
    for date, bar_val in per_date.items():
        bar = int(bar_val)
        if prev_bar is not None:
            if bar < prev_bar:
                violations.append(
                    f"non-monotone bar count: {prev_date}={prev_bar} -> {date}={bar} "
                    f"(counter reset / rewrite)"
                )
            elif bar - prev_bar > MAX_BAR_STEP:
                violations.append(
                    f"bar-count stall: {prev_date}={prev_bar} -> {date}={bar} "
                    f"(+{bar - prev_bar} > MAX_BAR_STEP={MAX_BAR_STEP}; "
                    f"{bar - prev_bar - 1} un-evaluated bars — G1 daily-run gap)"
                )
        prev_date, prev_bar = str(date), bar
    return (len(violations) == 0), violations


def _decide_status_and_gate(
    bars: int,
    metrics: dict[str, Any],
    env_pos: str,
    op_unsafe: bool,
    inv_fail: bool,
    sub_p05_streak: int,
    continuity_breach: bool = False,
    ledger_discontinuous: bool = False,
) -> tuple[str, str]:
    # Hard operational short-circuits. Ledger discontinuity is a G1
    # ("daily run success rate = 100%") breach: the bar count cannot be trusted,
    # so no gate may advance — least of all the 90-bar deployment candidate.
    if ledger_discontinuous:
        return "OPERATIONALLY_UNSAFE", "ESCALATE_REVIEW"
    if op_unsafe or inv_fail:
        return "OPERATIONALLY_UNSAFE", "ESCALATE_REVIEW"

    # Continuity gate — a missing-bar breach (two or more business days
    # dropped from the sample) corrupts the envelope's clock assumption.
    # Fail closed: a discontinuous sample can never advance to a deploy
    # candidate, regardless of how favourable the surviving bars look.
    if continuity_breach:
        return "OPERATIONALLY_UNSAFE", "NO_DEPLOY"

    # Risk gate G4
    dd_live = metrics.get("max_dd_live") or 0.0
    if np.isfinite(dd_live) and dd_live > DEMO_MAX_DD * DD_GATE_MULT:
        return "OUTSIDE_EXPECTATION", "ESCALATE_REVIEW"

    # Drift gate G3
    if env_pos == "below_p05" and sub_p05_streak >= 20:
        if bars >= 60:
            return "OUTSIDE_EXPECTATION", "NO_DEPLOY"
        return "OUTSIDE_EXPECTATION", "ESCALATE_REVIEW"

    if bars < 20:
        return "BUILDING_SAMPLE", "CONTINUE_SHADOW"

    # 90-bar truth gate
    if bars >= 90:
        if env_pos in {"p25_p75", "p75_p95"} and metrics.get("sharpe_live", float("nan")) > 0:
            return "WITHIN_EXPECTATION", "DEPLOYMENT_CANDIDATE_PENDING_OWNER"
        if env_pos in {"p05_p25"}:
            return "UNDERWATCH", "CONTINUE_SHADOW"
        return "OUTSIDE_EXPECTATION", "NO_DEPLOY"

    # Interior bars
    if env_pos == "below_p05":
        return "OUTSIDE_EXPECTATION", "ESCALATE_REVIEW"
    if env_pos == "p05_p25":
        return "UNDERWATCH", "CONTINUE_SHADOW"
    return "WITHIN_EXPECTATION", "CONTINUE_SHADOW"


# --------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------- #


def _append_scoreboard(row: dict[str, Any]) -> None:
    new = not LIVE_SCOREBOARD.exists()
    with LIVE_SCOREBOARD.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SCOREBOARD_COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in SCOREBOARD_COLUMNS})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shadow validation evaluator")
    ap.add_argument("--paper-equity", type=Path, default=PAPER_EQUITY)
    ap.add_argument("--rebuild-envelope", action="store_true")
    args = ap.parse_args(argv)

    SHADOW_DIR.mkdir(parents=True, exist_ok=True)

    # Predictive envelope (append-only; regenerated only on --rebuild-envelope)
    oos = _demo_oos_log_returns()
    envelope = _build_envelope(
        oos,
        n_paths=ENVELOPE_N_PATHS,
        block_len=ENVELOPE_BLOCK_LEN,
        horizon=ENVELOPE_HORIZON_BARS,
        seed=ENVELOPE_SEED,
    )
    if args.rebuild_envelope and PREDICTIVE_ENVELOPE.exists():
        PREDICTIVE_ENVELOPE.unlink()
    _write_envelope_if_missing(envelope)
    _write_drift_note(len(oos))

    # Live ledger from spike paper-state
    live = _load_live_ledger(args.paper_equity)
    metrics = _compute_live_metrics(live)
    bars = metrics["live_bars_completed"]

    bench_cum, bench_sh = _benchmark_cum(live)

    # Envelope position at the current live bar
    live_cum_log = float(np.log(1.0 + metrics["cumulative_net_return"])) if bars > 0 else 0.0
    env_pos = _envelope_position(live_cum_log, bars, envelope) if bars > 0 else "n/a"

    # Existing scoreboard (to measure below-p05 streak)
    board = (
        pd.read_csv(LIVE_SCOREBOARD)
        if LIVE_SCOREBOARD.exists()
        else pd.DataFrame(columns=list(SCOREBOARD_COLUMNS))
    )
    streak = _envelope_sub_p05_streak(board)
    if env_pos == "below_p05":
        streak += 1
    else:
        streak = 0

    # G1 ledger-continuity guard (read-only on the existing scoreboard).
    ledger_ok, ledger_violations = audit_ledger_continuity(board)
    LEDGER_CONTINUITY_AUDIT.write_text(
        json.dumps(
            {
                "audited_utc": _now_utc(),
                "scoreboard_sha256": _sha256(LIVE_SCOREBOARD) if LIVE_SCOREBOARD.exists() else "",
                "continuous": ledger_ok,
                "max_bar_step": MAX_BAR_STEP,
                "violations": ledger_violations,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if not ledger_ok:
        for v in ledger_violations:
            print(f"LEDGER-DISCONTINUITY (G1): {v}", file=sys.stderr)

    op_unsafe = _latest_pipeline_unsafe()
    inv_fail = _any_invariant_fail()

    # Continuity audit of the live ledger: detect and log any missing-bar
    # gaps, then fail the gate closed if the sample is discontinuous.
    continuity = _continuity_summary(live)
    _log_ledger_gaps(live)

    status, gate = _decide_status_and_gate(
        bars=bars,
        metrics=metrics,
        env_pos=env_pos,
        op_unsafe=op_unsafe,
        inv_fail=inv_fail,
        sub_p05_streak=streak,
        continuity_breach=bool(continuity["continuity_breach"]),
        ledger_discontinuous=not ledger_ok,
    )

    assert status in STATUS_VOCAB, f"status {status!r} not in {sorted(STATUS_VOCAB)}"
    assert gate in GATE_VOCAB, f"gate {gate!r} not in {sorted(GATE_VOCAB)}"

    eval_row = {
        "eval_date": _now_utc()[:10],
        "live_bars_completed": bars,
        "cumulative_net_return": round(metrics["cumulative_net_return"], 6),
        "annualized_return_live": (
            round(metrics["annualized_return_live"], 6)
            if np.isfinite(metrics["annualized_return_live"])
            else ""
        ),
        "annualized_vol_live": (
            round(metrics["annualized_vol_live"], 6)
            if np.isfinite(metrics["annualized_vol_live"])
            else ""
        ),
        "sharpe_live": (
            round(metrics["sharpe_live"], 4) if np.isfinite(metrics["sharpe_live"]) else ""
        ),
        "max_dd_live": (
            round(metrics["max_dd_live"], 6) if np.isfinite(metrics["max_dd_live"]) else ""
        ),
        "turnover_ann_live": (
            round(metrics["turnover_ann_live"], 4)
            if np.isfinite(metrics["turnover_ann_live"])
            else ""
        ),
        "hit_rate_live": (
            round(metrics["hit_rate_live"], 4) if np.isfinite(metrics["hit_rate_live"]) else ""
        ),
        "avg_win_live": (
            round(metrics["avg_win_live"], 6) if np.isfinite(metrics["avg_win_live"]) else ""
        ),
        "avg_loss_live": (
            round(metrics["avg_loss_live"], 6) if np.isfinite(metrics["avg_loss_live"]) else ""
        ),
        "cost_drag_bps_live": (
            round(metrics["cost_drag_bps_live"], 2)
            if np.isfinite(metrics["cost_drag_bps_live"])
            else ""
        ),
        "benchmark_cum_return": round(bench_cum, 6) if np.isfinite(bench_cum) else "",
        "benchmark_sharpe_live": round(bench_sh, 4) if np.isfinite(bench_sh) else "",
        "relative_return_vs_benchmark": (
            round(metrics["cumulative_net_return"] - bench_cum, 6) if np.isfinite(bench_cum) else ""
        ),
        "predictive_envelope_quantile": env_pos,
        "status_label": status,
        "gate_decision": gate,
    }
    _append_scoreboard(eval_row)

    # Update LIVE_STATE
    LIVE_STATE.write_text(
        json.dumps(
            {
                "last_eval_utc": _now_utc(),
                "live_bars": bars,
                "cumulative_net_return": round(metrics["cumulative_net_return"], 6),
                "sharpe_live": (
                    round(metrics["sharpe_live"], 4)
                    if np.isfinite(metrics["sharpe_live"])
                    else None
                ),
                "max_dd_live": (
                    round(metrics["max_dd_live"], 6)
                    if np.isfinite(metrics["max_dd_live"])
                    else None
                ),
                "predictive_envelope_quantile": env_pos,
                "status_label": status,
                "gate_decision": gate,
                "operationally_unsafe": op_unsafe,
                "any_invariant_fail": inv_fail,
                "continuity_breach": bool(continuity["continuity_breach"]),
                "continuity_gaps": int(continuity["n_gaps"]),
                "continuity_critical_gaps": int(continuity["n_critical_gaps"]),
                "continuity_max_gap_bdays": int(continuity["max_gap_bdays"]),
                "continuity_total_missing_bdays": int(continuity["total_missing_bdays"]),
                "ledger_continuous": ledger_ok,
                "ledger_continuity_violations": len(ledger_violations),
            },
            indent=2,
        )
    )

    print(json.dumps({"eval": eval_row}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
