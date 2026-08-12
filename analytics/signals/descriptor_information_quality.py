# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Descriptor-only information-quality measures for the methodology stack.

This module *adds computation* to the descriptor pipeline: instead of a bare
state list + digest, it quantifies how much information a descriptor output
carries and how distinguishable it is from its declared null baseline. Every
quantity is a STRUCTURAL descriptor of an already-computed state sequence —
never a predictive, significance, or financial claim
(``claim_boundary="descriptor_only_not_predictor"``).

It consumes exactly what the rest of the stack already produces:

* ``observed_states`` / ``null_states`` — label tuples of the shape returned
  by :func:`analytics.signals.state_quantization.quantize_states`
  (``QuantizationStateResult.states``);
* ``labels`` — the closed label vocabulary those states are drawn from;
* ``observed_percentile`` — the structural mid-rank percentile from
  :func:`analytics.signals.null_comparison.compare_to_null`.

Quantities (all pure, deterministic, fail-closed):

* ``shannon_entropy_bits``  H = -Σ p·log2 p over the empirical label pmf,
  in ``[0, log2 k]``;
* ``effective_states``      ``2**H`` (perplexity), in ``[1, k]``;
* ``normalized_entropy``    ``H / log2(k)``, in ``[0, 1]`` (``0`` when k==1);
* ``js_divergence_bits``    Jensen–Shannon divergence observed‖null, the
  symmetric distinguishability of the two label distributions, in
  ``[0, 1]`` bits;
* ``distinguishability``    ``|percentile - 50| / 50`` from the null
  comparison, in ``[0, 1]``;
* ``null_effective_n``      the count of null states actually described.

High descriptor information-quality means the output is both internally
informative (entropy neither collapsed nor pure-uniform noise) and externally
distinguishable from its null (JS divergence and distinguishability margin
away from zero). The module reports the numbers; it asserts nothing about
future returns.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

import numpy as np

__all__ = [
    "CLAIM_BOUNDARY",
    "InformationQuality",
    "compute_information_quality",
    "as_metadata",
]

CLAIM_BOUNDARY = "descriptor_only_not_predictor"
_EPS = 1e-12


@dataclass(frozen=True)
class InformationQuality:
    """Immutable descriptor-only information-quality record."""

    shannon_entropy_bits: float
    effective_states: float
    normalized_entropy: float
    js_divergence_bits: float
    distinguishability: float
    null_effective_n: int
    n_states: int
    claim_boundary: str
    not_predictive_claim: bool
    not_financial_advice: bool
    research_only: bool


def _index_map(labels: Sequence[str]) -> dict[str, int]:
    if len(labels) < 1:
        raise ValueError("information-quality: labels vocabulary must be non-empty")
    index: dict[str, int] = {}
    for i, lab in enumerate(labels):
        if not isinstance(lab, str):
            raise ValueError("information-quality: labels must be strings")
        if lab in index:
            raise ValueError(f"information-quality: duplicate label {lab!r} in vocabulary")
        index[lab] = i
    return index


def _empirical_pmf(states: Sequence[str], index: Mapping[str, int]) -> np.ndarray:
    counts = np.zeros(len(index), dtype=np.float64)
    for s in states:
        if s not in index:
            raise ValueError(f"information-quality: state {s!r} not in label vocabulary")
        counts[index[s]] += 1.0
    total = counts.sum()
    if total <= 0:
        raise ValueError("information-quality: no states to describe")
    return np.asarray(counts / total, dtype=np.float64)


def _entropy_bits(pmf: np.ndarray) -> float:
    p = pmf[pmf > 0.0]
    return float(-np.sum(p * np.log2(p)))


def _js_divergence_bits(p: np.ndarray, q: np.ndarray) -> float:
    """Jensen–Shannon divergence in bits. Symmetric, bounded in ``[0, 1]``."""
    m = 0.5 * (p + q)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = a > 0.0
        return float(np.sum(a[mask] * np.log2(a[mask] / (b[mask] + _EPS))))

    js = 0.5 * _kl(p, m) + 0.5 * _kl(q, m)
    # bounds: JS divergence is analytically in [0, 1] bits; clamp float noise
    # (sub-ulp negatives from the _EPS floor) into the closed interval.
    return float(min(1.0, max(0.0, js)))


def compute_information_quality(
    observed_states: Sequence[str],
    null_states: Sequence[str],
    *,
    labels: Sequence[str],
    observed_percentile: float,
) -> InformationQuality:
    """Quantify descriptor information-quality of a state sequence vs a null.

    ``observed_states`` and ``null_states`` are label tuples drawn from the
    closed ``labels`` vocabulary. ``observed_percentile`` is the structural
    mid-rank percentile in ``[0, 100]``. Fail-closed on an empty/duplicated
    vocabulary, an out-of-vocabulary state, an empty observed sequence, or a
    percentile outside ``[0, 100]``.
    """
    if not (0.0 <= observed_percentile <= 100.0):
        raise ValueError("information-quality: percentile outside [0, 100]")
    index = _index_map(labels)
    k = len(index)

    p_obs = _empirical_pmf(observed_states, index)
    h = _entropy_bits(p_obs)
    eff = float(2.0**h)
    denom = float(np.log2(k)) if k > 1 else 1.0
    norm_h = float(h / denom) if denom > 0 else 0.0

    if len(null_states) > 0:
        p_nul = _empirical_pmf(null_states, index)
        js = _js_divergence_bits(p_obs, p_nul)
    else:
        js = 0.0

    distinguishability = float(abs(observed_percentile - 50.0) / 50.0)

    return InformationQuality(
        shannon_entropy_bits=h,
        effective_states=eff,
        normalized_entropy=norm_h,
        js_divergence_bits=js,
        distinguishability=distinguishability,
        null_effective_n=int(len(null_states)),
        n_states=int(k),
        claim_boundary=CLAIM_BOUNDARY,
        not_predictive_claim=True,
        not_financial_advice=True,
        research_only=True,
    )


def as_metadata(iq: InformationQuality) -> Mapping[str, object]:
    """Return an immutable, claim-stamped mapping of the quality record."""
    return MappingProxyType(
        {
            "shannon_entropy_bits": iq.shannon_entropy_bits,
            "effective_states": iq.effective_states,
            "normalized_entropy": iq.normalized_entropy,
            "js_divergence_bits": iq.js_divergence_bits,
            "distinguishability": iq.distinguishability,
            "null_effective_n": iq.null_effective_n,
            "n_states": iq.n_states,
            "claim_boundary": iq.claim_boundary,
            "not_predictive_claim": iq.not_predictive_claim,
            "not_financial_advice": iq.not_financial_advice,
            "research_only": iq.research_only,
        }
    )
