from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.hyperdirect_veto import HyperdirectConfig, HyperdirectVeto  # noqa: E402

__all__ = ["CalibrationPoint", "characterise", "recommend_gain", "main"]

# ---------------------------------------------------------------------------
# PROVENANCE / TIER
#
#   This is a SYNTHETIC characterisation. The (conflict, margin,
#   should_promote) triples are drawn from a hand-specified generative
#   model, NOT from observed inference outcomes. Tier: EXTRAPOLATED.
#   It produces a *tradeoff surface* and a *procedure*, never a claim
#   that any parameter is "validated", "optimal", or "production-ready"
#   on real data. Real calibration requires a labelled corpus of past
#   inference promotions and lives upstream of this primitive.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationPoint:
    conflict_gain: float
    false_promote_rate: float  # promoted a should-NOT-promote claim
    false_veto_rate: float  # vetoed a should-promote claim
    n_pos: int
    n_neg: int


def _synthetic_corpus(n: int, seed: int) -> list[tuple[dict[str, float], float, bool]]:
    """Hand-specified generative model.

    POSITIVE (should promote): strong margin, low residual conflict.
    NEGATIVE (should not):      weak/!= margin, elevated residual conflict.
    The two classes overlap on purpose so the surface is non-trivial.
    """
    rng = random.Random(seed)
    rows: list[tuple[dict[str, float], float, bool]] = []
    for _ in range(n):
        positive = rng.random() < 0.5
        if positive:
            margin = rng.gauss(0.6, 0.25)
            conflict = {
                "falsifier_disagreement": abs(rng.gauss(0.10, 0.10)),
                "witness_uncertainty": abs(rng.gauss(0.10, 0.10)),
                "purpose_drift": abs(rng.gauss(0.08, 0.08)),
            }
        else:
            margin = rng.gauss(0.20, 0.30)
            conflict = {
                "falsifier_disagreement": min(1.0, abs(rng.gauss(0.45, 0.25))),
                "witness_uncertainty": min(1.0, abs(rng.gauss(0.40, 0.25))),
                "purpose_drift": min(1.0, abs(rng.gauss(0.35, 0.20))),
            }
        conflict = {k: max(0.0, min(1.0, v)) for k, v in conflict.items()}
        rows.append((conflict, margin, positive))
    return rows


def characterise(
    gains: list[float],
    *,
    n: int = 20_000,
    seed: int = 20260515,
    hard_ceiling: float = 0.8,
    base_margin: float = 0.0,
) -> list[CalibrationPoint]:
    corpus = _synthetic_corpus(n, seed)
    n_pos = sum(1 for _, _, p in corpus if p)
    n_neg = len(corpus) - n_pos
    points: list[CalibrationPoint] = []
    for gain in gains:
        gate = HyperdirectVeto(
            HyperdirectConfig(
                hard_ceiling=hard_ceiling,
                base_margin=base_margin,
                conflict_gain=gain,
            )
        )
        false_promote = 0
        false_veto = 0
        for conflict, margin, should_promote in corpus:
            promoted = gate.evaluate(conflict, evidence_margin=margin).passed
            if promoted and not should_promote:
                false_promote += 1
            elif not promoted and should_promote:
                false_veto += 1
        points.append(
            CalibrationPoint(
                conflict_gain=gain,
                false_promote_rate=false_promote / max(1, n_neg),
                false_veto_rate=false_veto / max(1, n_pos),
                n_pos=n_pos,
                n_neg=n_neg,
            )
        )
    return points


def recommend_gain(
    points: list[CalibrationPoint], max_false_veto: float
) -> CalibrationPoint | None:
    """Principled default: this is a fail-closed brake, so the objective
    is to MINIMISE false-promote (letting a bad claim through) subject to
    keeping false-veto (blocking a good claim) within an explicit budget.
    No magic number — the default falls out of the stated objective and
    the synthetic surface, and is only as good as that synthetic model.
    """
    feasible = [p for p in points if p.false_veto_rate <= max_false_veto]
    if not feasible:
        return None
    return min(feasible, key=lambda p: (p.false_promote_rate, -p.conflict_gain))


def main() -> int:
    gains = [round(0.25 * i, 2) for i in range(0, 13)]
    points = characterise(gains)
    print("HyperdirectVeto — SYNTHETIC calibration surface (tier: EXTRAPOLATED)")
    print("  generative model is hand-specified; NOT observed inference data.")
    print(f"  corpus: n_pos={points[0].n_pos} n_neg={points[0].n_neg}\n")
    print(f"  {'gain':>6} {'false_promote':>14} {'false_veto':>11}")
    for p in points:
        print(f"  {p.conflict_gain:>6.2f} {p.false_promote_rate:>14.4f} {p.false_veto_rate:>11.4f}")
    budget = 0.10
    rec = recommend_gain(points, max_false_veto=budget)
    print(f"\n  procedure: minimise false_promote s.t. false_veto <= {budget:.2f}")
    if rec is None:
        print(
            "  -> no gain in the swept range meets the budget on this "
            "synthetic surface (report honestly; do not pick anyway)."
        )
    else:
        print(
            f"  -> synthetic default conflict_gain={rec.conflict_gain:.2f} "
            f"(false_promote={rec.false_promote_rate:.4f}, "
            f"false_veto={rec.false_veto_rate:.4f}). EXTRAPOLATED — must be "
            f"re-derived on a real labelled promotion corpus before any "
            f"non-advisory use."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
