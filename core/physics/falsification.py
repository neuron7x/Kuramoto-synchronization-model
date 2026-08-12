# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Empirical falsification — cut beautiful but unconfirmed hypotheses.

A claim is only ``empirical`` if it rides on real, provenanced, leakage-free
data. This module makes that a hard gate: a synthetic-only witness can never
validate an empirical claim, shuffled labels destroy a real effect, leaked data
is rejected, and a missing dataset provenance fails closed. Leakage detection
reuses :mod:`core.data.leakage`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import ArrayLike

from core.data.leakage import LeakageError, assert_no_train_test_leakage

__all__ = [
    "Witness",
    "synthetic_witness",
    "empirical_witness",
    "negative_control",
    "leakage_detector",
    "rejection_report",
]


@dataclass(frozen=True)
class Witness:
    """A falsification witness: an effect size plus its evidentiary provenance.

    ``data_source`` is ``"synthetic"`` or ``"empirical"``. ``effect_size`` is the
    observed statistic. ``dataset_id`` is the provenance handle — empty means
    unprovenanced. ``shuffled`` marks a label-permuted (null) run. ``leaked`` is
    set by the leakage detector.
    """

    data_source: str
    effect_size: float
    dataset_id: str = ""
    shuffled: bool = False
    leaked: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


def synthetic_witness(effect_size: float, *, shuffled: bool = False) -> Witness:
    """Build a synthetic witness (no real-world provenance, by construction)."""
    return Witness(data_source="synthetic", effect_size=float(effect_size), shuffled=shuffled)


def empirical_witness(
    effect_size: float,
    *,
    dataset_id: str,
    shuffled: bool = False,
    leaked: bool = False,
    metadata: dict[str, object] | None = None,
) -> Witness:
    """Build an empirical witness; ``dataset_id`` is the required provenance handle."""
    return Witness(
        data_source="empirical",
        effect_size=float(effect_size),
        dataset_id=dataset_id,
        shuffled=shuffled,
        leaked=leaked,
        metadata=metadata or {},
    )


def negative_control(values: ArrayLike, labels: ArrayLike, seed: int) -> Witness:
    """Label-shuffled null: correlation between values and a permuted label vector.

    Destroys any genuine association; the resulting effect is a sample from the
    null. Returned as a ``shuffled`` empirical witness so the gate treats it as a
    negative control, never as a passing claim.
    """
    v = np.asarray(values, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    if v.shape != y.shape or v.ndim != 1 or v.size < 2:
        raise ValueError("values and labels must be matching 1-D arrays of length >= 2")
    # Explicit seeded generator (deterministic, not ambient nondeterminism).
    rng = np.random.Generator(np.random.PCG64(seed))
    permuted = rng.permutation(y)
    if float(v.std()) == 0.0 or float(permuted.std()) == 0.0:
        effect = 0.0
    else:
        effect = float(np.corrcoef(v, permuted)[0, 1])
    return Witness(
        data_source="empirical", effect_size=effect, dataset_id="shuffled-null", shuffled=True
    )


def leakage_detector(
    train_times: ArrayLike, test_times: ArrayLike, *, embargo: float = 0.0
) -> bool:
    """Return True iff the train/test split leaks (reusing core.data.leakage).

    Does not raise on leakage — it reports it, so the caller can mark the witness
    ``leaked`` and let :func:`rejection_report` reject it.
    """
    try:
        assert_no_train_test_leakage(train_times, test_times, embargo=embargo)
    except LeakageError:
        return True
    return False


def rejection_report(witness: Witness, *, min_effect: float) -> dict[str, object]:
    """Adjudicate a witness against the empirical-admission contract.

    A claim is ADMITTED only if it is an empirical witness, carries a non-empty
    dataset provenance, is not a shuffled null, is not leaked, and its effect
    magnitude clears ``min_effect``. Every other case is REJECTED with a reason.
    """
    reasons: list[str] = []
    if witness.data_source != "empirical":
        reasons.append(f"non-empirical data_source={witness.data_source!r}")
    if not witness.dataset_id:
        reasons.append("missing dataset provenance")
    if witness.shuffled:
        reasons.append("shuffled/null witness")
    if witness.leaked:
        reasons.append("leakage detected")
    if abs(witness.effect_size) < min_effect:
        reasons.append(f"effect |{witness.effect_size:.4g}| < min_effect {min_effect:.4g}")
    return {"admitted": not reasons, "reasons": reasons, "effect_size": witness.effect_size}
