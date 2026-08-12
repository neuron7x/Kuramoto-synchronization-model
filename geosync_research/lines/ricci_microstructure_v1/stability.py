"""Cross-seed stability + multiple-null correction (V2 task 6).

A single-seed SUPPORTED verdict can be a seed fluke. This module aggregates the
per-seed artifacts (seeds 1337 / 2026 / 7719) into one stability verdict and
provides a Bonferroni correction for when several nulls are tested.

Rule (fail-closed): the lane may report SUPPORTED only if EVERY seed is SUPPORTED
and the statuses are consistent across seeds. Any disagreement, or any seed not
SUPPORTED, demotes the aggregate to the worst observed allowed status — never an
optimistic one. Only the three allowed statuses are emitted.
"""

from __future__ import annotations

from typing import Any

REQUIRED_SEEDS = (1337, 2026, 7719)
_ALLOWED = ("SUPPORTED", "HYPOTHESIS_NOT_SUPPORTED", "INVALID")
# severity order: SUPPORTED is the strongest claim, so the aggregate is the
# *least* supportive status any seed produced (fail-closed demotion).
_SEVERITY = {"SUPPORTED": 0, "HYPOTHESIS_NOT_SUPPORTED": 1, "INVALID": 2}


def bonferroni(p_values: dict[str, float]) -> dict[str, float]:
    """Bonferroni-correct a family of per-null p-values: p_adj = min(1, p * m)."""
    m = len(p_values)
    if m == 0:
        return {}
    return {k: min(1.0, float(v) * m) for k, v in p_values.items()}


def seed_stability(
    artifacts: list[dict[str, Any]],
    *,
    p_threshold: float = 0.01,
    delta_floor: float = 0.147,
) -> dict[str, Any]:
    """Aggregate per-seed artifacts into a fail-closed stability verdict."""
    if not artifacts:
        return {"n_seeds": 0, "stable": False, "aggregate_status": "INVALID", "reason": "no seeds"}

    statuses = [str(a["falsification_status"]) for a in artifacts]
    if any(s not in _ALLOWED for s in statuses):
        raise ValueError(f"non-allowed status present: {statuses}")
    seeds = sorted(int(a["seed"]) for a in artifacts)
    p_values = [float(a["p_value"]) for a in artifacts]
    deltas = [float(a["cliffs_delta"]) for a in artifacts]
    curvs = [float(a["mean_curvature"]) for a in artifacts]

    consistent = len(set(statuses)) == 1
    # fail-closed: aggregate is the least-supportive status any seed produced
    aggregate_status = max(statuses, key=lambda s: _SEVERITY[s])
    all_supported = all(s == "SUPPORTED" for s in statuses)
    # a SUPPORTED aggregate additionally requires every seed to clear both gates
    gates_all = all(p < p_threshold and abs(d) >= delta_floor for p, d in zip(p_values, deltas))
    if all_supported and consistent and gates_all:
        aggregate_status = "SUPPORTED"

    return {
        "n_seeds": len(artifacts),
        "seeds": seeds,
        "required_seeds_present": set(seeds) >= set(REQUIRED_SEEDS),
        "statuses": statuses,
        "consistent": consistent,
        "stable": consistent,
        "aggregate_status": aggregate_status,
        "p_value_range": [min(p_values), max(p_values)],
        "cliffs_delta_range": [min(deltas), max(deltas)],
        "mean_curvature_range": [min(curvs), max(curvs)],
    }
