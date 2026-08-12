"""Render the human-readable SHADOW_SUMMARY.md from the live scoreboard,
the predictive envelope, and the operational-incident ledger.

Deterministic, offline, ≤ 500 words. No interactive input, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

import pandas as pd  # noqa: E402

SHADOW_DIR = REPO / "results" / "cross_asset_kuramoto" / "shadow_validation"
SCOREBOARD = SHADOW_DIR / "live_scoreboard.csv"
LIVE_STATE = SHADOW_DIR / "LIVE_STATE.json"
ENVELOPE = SHADOW_DIR / "predictive_envelope.csv"
INCIDENTS = SHADOW_DIR / "operational_incidents.csv"
SUMMARY = SHADOW_DIR / "SHADOW_SUMMARY.md"


def _latest_scoreboard_row() -> dict | None:
    if not SCOREBOARD.exists():
        return None
    df = pd.read_csv(SCOREBOARD)
    if df.empty:
        return None
    return dict(df.iloc[-1])


def _incident_count() -> int:
    if not INCIDENTS.exists():
        return 0
    return int(len(pd.read_csv(INCIDENTS)))


def _render_md() -> str:
    row = _latest_scoreboard_row()
    inc = _incident_count()
    state = json.loads(LIVE_STATE.read_text()) if LIVE_STATE.exists() else {}
    envelope_exists = ENVELOPE.exists()

    lines: list[str] = []
    lines.append("# Cross-Asset Kuramoto · Shadow Summary\n")
    lines.append(
        "Deterministic snapshot from the live scoreboard. Numbers and\n"
        "gate decisions only; no marketing language.\n\n"
    )

    if row is None:
        lines.append("## No evaluation data yet.\n\n")
        lines.append(
            "Run `python scripts/evaluate_cross_asset_kuramoto_shadow.py` "
            "after at least one shadow run to populate the scoreboard.\n"
        )
        return "".join(lines)

    bars = int(float(row.get("live_bars_completed", 0)))
    lines.append("## Current live bar count\n\n")
    lines.append(f"- Live bars completed: **{bars}**\n")
    lines.append("- Spike paper-trader start date: 2026-04-11 " "(day-90 gate ≈ 2026-07-10)\n\n")

    lines.append("## Operational health\n\n")
    lines.append(f"- Predictive envelope built: **{envelope_exists}**\n")
    lines.append(f"- Operational incidents logged: **{inc}**\n")
    lines.append(
        f"- Operationally unsafe (latest): " f"**{state.get('operationally_unsafe', 'n/a')}**\n"
    )
    lines.append(f"- Any invariant fail: **{state.get('any_invariant_fail', False)}**\n\n")

    def _f(v: object) -> str:
        try:
            return f"{float(v):.4f}"
        except (TypeError, ValueError):
            return str(v)

    lines.append("## Live metrics\n\n")
    lines.append("| metric | value |\n|---|---:|\n")
    for col in (
        "cumulative_net_return",
        "annualized_return_live",
        "annualized_vol_live",
        "sharpe_live",
        "max_dd_live",
        "hit_rate_live",
        "turnover_ann_live",
        "cost_drag_bps_live",
    ):
        lines.append(f"| {col} | {_f(row.get(col, ''))} |\n")
    lines.append("\n")

    lines.append("## Benchmark comparison\n\n")
    lines.append("| metric | value |\n|---|---:|\n")
    for col in ("benchmark_cum_return", "benchmark_sharpe_live", "relative_return_vs_benchmark"):
        lines.append(f"| {col} | {_f(row.get(col, ''))} |\n")
    lines.append("\n")

    lines.append("## Envelope position\n\n")
    lines.append(
        f"- Quantile band (live vs historical OOS block-bootstrap): "
        f"**{row.get('predictive_envelope_quantile', 'n/a')}**\n"
        "- Envelope source: demo-ready OOS integrated log returns\n"
        "  (`results/cross_asset_kuramoto/demo/equity_curve.csv`); seed and\n"
        "  block length locked in `DRIFT_NOTE.md`.\n\n"
    )

    lines.append("## Cost sensitivity (demo-baseline, recorded)\n\n")
    lines.append(
        "Baseline OOS cost drag at lock: 231 bps / year (23.1 % of gross,\n"
        "see `COST_MODEL.md`). Live cost drag above is reported with the\n"
        "paper-trader's own per-bar cost slot, cumulated over live bars.\n\n"
    )

    lines.append("## Known caveats carried from demo-ready stage\n\n")
    lines.append(
        "- OBS-1 `scipy.signal.hilbert` non-causal; preserved\n"
        "  (`INTEGRATION_NOTES.md`).\n"
        "- DP5 forward-fill(limit=3) material (ΔSharpe 0.22); preserved\n"
        "  (`PIPELINE_AUDIT.md`).\n"
        "- DP3 data snapshot age >5 bdays vs current clock; this is\n"
        "  expected for the spike snapshot and **is** the source of the\n"
        "  current `OPERATIONALLY_UNSAFE` label.\n"
        "- Fold 3 (2022) Sharpe −1.15 historically; preserved.\n\n"
    )

    lines.append("## Current recommendation\n\n")
    lines.append(
        f"- **status_label:** `{row.get('status_label', 'n/a')}`\n"
        f"- **gate_decision:** `{row.get('gate_decision', 'n/a')}`\n\n"
    )
    lines.append(
        "Claude Code does not authorize capital deployment. The gate is\n"
        "advisory and computed from `ACCEPTANCE_GATES.md`. At 90 live bars\n"
        "the truth gate fires exactly one of `DEPLOYMENT_CANDIDATE_PENDING_OWNER`,\n"
        "`CONTINUE_SHADOW`, or `NO_DEPLOY`.\n"
    )
    return "".join(lines)


def main() -> int:
    SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    md = _render_md()
    SUMMARY.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
