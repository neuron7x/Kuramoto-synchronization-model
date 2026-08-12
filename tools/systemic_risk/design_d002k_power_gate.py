# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P4 power-first gate before the event-conditioned benchmark run.

This module is the truth point of the D-002K lineage. D-002J-P7 REFUSED
on ``effect_too_small``: 102 canonical cells, Bonferroni alpha =
0.05/102 = 4.9e-4, n_min in {150, 235, 417} vs a feasible cap of 100.
D-002K's whole design hypothesis is that *narrowing the pre-registered
scope* -- ONE mechanism (``funding_liquidity_rollover``), THREE crisis
windows (CW3 / CW4 / CW5), ONE primary metric
(``pre_post_standardized_mean_shift``) -- lowers the Bonferroni
denominator from 102 to **3** and so raises the per-hypothesis alpha
enough that a *plausible, conservative* funding-liquidity effect becomes
detectable at a feasible sample.

P4 tests that hypothesis HONESTLY. There are exactly two legitimate
outcomes:

* ``POWER_GATE_PASS`` -- at the K-P0-locked Bonferroni alpha
  (0.05/3 = 0.016667) a *conservative* effect prior reaches power >= 0.8
  within a feasible sample. The P5 event-conditioned run becomes legal.
* ``POWER_GATE_REFUSED_UNDERPOWERED`` -- even with the honestly narrowed
  3-hypothesis scope the conservative effect prior cannot reach power
  >= 0.8 at the feasible sample. D-002K halts. The truthful negative is
  retained, exactly as D-002J-P7 was retained. Forward motion is a
  fresh D-002L pre-registration, NOT a P5 run and NOT a D-002J rescue.

ANTI-LAUNDERING SPINE. The Bonferroni denominator 3 is the legitimate
consequence of there being honestly FEWER pre-registered hypotheses
(1 mechanism x 3 windows x 1 primary metric = 3, locked in K-P0), NOT a
loosening of D-002J-P7's alpha = 4.9e-4 at a fixed hypothesis count.
Fewer hypotheses => a legitimately smaller denominator. Loosening alpha
at a fixed hypothesis count would be forbidden laundering and is exactly
the failure the whole stack exists to prevent. This module records that
distinction explicitly and never relaxes alpha at fixed scope, never
inflates the effect prior, never shrinks below the K-P0 3-cell lock, and
never swaps the primary metric.

The module imports no physics, no trading and no real data. It is pure
``numpy`` / ``scipy`` and is deterministic by construction. It scores
NOTHING: it computes definitions and arithmetic only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Repo anchors (read-only; never mutates any frozen artifact)
# ---------------------------------------------------------------------------

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
"""Absolute path to the GeoSync repo root (two parents above this file)."""

KP0_PREREG_REL: Final[str] = "docs/governance/D002K_PREREGISTRATION.yaml"
KP0_PRIMARY_METRIC_CONTRACT_REL: Final[str] = (
    "artifacts/d002k/prereg/d002k_primary_metric_contract_v1.json"
)
KP1_OBSERVABLE_CONTRACT_REL: Final[str] = (
    "artifacts/d002k/observables/source_observable_contract_v1.json"
)
KP2_PLACEBO_REGISTRY_REL: Final[str] = "artifacts/d002k/placebo/matched_placebo_registry_v1.json"
KP3_METRIC_CONTRACT_REL: Final[str] = "artifacts/d002k/metrics/event_metric_contract_v1.json"

# ---------------------------------------------------------------------------
# K-P0-locked design constants (read straight off the frozen pre-registration)
# ---------------------------------------------------------------------------

ALPHA_FWER: Final[float] = 0.05
"""Family-wise alpha before the K-P0-locked Bonferroni split."""

N_WINDOWS: Final[int] = 3
"""K-P0-locked pre-registered crisis windows: CW3 / CW4 / CW5 (= 3)."""

N_PRIMARY_METRICS: Final[int] = 1
"""K-P0-locked primary confirmatory endpoint count.

Exactly one: ``pre_post_standardized_mean_shift`` (K-P3 confirmatory).
"""

POWER_TARGET: Final[float] = 0.8
"""K-P0-locked target statistical power (``power_gate_policy``)."""

N_PLACEBO_REF: Final[int] = 5
"""K-P2-locked matched placebos per crisis window (the reference arm).

The K-P3 contrast is ``Delta = metric_crisis - mean(metric over the 5
K-P2 matched placebos)`` per crisis window. The reference arm therefore
has a fixed size of 5 per window.
"""

# Event-conditioned feasible cap. CW3 (US repo spike 2019), CW4 (COVID
# dash-for-cash 2020) and CW5 (UK gilt LDI 2022) are UNIQUE historical
# events. They are scored on point-in-time public observables -- there is
# exactly ONE realisation of each crisis window in recorded history; it
# cannot be re-run, re-seeded or resampled the way a synthetic substrate
# sweep can. The crisis-side replication count is therefore physically
# capped at n1 = 1 per window. This is NOT a budget guess: it is a hard
# data-availability bound of an event-conditioned design. Contrast
# D-002J-P7, whose feasible cap was n_seeds = 100 because its substrates
# were synthetic and re-runnable. The binding constraint here is not
# runtime (event-conditioned scoring is trivial) and not alpha (narrowed
# honestly to 0.05/3) -- it is that an irreproducible single crisis
# realisation cannot supply more than one crisis-side observation.
FEASIBLE_CRISIS_N1_CAP: Final[int] = 1
"""Hard event-conditioned cap on crisis-side replicates per window (= 1)."""

D002J_P7_BONFERRONI_DENOMINATOR: Final[int] = 102
"""D-002J-P7's refused Bonferroni denominator (102 canonical cells)."""

D002J_P7_ALPHA_PER_CELL: Final[float] = 0.05 / 102
"""D-002J-P7's refused per-cell alpha = 0.05/102 = 4.9e-4 (anchor)."""

D002J_P7_REFUSED_AXIS: Final[str] = "effect_too_small"
"""D-002J-P7's retained refusal axis (must NOT be undone here)."""

# Honest, conservative effect-size prior.
#
# Provenance: the funding-liquidity literature on SOFR / repo-spread
# dislocations in CW3/CW4/CW5-class events reports pre/post standardised
# funding-stress shifts of MANY pre-crisis baseline standard deviations
# (e.g. Copeland, Duffie & Yang, "Reserves Were Not So Ample", 2021, on
# the Sep-2019 SOFR/repo spike; Avalos, Ehlers & Eren, BIS Quarterly
# Review Dec-2019, on the same repo dislocation; Bank of England, "The
# Bank's response to the gilt market crisis", Dec-2022, on the 2022 LDI
# gilt episode). Those point estimates correspond to LARGE-to-extreme
# standardised effects. The honest move is NOT to plug in those large
# point estimates (that would over-power trivially and is the exact
# self-deception this gate exists to prevent). Instead the prior is
# pinned to the CONSERVATIVE lower edge: Cohen's d = 0.80, the
# conventional floor of a "large" standardised effect (Cohen 1988). This
# is deliberately the SMALLEST value the literature could justify -- it
# can only push the gate toward REFUSED, never toward a manufactured
# PASS. It is NOT inflated.
EFFECT_D_CONSERVATIVE: Final[float] = 0.80
"""Conservative (lower-edge) standardised effect prior (Cohen's d)."""

EFFECT_PROVENANCE: Final[str] = (
    "Funding-liquidity literature on SOFR/repo-spread dislocations in "
    "CW3/CW4/CW5-class events (Copeland-Duffie-Yang 2021 'Reserves Were "
    "Not So Ample'; Avalos-Ehlers-Eren BIS Quarterly Review Dec-2019; "
    "Bank of England 'The Bank's response to the gilt market crisis' "
    "Dec-2022) reports pre/post standardised funding-stress shifts of "
    "many baseline sigmas, i.e. large-to-extreme standardised effects "
    "for the pre_post_standardized_mean_shift metric family. The prior "
    "is pinned to the CONSERVATIVE lower edge -- Cohen's d = 0.80, the "
    "conventional 'large' floor (Cohen 1988) -- NOT the literature point "
    "estimate. Smaller end chosen by rule; can only push toward REFUSED."
)

EFFECT_CONSERVATIVE_BOUND: Final[str] = (
    "d = 0.80 is the conventional lower threshold of a 'large' Cohen's d "
    "(Cohen 1988). The funding-liquidity literature point estimates are "
    "multiples of baseline sigma (substantially larger); 0.80 is the "
    "smallest defensible bound and is used precisely because it cannot "
    "manufacture a PASS. Any value the literature would actually support "
    "is larger; using the floor is the conservative, anti-inflation "
    "choice mandated by the K-P0 effect_prior_source rule."
)

# ---------------------------------------------------------------------------
# Schema / decision constants
# ---------------------------------------------------------------------------

SCHEMA_DESIGN: Final[str] = "D002K-POWER-DESIGN-v1"
SCHEMA_SUMMARY: Final[str] = "D002K-POWER-SUMMARY-v1"

DECISION_PASS: Final[str] = "POWER_GATE_PASS"
DECISION_REFUSED: Final[str] = "POWER_GATE_REFUSED_UNDERPOWERED"
DECISION_INVALID: Final[str] = "POWER_GATE_INVALID"

REFUSAL_RULE: Final[str] = (
    "POWER-FIRST FAIL-CLOSED RULE (K-P0 power_gate_policy): "
    "canonical_run_authorized is True IFF, at the K-P0-locked Bonferroni "
    "alpha = 0.05 / (n_windows * n_primary_metrics) = 0.05/3 = 0.016667, "
    "the conservative honestly-sourced effect prior reaches power >= 0.8 "
    "at the feasible event-conditioned sample (crisis-side n1 <= 1 per "
    "window because CW3/CW4/CW5 are unique unrepeatable historical "
    "events; reference arm n2 = 5 K-P2 matched placebos per window). The "
    "effect prior is the conservative lower edge of the "
    "funding-liquidity literature (NOT the point estimate, NOT "
    "inflated); the Bonferroni denominator is the K-P0-locked "
    "pre-registered hypothesis count 3 (NOT a relaxation of D-002J-P7's "
    "0.05/102 at a fixed hypothesis count); the scope is the K-P0 "
    "3-cell lock (no shrink, no primary swap). If power < 0.8 at the "
    "feasible sample the gate emits POWER_GATE_REFUSED_UNDERPOWERED, "
    "status TERMINAL_REFUSED, canonical_run_authorized False, halts the "
    "lineage at P4 (next legal = a fresh D-002L pre-registration; NOT "
    "P5, NOT a D-002J resurrection) and retains this design as a "
    "truthful negative artifact. The gate NEVER loosens alpha at fixed "
    "scope, inflates the effect prior, shrinks below the K-P0 3-cell "
    "lock or swaps the primary metric to manufacture a PASS -- that is "
    "the exact self-deception D-002J-P7 was correctly refused for."
)

COMPARISON_NOTE_TO_D002J_P7: Final[str] = (
    "D-002J-P7 was correctly REFUSED at Bonferroni denominator 102 "
    "(alpha = 0.05/102 = 4.9e-4) on axis effect_too_small and stays "
    "TERMINAL_REFUSED and retained. D-002K-P4's Bonferroni denominator "
    "is 3 because K-P0 PRE-REGISTERED only 1 mechanism x 3 windows x 1 "
    "primary metric = 3 hypotheses. The smaller denominator is the "
    "legitimate consequence of fewer pre-registered hypotheses, NOT a "
    "loosening of D-002J-P7's alpha at a fixed hypothesis count. "
    "Narrowing scope is not relaxing statistics. D-002K does not "
    "un-refuse D-002J."
)


# ---------------------------------------------------------------------------
# Provenance helpers (read-only)
# ---------------------------------------------------------------------------


def _sha256_of(rel_path: str) -> str:
    """Return the sha256 hex digest of a repo-relative file (provenance)."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        msg = f"required parent artifact missing: {path}"
        raise FileNotFoundError(msg)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(rel_path: str) -> dict[str, Any]:
    """Read a repo-relative JSON artifact (read-only)."""
    path = REPO_ROOT / rel_path
    if not path.is_file():
        msg = f"required parent artifact missing: {path}"
        raise FileNotFoundError(msg)
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        msg = f"{path}: top-level JSON must be an object"
        raise ValueError(msg)
    return payload


# ---------------------------------------------------------------------------
# Effect-size prior (honest; conservative; explicitly NOT inflated)
# ---------------------------------------------------------------------------


def effect_size_prior() -> dict[str, Any]:
    """Return the honest, conservative, NON-inflated effect-size prior.

    The only legitimate sources per the K-P0 ``effect_prior_source``
    rule are (a) the magnitude implied by the funding-liquidity
    literature for SOFR/repo-spread dislocations in CW3/CW4/CW5-class
    events, expressed as a standardised Cohen's d for the
    ``pre_post_standardized_mean_shift`` primary metric, and (b) a
    conservative bound. The literature point estimates are large-to-
    extreme; this function returns the CONSERVATIVE lower edge
    (d = 0.80, the 'large' floor) precisely so it cannot manufacture a
    PASS. The ``not_inflated`` flag is always True by construction.
    """
    return {
        "cohen_d": EFFECT_D_CONSERVATIVE,
        "provenance": EFFECT_PROVENANCE,
        "conservative_bound": EFFECT_CONSERVATIVE_BOUND,
        "justification": (
            "K-P0 effect_prior_source rule forbids inflation. The "
            "funding-liquidity literature would justify a much larger d; "
            "the conservative lower edge d=0.80 is used by rule. A "
            "smaller, conservative prior can only push the honest gate "
            "toward REFUSED, never toward a manufactured PASS."
        ),
        "not_inflated": True,
    }


# ---------------------------------------------------------------------------
# Alpha policy (K-P0-locked Bonferroni denominator = n_windows x n_metrics)
# ---------------------------------------------------------------------------


def bonferroni_alpha(n_windows: int, n_primary_metrics: int) -> float:
    """Per-hypothesis Bonferroni alpha = 0.05 / (n_windows * n_metrics).

    This is the K-P0-locked ``power_gate_policy.alpha_policy``
    denominator rule verbatim. With the K-P0 lock
    (n_windows=3, n_primary_metrics=1) the denominator is 3 and the
    per-hypothesis alpha is 0.05/3 = 0.016667. The smaller denominator
    relative to D-002J-P7's 102 is the legitimate consequence of fewer
    PRE-REGISTERED hypotheses, NOT a relaxation of alpha at a fixed
    hypothesis count. Fail-closed on degenerate axis counts.
    """
    if n_windows < 1 or n_primary_metrics < 1:
        msg = (
            "Bonferroni axes must each be >= 1; got "
            f"n_windows={n_windows!r}, n_primary_metrics={n_primary_metrics!r}"
        )
        raise ValueError(msg)
    denominator = n_windows * n_primary_metrics
    return ALPHA_FWER / denominator


def _z_alpha_two_sided(alpha: float) -> float:
    """Two-sided Gaussian critical value for level ``alpha``."""
    if not 0.0 < alpha < 1.0:
        msg = f"alpha must be in (0,1), got {alpha!r}"
        raise ValueError(msg)
    return float(stats.norm.ppf(1.0 - alpha / 2.0))


def power_one_vs_reference(
    effect_d: float,
    alpha: float,
    n_crisis: int,
    n_placebo_ref: int = N_PLACEBO_REF,
) -> float:
    """Power of the crisis-vs-matched-placebo-reference contrast.

    Test family: the K-P3 confirmatory contrast is
    ``Delta = metric_crisis - mean(metric over the n_placebo_ref K-P2
    matched placebos)`` per crisis window. This is a two-independent-
    group standardised-mean comparison with arm sizes
    ``n_crisis`` (crisis side) and ``n_placebo_ref`` (matched-placebo
    reference side). For a two-sided test at level ``alpha`` against a
    standardised effect ``effect_d`` the non-centrality is

        ncp = effect_d / sqrt(1/n_crisis + 1/n_placebo_ref)

    and the achieved power is ``Phi(ncp - z_{1-alpha/2})`` (the standard
    normal-approximation power; the small-n exact non-central-t is
    strictly LOWER, so this normal approximation is the optimistic
    bound -- using it can only push the gate toward PASS, so a REFUSE
    under it is conservative and honest). Deterministic; no data, no
    clipping, no silent repair.
    """
    if effect_d <= 0.0:
        msg = f"effect_d must be > 0, got {effect_d!r}"
        raise ValueError(msg)
    if n_crisis < 1:
        msg = f"n_crisis must be >= 1, got {n_crisis!r}"
        raise ValueError(msg)
    if n_placebo_ref < 1:
        msg = f"n_placebo_ref must be >= 1, got {n_placebo_ref!r}"
        raise ValueError(msg)
    z_a = _z_alpha_two_sided(alpha)
    ncp = effect_d / float(np.sqrt(1.0 / n_crisis + 1.0 / n_placebo_ref))
    return float(stats.norm.cdf(ncp - z_a))


def n_min_for_power(
    effect_d: float,
    alpha: float,
    power: float = POWER_TARGET,
    n_placebo_ref: int = N_PLACEBO_REF,
) -> int:
    """Minimal crisis-side replicate count for power >= ``power``.

    Solves for the smallest integer crisis-side replication ``n_crisis``
    such that, with the K-P2-locked 1:n_placebo_ref reference ratio
    (the reference arm scales as ``n_placebo_ref * n_crisis`` to keep
    the K-P2 matched-placebo design ratio), the two-group standardised-
    mean test reaches the target power at the K-P0 Bonferroni alpha.
    Reported for design transparency even when the event-conditioned
    feasible cap (crisis windows are unrepeatable; n_crisis <= 1) makes
    that ``n_min`` unreachable -- that gap is precisely the refusal
    signal. Fail-closed on degenerate inputs; deterministic.
    """
    if effect_d <= 0.0:
        msg = f"effect_d must be > 0, got {effect_d!r}"
        raise ValueError(msg)
    if not 0.0 < power < 1.0:
        msg = f"power must be in (0,1), got {power!r}"
        raise ValueError(msg)
    if n_placebo_ref < 1:
        msg = f"n_placebo_ref must be >= 1, got {n_placebo_ref!r}"
        raise ValueError(msg)
    z_a = _z_alpha_two_sided(alpha)
    z_b = float(stats.norm.ppf(power))
    # Closed form for n_crisis with reference arm = n_placebo_ref * n_crisis:
    #   power=target  =>  effect_d / sqrt(1/n + 1/(r*n)) = z_a + z_b
    #   => n = ((z_a + z_b)/effect_d)^2 * (1 + 1/r)
    ratio_term = 1.0 + 1.0 / float(n_placebo_ref)
    n_float = ((z_a + z_b) / effect_d) ** 2 * ratio_term
    return int(np.ceil(n_float))


def minimum_detectable_effect(
    alpha: float,
    power: float,
    n_crisis: int,
    n_placebo_ref: int = N_PLACEBO_REF,
) -> float:
    """Smallest standardised d detectable at (alpha, power, arm sizes).

    Inverse of :func:`power_one_vs_reference`. Two-sided two-group
    normal approximation. Deterministic; fail-closed.
    """
    if not 0.0 < power < 1.0:
        msg = f"power must be in (0,1), got {power!r}"
        raise ValueError(msg)
    if n_crisis < 1 or n_placebo_ref < 1:
        msg = f"arm sizes must be >= 1; got n_crisis={n_crisis!r}, n_placebo_ref={n_placebo_ref!r}"
        raise ValueError(msg)
    z_a = _z_alpha_two_sided(alpha)
    z_b = float(stats.norm.ppf(power))
    return (z_a + z_b) * float(np.sqrt(1.0 / n_crisis + 1.0 / n_placebo_ref))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerGateResult:
    """Terminal verdict of the D-002K-P4 power-first gate."""

    decision: str
    canonical_run_authorized: bool
    power_at_feasible_n: float
    n_min: int
    alpha_per: float
    effect_d: float
    refusal_reason: str | None
    refused_axis: str | None


def power_gate_decision(
    effect_d: float,
    alpha_per: float,
    feasible_crisis_n1: int = FEASIBLE_CRISIS_N1_CAP,
    n_placebo_ref: int = N_PLACEBO_REF,
    power_target: float = POWER_TARGET,
) -> PowerGateResult:
    """Fail-closed terminal decision.

    PASS iff the honest conservative effect prior reaches power
    >= ``power_target`` at the K-P0 Bonferroni ``alpha_per`` within the
    feasible event-conditioned sample (crisis-side ``feasible_crisis_n1``
    per window, reference arm ``n_placebo_ref``). Otherwise
    REFUSED_UNDERPOWERED with the exact axis. Fail-closed on degenerate
    inputs; deterministic.
    """
    if effect_d <= 0.0:
        return PowerGateResult(
            decision=DECISION_INVALID,
            canonical_run_authorized=False,
            power_at_feasible_n=0.0,
            n_min=-1,
            alpha_per=alpha_per,
            effect_d=effect_d,
            refusal_reason=f"degenerate effect prior {effect_d!r}",
            refused_axis="invalid_effect_prior",
        )
    if not 0.0 < alpha_per < 1.0:
        return PowerGateResult(
            decision=DECISION_INVALID,
            canonical_run_authorized=False,
            power_at_feasible_n=0.0,
            n_min=-1,
            alpha_per=alpha_per,
            effect_d=effect_d,
            refusal_reason=f"degenerate alpha {alpha_per!r}",
            refused_axis="invalid_alpha",
        )
    power_feasible = power_one_vs_reference(effect_d, alpha_per, feasible_crisis_n1, n_placebo_ref)
    nmin = n_min_for_power(effect_d, alpha_per, power_target, n_placebo_ref)
    if power_feasible >= power_target:
        return PowerGateResult(
            decision=DECISION_PASS,
            canonical_run_authorized=True,
            power_at_feasible_n=power_feasible,
            n_min=nmin,
            alpha_per=alpha_per,
            effect_d=effect_d,
            refusal_reason=None,
            refused_axis=None,
        )
    reason = (
        f"At the K-P0-locked Bonferroni alpha_per={alpha_per:.6f} "
        f"(0.05/{N_WINDOWS * N_PRIMARY_METRICS}) the conservative honest "
        f"effect prior d={effect_d:g} reaches power "
        f"{power_feasible:.4f} at the feasible event-conditioned sample "
        f"(crisis-side n1={feasible_crisis_n1} per window because "
        f"CW3/CW4/CW5 are unique unrepeatable historical events; "
        f"reference arm n2={n_placebo_ref} K-P2 matched placebos) -- "
        f"far below the K-P0 power target {power_target}. The "
        f"design-transparency n_min for power>={power_target} is "
        f"{nmin} crisis-side replicates per window, which an "
        f"event-conditioned design CANNOT supply (a crisis window "
        f"happens once). This is the SAME class of honest refusal as "
        f"D-002J-P7 (effect_too_small at alpha=0.05/102). Loosening "
        f"alpha at fixed scope, inflating the effect prior, shrinking "
        f"below the K-P0 3-cell lock or swapping the primary metric to "
        f"force a PASS is forbidden. Lineage halts at P4; next legal "
        f"node is a fresh D-002L pre-registration designed against this "
        f"axis. D-002J stays REFUSED."
    )
    return PowerGateResult(
        decision=DECISION_REFUSED,
        canonical_run_authorized=False,
        power_at_feasible_n=power_feasible,
        n_min=nmin,
        alpha_per=alpha_per,
        effect_d=effect_d,
        refusal_reason=reason,
        refused_axis="effect_too_small_event_conditioned",
    )


# ---------------------------------------------------------------------------
# Artifact assembly
# ---------------------------------------------------------------------------


def build_power_design(generated_at: str) -> dict[str, Any]:
    """Build the ``D002K-POWER-DESIGN-v1`` payload (deterministic)."""
    prior = effect_size_prior()
    alpha_per = bonferroni_alpha(N_WINDOWS, N_PRIMARY_METRICS)
    gate = power_gate_decision(prior["cohen_d"], alpha_per)
    mde_feasible = minimum_detectable_effect(
        alpha_per, POWER_TARGET, FEASIBLE_CRISIS_N1_CAP, N_PLACEBO_REF
    )
    return {
        "schema_version": SCHEMA_DESIGN,
        "generated_at": generated_at,
        "study_id": "D-002K-P4",
        "node_id": "D002K-P4",
        "phase": "P4",
        "parent_kp0_prereg_path": KP0_PREREG_REL,
        "parent_kp0_prereg_sha256": _sha256_of(KP0_PREREG_REL),
        "parent_kp0_primary_metric_contract_path": (KP0_PRIMARY_METRIC_CONTRACT_REL),
        "parent_kp0_primary_metric_contract_sha256": _sha256_of(KP0_PRIMARY_METRIC_CONTRACT_REL),
        "parent_kp1_observable_contract_path": KP1_OBSERVABLE_CONTRACT_REL,
        "parent_kp1_observable_contract_sha256": _sha256_of(KP1_OBSERVABLE_CONTRACT_REL),
        "parent_kp2_placebo_registry_path": KP2_PLACEBO_REGISTRY_REL,
        "parent_kp2_placebo_registry_sha256": _sha256_of(KP2_PLACEBO_REGISTRY_REL),
        "parent_kp3_metric_contract_path": KP3_METRIC_CONTRACT_REL,
        "parent_kp3_metric_contract_sha256": _sha256_of(KP3_METRIC_CONTRACT_REL),
        "primary_metric": "pre_post_standardized_mean_shift",
        "alpha_policy": {
            "family": "bonferroni",
            "denominator": N_WINDOWS * N_PRIMARY_METRICS,
            "n_windows": N_WINDOWS,
            "n_primary_metrics": N_PRIMARY_METRICS,
            "alpha_per": alpha_per,
            "derivation": "0.05/(3×1)",
            "denominator_derives_from": (
                "K-P0-locked pre-registered hypothesis count: 1 mechanism "
                "(funding_liquidity_rollover) × 3 windows (CW3/CW4/CW5) × "
                "1 primary metric (pre_post_standardized_mean_shift) = 3 "
                "hypotheses. The smaller denominator vs D-002J-P7's 102 "
                "is the legitimate consequence of FEWER pre-registered "
                "hypotheses, NOT a relaxation of D-002J-P7's α=4.9e-4 at "
                "a fixed hypothesis count."
            ),
        },
        "effect_size_assumption": prior,
        "test_family": (
            "Crisis-vs-matched-placebo-reference contrast (K-P3): "
            "Delta = metric_crisis - mean(metric over 5 K-P2 matched "
            "placebos) per crisis window. Two-independent-group "
            "standardised-mean comparison, arm sizes n_crisis (crisis "
            "side) vs n_placebo_ref=5 (reference). Power via the "
            "two-sided normal approximation Phi(ncp - z_{1-alpha/2}) "
            "with ncp = d / sqrt(1/n_crisis + 1/n_placebo_ref); the "
            "exact small-n non-central-t power is strictly lower, so "
            "this normal bound is optimistic and a REFUSE under it is "
            "conservative."
        ),
        "n_min": gate.n_min,
        "power_target": POWER_TARGET,
        "feasible_n_cap": {
            "crisis_side_n1_per_window": FEASIBLE_CRISIS_N1_CAP,
            "reference_arm_n2_per_window": N_PLACEBO_REF,
            "justification": (
                "CW3 (US repo spike 2019), CW4 (COVID dash-for-cash "
                "2020) and CW5 (UK gilt LDI 2022) are UNIQUE historical "
                "events scored on point-in-time public observables. Each "
                "crisis window has exactly ONE realisation in recorded "
                "history; it cannot be re-run, re-seeded or resampled. "
                "The crisis-side replication count is therefore "
                "physically capped at n1=1 per window. This is a hard "
                "data-availability bound of an event-conditioned design, "
                "not a budget guess; runtime is trivial (the binding "
                "constraint is effect detectability, not compute)."
            ),
            "d002j_p7_anchor_reference": (
                "D-002J-P7's feasible cap was n_seeds=100 because its "
                "substrates were SYNTHETIC and re-runnable. D-002K is "
                "real-public-data event-conditioned, so the cap is the "
                "irreducible n1=1 per crisis window. The cap is NOT "
                "inflated to manufacture a PASS; it is the most generous "
                "value physically available (one realisation per event)."
            ),
        },
        "power_at_feasible_n": gate.power_at_feasible_n,
        "minimum_detectable_effect_at_feasible_n": mde_feasible,
        "false_negative_risk": {
            "at_feasible_n": round(1.0 - gate.power_at_feasible_n, 6),
            "interpretation": (
                "Type-II error of the crisis-vs-placebo-reference "
                "contrast at the feasible event-conditioned sample "
                "(n1=1, n2=5) at the K-P0 Bonferroni alpha for the "
                "conservative effect prior."
            ),
        },
        "refusal_rule": REFUSAL_RULE,
        "canonical_run_authorized": gate.canonical_run_authorized,
        "decision": gate.decision,
        "refused_axis": gate.refused_axis,
        "refusal_reason": gate.refusal_reason,
        "comparison_to_d002j_p7": {
            "d002j_bonferroni": D002J_P7_BONFERRONI_DENOMINATOR,
            "d002k_bonferroni": N_WINDOWS * N_PRIMARY_METRICS,
            "d002j_alpha_per_cell": D002J_P7_ALPHA_PER_CELL,
            "d002k_alpha_per": alpha_per,
            "narrowing_is_scope_not_alpha_relaxation": True,
            "d002j_refused_axis": D002J_P7_REFUSED_AXIS,
            "note": COMPARISON_NOTE_TO_D002J_P7,
        },
        "no_data_scoring_performed": True,
        "no_model_run_performed": True,
        "no_real_data": True,
        "claim_boundary": (
            "Power design only; no data scoring; alpha NOT relaxed vs "
            "D-002J-P7 (narrowing is K-P0-locked scope, not loosened "
            "stats); effect prior conservative not inflated; D-002J + "
            "K-P0..P3 frozen."
        ),
    }


def build_power_summary(generated_at: str) -> dict[str, Any]:
    """Build the ``D002K-POWER-SUMMARY-v1`` payload (deterministic)."""
    prior = effect_size_prior()
    alpha_per = bonferroni_alpha(N_WINDOWS, N_PRIMARY_METRICS)
    gate = power_gate_decision(prior["cohen_d"], alpha_per)
    return {
        "schema_version": SCHEMA_SUMMARY,
        "generated_at": generated_at,
        "study_id": "D-002K-P4",
        "phase": "P4",
        "decision": gate.decision,
        "canonical_run_authorized": gate.canonical_run_authorized,
        "alpha_per": alpha_per,
        "bonferroni_denominator": N_WINDOWS * N_PRIMARY_METRICS,
        "effect_d": prior["cohen_d"],
        "n_min": gate.n_min,
        "power_at_feasible_n": gate.power_at_feasible_n,
        "refused_axis": gate.refused_axis,
        "d002j_p7_anchor": {
            "bonferroni_denominator": D002J_P7_BONFERRONI_DENOMINATOR,
            "alpha_per_cell": D002J_P7_ALPHA_PER_CELL,
            "refused_axis": D002J_P7_REFUSED_AXIS,
            "status": "TERMINAL_REFUSED_RETAINED",
        },
        "narrowing_legitimacy_asserted": True,
        "no_canonical_run_executed": True,
    }


def _write_json(payload: dict[str, Any], rel_path: str) -> None:
    out = REPO_ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2)
        fh.write("\n")


def main(argv: list[str] | None = None) -> int:
    """CLI: assemble the design and write the two power artifacts."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m tools.systemic_risk.design_d002k_power_gate",
        description="D-002K-P4 power-first gate before benchmark run.",
    )
    parser.add_argument(
        "--generated-at",
        type=str,
        default="2026-05-15T00:00:00Z",
        help="ISO timestamp stamped into the artifacts",
    )
    args = parser.parse_args(argv)
    design = build_power_design(args.generated_at)
    summary = build_power_summary(args.generated_at)
    _write_json(design, "artifacts/d002k/power/power_design_v1.json")
    _write_json(summary, "artifacts/d002k/power/power_summary_v1.json")
    import sys

    sys.stdout.write(
        f"P4 power gate: decision={design['decision']} "
        f"canonical_run_authorized={design['canonical_run_authorized']} "
        f"alpha_per={design['alpha_policy']['alpha_per']:.6f} "
        f"effect_d={design['effect_size_assumption']['cohen_d']} "
        f"power_at_feasible_n={design['power_at_feasible_n']:.6f} "
        f"n_min={design['n_min']} "
        f"bonferroni_denominator={design['alpha_policy']['denominator']}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
