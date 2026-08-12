# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic scenario simulation harness for the descriptor pipeline.

Runs the integrated descriptor capsule
(:func:`analytics.signals.descriptor_capsule.build_capsule`) across a fixed
catalogue of seeded scenarios — ``nominal``, ``noisy``, ``boundary``,
``degenerate``, ``invalid``, ``null_baseline`` — so the descriptor modules are
exercised reproducibly over their whole input manifold, not just the happy
path. Each scenario deterministically generates an observed series from its
seed; the harness feeds it through the capsule and reports the manifest digest,
the information-quality summary, and the invalid-state count.

There are NO trading or predictive semantics anywhere here: scenarios are
structural input regimes, and every emitted manifest carries
``claim_boundary="descriptor_only_not_predictor"``. Identical seeds reproduce
byte-identical scenario manifests.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np

from analytics.signals.descriptor_capsule import build_capsule

__all__ = ["SCENARIOS", "run_scenario", "run_all_scenarios"]

# Shared deterministic quantization frame for every scenario.
_THRESHOLDS = [-0.5, 0.5]
_LABELS = ["low", "mid", "high"]
_N = 512


def _nominal(rng: np.random.Generator) -> list[float]:
    return rng.normal(0.0, 1.0, size=_N).tolist()


def _noisy(rng: np.random.Generator) -> list[float]:
    base = rng.normal(0.0, 1.0, size=_N)
    # sparse heavy-tailed contamination — finite, still well-defined
    idx = rng.integers(0, _N, size=_N // 20)
    base[idx] += rng.normal(0.0, 8.0, size=idx.size)
    return base.tolist()


def _boundary(rng: np.random.Generator) -> list[float]:
    # values sitting exactly on the declared thresholds
    pattern = np.array(_THRESHOLDS * (_N // len(_THRESHOLDS)), dtype=np.float64)
    return pattern.tolist()


def _degenerate(rng: np.random.Generator) -> list[float]:
    # constant series — collapses to a single quantized state
    return np.full(_N, 0.0, dtype=np.float64).tolist()


def _invalid(rng: np.random.Generator) -> list[float]:
    # finite series with injected non-finite values -> counted as invalid states
    base = rng.normal(0.0, 1.0, size=_N)
    base[::17] = np.nan
    base[5::31] = np.inf
    return base.tolist()


def _null_baseline(rng: np.random.Generator) -> list[float]:
    # observed drawn from the same law as the null -> structurally indistinguishable
    return rng.normal(0.0, 1.0, size=_N).tolist()


SCENARIOS: Mapping[str, Callable[[np.random.Generator], list[float]]] = {
    "nominal": _nominal,
    "noisy": _noisy,
    "boundary": _boundary,
    "degenerate": _degenerate,
    "invalid": _invalid,
    "null_baseline": _null_baseline,
}


def run_scenario(name: str, *, seed: int) -> dict[str, Any]:
    """Run one named scenario deterministically and return its capsule report."""
    if name not in SCENARIOS:
        raise ValueError(
            f"descriptor-scenarios: unknown scenario {name!r}; choose from {sorted(SCENARIOS)}"
        )
    rng = np.random.default_rng(seed)
    observed = SCENARIOS[name](rng)
    config = {
        "observed": observed,
        "thresholds": _THRESHOLDS,
        "labels": _LABELS,
        "null_seed": seed,
        "null_n": _N,
        "source": f"scenario:{name}",
    }
    manifest = build_capsule(config)
    iq = manifest["stages"]["information_quality"]
    return {
        "scenario": name,
        "seed": int(seed),
        "manifest_digest": manifest["manifest_digest"],
        "invalid_count": manifest["stages"]["quantization"]["invalid_count"],
        "normalized_entropy": iq["normalized_entropy"],
        "js_divergence_bits": iq["js_divergence_bits"],
        "percentile": manifest["stages"]["null_comparison"]["percentile"],
        "claim_boundary": manifest["claim_boundary"],
    }


def run_all_scenarios(*, seed: int = 42) -> dict[str, Any]:
    """Run every scenario at a base seed and return a deterministic report."""
    reports = {name: run_scenario(name, seed=seed) for name in SCENARIOS}
    return {
        "seed": int(seed),
        "scenarios": reports,
        "claim_boundary": "descriptor_only_not_predictor",
        "not_predictive_claim": True,
        "research_only": True,
    }
