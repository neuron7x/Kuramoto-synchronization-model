"""Task 17: closing report generator over all verdict artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FILES = [
    "ofi_unity_dukascopy_verdict.json",
    "ricci_on_spread_verdict.json",
    "plv_spread_market_verdict.json",
    "spread_stress_verdict.json",
    "ricci_regime_verdict.json",
    "horizon_sweep_verdict.json",
    "signal_combiner_verdict.json",
]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {"FINAL": "MISSING"}


def run(results_dir: Path, output_json: Path) -> dict[str, Any]:
    data = {name: _load(results_dir / name) for name in FILES}
    finals = [v.get("FINAL", "MISSING") for v in data.values()]
    passed = sum(1 for f in finals if f in {"SIGNAL_READY", "BREAKTHROUGH", "REGIME_EFFECT"})

    ic_candidates = {
        "ofi": data["ofi_unity_dukascopy_verdict.json"].get("IC", 0.0),
        "ricci": data["ricci_on_spread_verdict.json"].get("IC", 0.0),
        "stress": data["spread_stress_verdict.json"].get("IC", 0.0),
        "combined": data["signal_combiner_verdict.json"].get("IC_combined", 0.0),
    }
    best_signal = max(ic_candidates, key=lambda k: float(ic_candidates[k] or 0.0))
    best_ic = float(ic_candidates[best_signal] or 0.0)

    hs = data["horizon_sweep_verdict.json"]
    optimal_h = hs.get("optimal_horizon_spread")
    regime_effect = data["ricci_regime_verdict.json"].get("FINAL") == "REGIME_EFFECT"
    comb_lift = float(data["signal_combiner_verdict.json"].get("IC_combined", 0.0)) - max(
        float(data["signal_combiner_verdict.json"].get("IC_spread", 0.0)),
        float(data["signal_combiner_verdict.json"].get("IC_ricci", 0.0)),
    )

    report = {
        "substrate": "BID_ASK_MICROSTRUCTURE",
        "signals_tested": 4,
        "signals_passed": passed,
        "best_IC": round(best_ic, 6),
        "best_signal": best_signal,
        "optimal_horizon": optimal_h,
        "regime_effect": regime_effect,
        "combination_lift": round(comb_lift, 6),
        "FINAL_VERDICT": "SIGNAL_READY" if passed > 0 and best_ic >= 0.08 else "REJECT",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    report["replay_hash"] = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    p.add_argument("--output-json", type=Path, default=Path("results/FINAL_REPORT.json"))
    args = p.parse_args()
    run(args.results_dir, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
