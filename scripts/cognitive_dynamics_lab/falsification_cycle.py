#!/usr/bin/env python3
# mypy: ignore-errors
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import TypedDict


class WeightResult(TypedDict):
    weight: str
    value: float
    baseline_score: float
    ablation_score: float
    amplification_score: float
    signal_loss: float
    risk_delta: float
    verdict: str
    verification: str


WEIGHTS: dict[str, float] = {
    "alpha_error": 0.35,
    "alpha_explore": 0.20,
    "alpha_gain": 0.20,
    "alpha_novelty": 0.25,
    "beta_energy": 0.25,
    "beta_invalid": 0.25,
    "beta_sparsity": 0.20,
    "beta_stability": 0.30,
    "w_accuracy": 0.25,
    "w_diversity": 0.15,
    "w_energy": 0.10,
    "w_realism": 0.30,
    "w_stability": 0.20,
}


def evaluate_weight(name: str, value: float) -> WeightResult:
    baseline = round(value * 10.0, 6)
    ablation = 0.0
    amplified = round(value * 15.0, 6)
    signal_loss = round(baseline - ablation, 6)
    risk_delta = round(max(0.0, amplified - 4.5), 6)
    if signal_loss >= 1.5 and risk_delta <= 0.5:
        verdict = "retain"
    else:
        verdict = "schedule_review"
    return {
        "weight": name,
        "value": value,
        "baseline_score": baseline,
        "ablation_score": ablation,
        "amplification_score": amplified,
        "signal_loss": signal_loss,
        "risk_delta": risk_delta,
        "verdict": verdict,
        "verification": "deterministic_replay_only",
    }


def write_cycle_outputs(out: Path, rows: list[WeightResult]) -> None:
    (out / "falsification_cycle.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    table_path = out / "falsification_table.csv"
    with table_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "weight",
                "value",
                "baseline_score",
                "ablation_score",
                "amplification_score",
                "signal_loss",
                "risk_delta",
                "verdict",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["weight"],
                    row["value"],
                    row["baseline_score"],
                    row["ablation_score"],
                    row["amplification_score"],
                    row["signal_loss"],
                    row["risk_delta"],
                    row["verdict"],
                ]
            )


def build_summary(rows: list[WeightResult]) -> dict[str, object]:
    return {
        "mode": "deterministic_synthetic_weight_review",
        "claim_tier": "simulation-only",
        "weights_tested": len(rows),
        "scheduled_for_review": sum(row["verdict"] != "retain" for row in rows),
        "entropy_residual": 0.0,
        "reproducibility": 1.0,
        "outputs": ["falsification_cycle.json", "falsification_table.csv"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="artifacts/cognitive_dynamics_lab")
    out = Path(parser.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)

    rows = [evaluate_weight(name, value) for name, value in sorted(WEIGHTS.items())]
    write_cycle_outputs(out, rows)

    summary = build_summary(rows)
    (out / "falsification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
