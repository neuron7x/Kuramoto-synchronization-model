# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""PNCC-A — Thermodynamic Budget (Landauer-cost proxy).

EXPERIMENTAL / OPT-IN.

Part of the Physics-Native Cognitive Kernel (PNCC). This module
quantifies a *system-level* thermodynamic budget for irreversible
decisions made by the orchestrator. It does NOT measure or improve
human cognition; any cognitive-improvement claim must be a registered
EvidenceClaim in ``tacl/evidence_ledger.py`` with baseline,
intervention, control, and 95% CI.

Cost components are dimensionless proxies — NOT joules. They track
*relative* thermodynamic work of decisions so that orchestration
policies can compare "irreversible vs reversible" alternatives under
a unified penalty currency.

Public API
----------
TokenCost                 — n_input + 4·n_output (decode dominates).
LatencyCost               — log(1 + wall_time_ns / 1e6).
EntropyCost               — bits_erased · ln(2)  (Landauer-style proxy).
IrreversibleActionCost    — penalty · score, 0 if reversible.
BudgetEntry               — sum of above over a single action.
BudgetLedger              — immutable tuple of entries with horizon.
ThermodynamicBudgetConfig — penalty + horizon + fail-closed knob.

compute_token_cost / compute_latency_cost / compute_entropy_cost /
compute_irreversibility_cost / aggregate_entry / total_cost /
filter_horizon / reversible_alternative_cost — pure functions.

Invariants
----------
INV-LANDAUER-PROXY (P0, universal):
    For any irreversible action's cost C_irr and the cost C_rev of its
    hypothetical reversible alternative with identical token / latency /
    entropy components::

        C_irr >= C_rev

    with strict ``>`` whenever ``irreversibility_score > 0``. This is
    the dimensionless analogue of Landauer's bound:
    erasure-coupled work cannot be smaller than a reversible
    alternative's work for the same I/O budget.

INV-HPC1 (universal):
    Bit-identical output under fixed inputs — the module is purely
    functional and uses no global state, no RNG, no time call.

INV-HPC2 (universal):
    Finite inputs ⇒ finite outputs. NaN / Inf inputs raise; negative
    component costs raise when ``fail_on_negative_cost`` is set
    (default True) — fail-closed, no silent repair.

Source anchor
-------------
R. Landauer, "Irreversibility and heat generation in the computing
process", IBM J. Res. Dev. 5 (1961) 183. This module is a *proxy*
tracking budget over orchestration steps; it does not claim to
compute physical work, and makes no claim of empirical attainment of
the Landauer bound on any specific hardware.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "BEKENSTEIN_BIT_COEFF",
    "HBAR_J_S",
    "SPEED_OF_LIGHT_M_S",
    "bekenstein_cognitive_ceiling",
    "BudgetEntry",
    "BudgetLedger",
    "EntropyCost",
    "IrreversibleActionCost",
    "LANDAUER_LN2",
    "LatencyCost",
    "ThermodynamicBudgetConfig",
    "TokenCost",
    "aggregate_entry",
    "compute_entropy_cost",
    "compute_irreversibility_cost",
    "compute_latency_cost",
    "compute_token_cost",
    "filter_horizon",
    "reversible_alternative_cost",
    "total_cost",
]


# Landauer-style multiplicative constant. Dimensionless here — it is the
# information-theoretic conversion between "bits erased" and the proxy
# cost currency, not k_B · T · ln(2). The use of ln(2) preserves the
# Landauer mapping: 1 bit erased ↔ ln(2) units of proxy work.
LANDAUER_LN2: float = math.log(2.0)

# Physical constants in SI for INV-BEKENSTEIN-COGNITIVE.
# CODATA 2018 reduced Planck constant; speed of light is exact by 1983 SI definition.
HBAR_J_S: float = 1.054_571_817e-34
SPEED_OF_LIGHT_M_S: float = 299_792_458.0
# Bekenstein 1981 PRD 23, 287: I_max(E, R) = 2π·E·R / (ℏ·c·ln 2) bits.
# Coefficient = 2π / (ℏ·c·ln 2) → multiply by E [J] · R [m] to get bits.
BEKENSTEIN_BIT_COEFF: float = (2.0 * math.pi) / (HBAR_J_S * SPEED_OF_LIGHT_M_S * LANDAUER_LN2)

# Decoder-dominance weight for output tokens. Decode is the
# autoregressive step and dominates wall time and energy on
# transformer-class accelerators; weight 4 is a conservative
# orchestration-side default and is NOT calibrated to any specific
# vendor's energy meter.
_OUTPUT_TOKEN_WEIGHT: float = 4.0

# Latency log-scale anchor: convert ns to ms before log1p so that
# sub-ms work contributes ~ wall_ns / 1e6 (Taylor) and second-scale
# work saturates softly. log1p chosen so that 0 ns ⇒ 0 cost exactly.
_LATENCY_NS_PER_MS: float = 1.0e6


def _check_finite(value: float, name: str) -> None:
    """Fail-closed finite check. NaN / Inf → ValueError. INV-HPC2."""
    if not math.isfinite(value):
        raise ValueError(
            f"INV-HPC2 VIOLATED: {name} must be finite, got {value!r}. "
            f"Finite inputs → finite outputs is a P0 contract; no silent repair."
        )


def _check_non_negative(value: float, name: str) -> None:
    """Fail-closed non-negativity. proxy_cost components are unsigned."""
    if value < 0.0:
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: {name} must be ≥ 0, got {value!r}. "
            f"Proxy costs are unsigned; negative cost would invalidate the "
            f"reversible-vs-irreversible ordering."
        )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenCost:
    """Token-budget proxy. ``proxy_cost = n_input + 4·n_output``.

    Decode dominates: each output token triggers a full forward pass
    over the KV cache and is the orchestration-side bottleneck.
    """

    n_input_tokens: int
    n_output_tokens: int
    proxy_cost: float


@dataclass(frozen=True, slots=True)
class LatencyCost:
    """Wall-time proxy. ``proxy_cost = log1p(wall_ns / 1e6)``.

    log1p ensures ``wall_ns == 0 ⇒ proxy_cost == 0`` exactly and
    saturates softly at second / minute scales.
    """

    wall_time_ns: int
    p99_ns: int
    proxy_cost: float


@dataclass(frozen=True, slots=True)
class EntropyCost:
    """Information-erasure proxy. ``proxy_cost = bits_erased · ln(2)``.

    ``bits_consumed`` is recorded for accounting; only ``bits_erased``
    enters the Landauer-style proxy. ``bits_erased == 0`` ⇒ entropy
    proxy is exactly zero.
    """

    bits_consumed: float
    bits_erased: float
    proxy_cost: float


@dataclass(frozen=True, slots=True)
class IrreversibleActionCost:
    """Irreversibility proxy. Zero if reversible; else ``penalty · score``.

    The penalty is the configured ``irreversibility_penalty``.
    ``irreversibility_score`` ∈ [0, 1] caps the proxy at the penalty.
    """

    is_irreversible: bool
    irreversibility_score: float
    proxy_cost: float


@dataclass(frozen=True, slots=True)
class BudgetEntry:
    """One action's full thermodynamic-budget record."""

    action_id: str
    timestamp_ns: int
    token: TokenCost
    latency: LatencyCost
    entropy: EntropyCost
    irreversible: IrreversibleActionCost
    total_proxy_cost: float


@dataclass(frozen=True, slots=True)
class BudgetLedger:
    """Immutable ledger of budget entries within a horizon."""

    entries: tuple[BudgetEntry, ...]
    horizon_ns: int


@dataclass(frozen=True, slots=True)
class ThermodynamicBudgetConfig:
    """Configuration for the thermodynamic-budget proxy.

    Attributes
    ----------
    irreversibility_penalty:
        Multiplicative penalty (≥ 0) applied to the irreversibility
        score when an action is marked irreversible.
    max_horizon_ns:
        Sliding-window horizon for ledger filtering; default 60 s.
    fail_on_negative_cost:
        If True, every aggregation re-asserts non-negativity of the
        sum cost. Set False only for explicitly justified test cases.
    """

    irreversibility_penalty: float = 1.0
    max_horizon_ns: int = 60_000_000_000  # 60 s
    fail_on_negative_cost: bool = True


# ---------------------------------------------------------------------------
# Pure cost computations
# ---------------------------------------------------------------------------


def compute_token_cost(n_in: int, n_out: int) -> TokenCost:
    """Token proxy. Both counts must be finite non-negative integers."""
    if n_in < 0:
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: n_in must be ≥ 0, got {n_in}. "
            f"Token counts are unsigned; no silent clamp."
        )
    if n_out < 0:
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: n_out must be ≥ 0, got {n_out}. "
            f"Token counts are unsigned; no silent clamp."
        )
    cost = float(n_in) + _OUTPUT_TOKEN_WEIGHT * float(n_out)
    _check_finite(cost, "token.proxy_cost")
    return TokenCost(n_input_tokens=n_in, n_output_tokens=n_out, proxy_cost=cost)


def compute_latency_cost(wall_ns: int, p99_ns: int) -> LatencyCost:
    """Latency proxy. ``wall_ns`` is the cost driver; ``p99_ns`` is recorded."""
    if wall_ns < 0:
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: wall_ns must be ≥ 0, got {wall_ns}. "
            f"Wall time is unsigned; no silent clamp."
        )
    if p99_ns < 0:
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: p99_ns must be ≥ 0, got {p99_ns}. "
            f"p99 latency is unsigned; no silent clamp."
        )
    cost = math.log1p(float(wall_ns) / _LATENCY_NS_PER_MS)
    _check_finite(cost, "latency.proxy_cost")
    return LatencyCost(wall_time_ns=wall_ns, p99_ns=p99_ns, proxy_cost=cost)


def compute_entropy_cost(bits_consumed: float, bits_erased: float) -> EntropyCost:
    """Entropy proxy. ``bits_erased == 0`` ⇒ ``proxy_cost == 0`` exactly."""
    _check_finite(bits_consumed, "bits_consumed")
    _check_finite(bits_erased, "bits_erased")
    _check_non_negative(bits_consumed, "bits_consumed")
    _check_non_negative(bits_erased, "bits_erased")
    cost = bits_erased * LANDAUER_LN2
    _check_finite(cost, "entropy.proxy_cost")
    return EntropyCost(
        bits_consumed=bits_consumed,
        bits_erased=bits_erased,
        proxy_cost=cost,
    )


def compute_irreversibility_cost(
    is_irreversible: bool,
    score: float,
    cfg: ThermodynamicBudgetConfig,
) -> IrreversibleActionCost:
    """Irreversibility proxy.

    Reversible actions are cost-free in this dimension.
    Irreversible actions pay ``penalty · score`` with ``score ∈ [0, 1]``.
    """
    _check_finite(score, "irreversibility_score")
    if not (0.0 <= score <= 1.0):
        raise ValueError(
            f"INV-LANDAUER-PROXY VIOLATED: irreversibility_score must be in "
            f"[0, 1], got {score!r}. Score is a saturating fraction; no clamp."
        )
    _check_finite(cfg.irreversibility_penalty, "irreversibility_penalty")
    _check_non_negative(cfg.irreversibility_penalty, "irreversibility_penalty")

    if is_irreversible:
        cost = cfg.irreversibility_penalty * score
    else:
        cost = 0.0
    _check_finite(cost, "irreversible.proxy_cost")
    _check_non_negative(cost, "irreversible.proxy_cost")
    return IrreversibleActionCost(
        is_irreversible=is_irreversible,
        irreversibility_score=score,
        proxy_cost=cost,
    )


def aggregate_entry(
    action_id: str,
    timestamp_ns: int,
    token: TokenCost,
    lat: LatencyCost,
    ent: EntropyCost,
    irr: IrreversibleActionCost,
) -> BudgetEntry:
    """Sum component proxies into a single ``BudgetEntry``."""
    if not action_id:
        raise ValueError("action_id must be a non-empty string; no silent default.")
    if timestamp_ns < 0:
        raise ValueError(
            f"timestamp_ns must be ≥ 0, got {timestamp_ns}. "
            f"Use a monotonic clock (e.g. time.monotonic_ns)."
        )
    total = token.proxy_cost + lat.proxy_cost + ent.proxy_cost + irr.proxy_cost
    _check_finite(total, "BudgetEntry.total_proxy_cost")
    _check_non_negative(total, "BudgetEntry.total_proxy_cost")
    return BudgetEntry(
        action_id=action_id,
        timestamp_ns=timestamp_ns,
        token=token,
        latency=lat,
        entropy=ent,
        irreversible=irr,
        total_proxy_cost=total,
    )


def total_cost(ledger: BudgetLedger) -> float:
    """Sum of ``total_proxy_cost`` over all entries in the ledger."""
    if not ledger.entries:
        return 0.0
    s = 0.0
    for entry in ledger.entries:
        _check_finite(entry.total_proxy_cost, f"entry[{entry.action_id}].total_proxy_cost")
        s += entry.total_proxy_cost
    _check_finite(s, "ledger.total_cost")
    return s


def filter_horizon(ledger: BudgetLedger, now_ns: int) -> BudgetLedger:
    """Return a new ledger keeping only entries within ``horizon_ns`` of ``now_ns``.

    Pure: no in-place mutation. ``horizon_ns`` is propagated unchanged.
    """
    if now_ns < 0:
        raise ValueError(f"now_ns must be ≥ 0, got {now_ns}.")
    if ledger.horizon_ns < 0:
        raise ValueError(f"horizon_ns must be ≥ 0, got {ledger.horizon_ns}.")
    cutoff = now_ns - ledger.horizon_ns
    kept = tuple(e for e in ledger.entries if e.timestamp_ns >= cutoff)
    return BudgetLedger(entries=kept, horizon_ns=ledger.horizon_ns)


def reversible_alternative_cost(
    entry: BudgetEntry,
    cfg: ThermodynamicBudgetConfig,
) -> float:
    """Hypothetical cost if the same action had been reversible.

    Token / latency / entropy components are *identical* (same I/O,
    same wall time, same bits erased) — only the irreversibility
    component is dropped. This is the C_rev side of INV-LANDAUER-PROXY.
    """
    _ = cfg  # cfg accepted for symmetry; reversible cost is intrinsically cfg-free
    cost = entry.token.proxy_cost + entry.latency.proxy_cost + entry.entropy.proxy_cost
    _check_finite(cost, "reversible_alternative_cost")
    _check_non_negative(cost, "reversible_alternative_cost")
    return cost


def bekenstein_cognitive_ceiling(radius_m: float, energy_J: float) -> float:
    """INV-BEKENSTEIN-COGNITIVE: maximum information (bits) for a region.

    Bekenstein 1981 (Phys. Rev. D 23, 287): for any system contained in a
    sphere of radius R with total energy E, the information content is
    bounded by I ≤ 2π·E·R / (ℏ·c·ln 2). Saturated by black holes
    (Bekenstein-Hawking entropy). Holographic principle ('t Hooft 1993,
    Susskind 1995) generalizes the bound to all gravitational systems.

    Inputs are SI (radius in metres, energy in joules). Output is bits.

    Fail-closed:
    - non-finite or negative inputs → ValueError (INV-HPC2)
    - radius_m == 0 OR energy_J == 0 → 0.0 bits (degenerate region)

    The function is stateless, dimensionally consistent, and identical to
    the closed-form `BEKENSTEIN_BIT_COEFF * energy_J * radius_m` once the
    fail-closed envelope is satisfied.
    """
    _check_finite(radius_m, "radius_m")
    _check_finite(energy_J, "energy_J")
    _check_non_negative(radius_m, "radius_m")
    _check_non_negative(energy_J, "energy_J")
    bits: float = BEKENSTEIN_BIT_COEFF * energy_J * radius_m
    _check_finite(bits, "bekenstein_cognitive_ceiling")
    return bits
