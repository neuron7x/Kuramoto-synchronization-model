# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G — Non-degenerate null mechanisms (M1 + M6 + M2).

Rationale
=========
D-002C attempt-2 (RUN_ID ``d002c_canonical_attempt_2_20260512T160318Z``)
emitted ``tier=D002C_REDESIGN_INSUFFICIENT_AT_TESTED_BUDGET`` because
at λ=0 the locked paired-CRN protocol produces
``K_precursor == K_baseline`` bit-identically. The permutation null
audit then collapses to ``p=1.0`` for those 9 λ=0 cells.

D-002G fixes this with three pre-committed mechanisms locked in
``docs/governance/D002G_PREREGISTRATION.yaml``:

* **M1 (primary)** — independent-seed null cohort. For seed ``s`` the
  precursor cohort uses ``s``; the null cohort uses
  ``s + null_seed_offset`` (offset=10000 per
  ``reproducibility.null_seed_offset``). At λ=0 the two K matrices are
  drawn independently — bit-identity is broken while H0 ("no precursor
  effect at λ=0") is preserved.

* **M6 (supplementary)** — placebo coupling. The precursor injection
  is applied to a RANDOM subset of off-diagonal edges with the SAME
  Frobenius-norm shift as the locked precursor (top-10% κ edges for
  ricci, inter-block edges for block_structured, locked sites for
  temporal_coupling). The metric SHOULD NOT detect this fake injection
  — if it does, the metric is a false-positive prone detector that
  responds to any energy injection rather than to substrate topology.

* **M2 (fallback)** — topology-preserving shuffle. Used only for
  substrates declared M1-INELIGIBLE (``block_structured``,
  ``temporal_coupling`` — seed-deterministic at λ=0). At λ>0 the
  precursor matrix is decomposed as ``K_p = K_0 + ΔK``; the support
  positions of ΔK (the precursor's topology) are HELD FIXED while the
  payload values at those positions are permuted by a deterministic
  RNG. The topology hash is preserved bit-identically; the payload
  assignment changes whenever the support carries ≥ 2 distinct values.
  Substrates whose ΔK is constant-valued at every privileged position
  yield ``INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL`` — the topology-
  preserving edge-weight shuffle cannot construct a non-degenerate
  null on a constant-valued payload, and the verifier refuses the cell
  fail-closed rather than emit a no-op null.

Strict scope
============
Mechanism implementation ONLY. NO sweep execution. NO claim layer.
NO threshold edits. NO substrate API surgery — this module CONSUMES
the existing ``Substrate`` protocol from :mod:`d002c_substrates`
without modification.

Data contract
=============
A :class:`NullRealization` carries the K_baseline matrix produced by
the chosen mechanism plus full content-addressed provenance:
``payload_sha256`` is sha256 over canonical JSON of
``{strategy, base_seed, null_seed, lambda_value, substrate_id, N,
metadata, K_flat_sha}`` where ``K_flat_sha`` is sha256 over
``K_baseline.tobytes()`` with shape+dtype tag. Same inputs → same
sha across machines and processes.

The K_baseline shape is ``(N, N)``. The substrate API produces a
``(T_HORIZON, N, N)`` trajectory; this module returns the static
slice at ``t=PRE_EVENT_START_QUARTER`` (well-defined because at λ=0
the substrate's ``K_baseline`` is broadcast-identical across the
time axis; for M6 we synthesise a single-slice placebo K).

Phase 0 verification (Phase 0a / 0b / 0c) is implemented in
:mod:`d002g_phase0_verification`. R2-B aggregation is implemented in
:mod:`d002g_r2b_gate`. This module is purely the realisation layer.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
from numpy.typing import NDArray

from .d002c_substrates import (
    BLOCK_FRACTIONS,
    PRECURSOR_INJECTION_WINDOW,
    Substrate,
    SubstrateRealization,
)

# ---------------------------------------------------------------------------
# Locked constants (frozen in docs/governance/D002G_PREREGISTRATION.yaml)
# ---------------------------------------------------------------------------

#: ``reproducibility.null_seed_offset`` in the pre-registration. The M1
#: null cohort draws an independent realisation at the offset seed.
NULL_SEED_OFFSET: Final[int] = 10000

#: ``reproducibility.r2_b_random_site_seed`` in the pre-registration.
#: Combined with ``base_seed`` via :func:`deterministic_mix` to seed the
#: M6 placebo edge-selection RNG.
R2_B_RANDOM_SITE_SEED: Final[int] = 99

#: Strategy string literals carried in the payload + downstream null
#: audit. The legacy value ``D002C_PAIRED_CRN_LEGACY`` is used by the
#: ``d002c_sweep_runner`` extension in Phase 7 for backward
#: compatibility with pre-A2 emissions; it is NOT a D-002G mechanism
#: and is intentionally not part of this Literal.
NullStrategy = Literal[
    "M1_INDEPENDENT_SEED",
    "M6_PLACEBO_COUPLING",
    "M2_TOPOLOGY_PRESERVING_SHUFFLE",
    "M3_TOPOLOGY_CONDITIONED",
]

#: Locked salt mixed with ``base_seed`` to produce the M6 RNG.
M6_PLACEBO_SALT: Final[int] = R2_B_RANDOM_SITE_SEED

#: Locked random_site-style salt for the M2 topology-preserving shuffle.
#: NOT an arithmetic offset (those collide trivially under stride
#: aliasing per the P1 Strike-R5 attack). The actual RNG seed is
#: ``deterministic_mix(base_seed, M2_PLACEBO_SALT)`` xor-mixed further
#: with the per-cell ``null_seed`` override when the caller supplies
#: one. Value 211 is a small prime distinct from
#: :data:`R2_B_RANDOM_SITE_SEED` (99) and :data:`NULL_SEED_OFFSET`
#: (10000) — domain-separation against M1 and M6 RNG streams.
M2_PLACEBO_SALT: Final[int] = 211

#: P3 salt for the M2 node-payload sub-domain shuffle. Distinct prime
#: (313) from the edge_weight salt (211) and the M6 salt (99). Used by
#: :func:`_default_null_seed_m2_node_payload` to derive a domain-
#: separated RNG stream — required by §11 closure rule (4) so the
#: node-payload shuffle never aliases the edge-weight stream under
#: stride attack (Strike-R5 anti-pattern). Honest stance: even though
#: every prereg-scoped substrate currently fails admissibility at the
#: contract level, the salt is locked so the verifier's RNG is
#: deterministic by construction — INELIGIBLE verdicts are themselves
#: bit-identical-replay invariants.
M2_NODE_PAYLOAD_SALT: Final[int] = 313

#: P3 salt for the M2 injection-sequence sub-domain shuffle. Distinct
#: prime (419) from edge_weight (211), node_payload (313), and M6 (99).
#: Same domain-separation rationale as :data:`M2_NODE_PAYLOAD_SALT`.
M2_INJECTION_SEQUENCE_SALT: Final[int] = 419

#: D-002G-M3 salt — topology-conditioned independent realisation under
#: matched-density resampling. Locked at 523 in the M3 pre-registration
#: (``docs/governance/D002G_P3_M3_PREREGISTRATION.md`` §9). A distinct
#: prime from the prior salts (99, 211, 313, 419) — full domain
#: separation across the M1/M6/M2 sub-domain and M3 RNG streams so the
#: per-mechanism realisation never aliases another mechanism under
#: stride / collision attacks (Strike-R5 anti-pattern).
M3_TOPOLOGY_CONDITIONED_SALT: Final[int] = 523

#: Strategy string constant emitted in :class:`NullRealization.metadata`
#: under the ``null_strategy`` key for an M3 realisation. Mirrors the
#: literal entry in :data:`NullStrategy`. Tests assert this constant
#: matches the literal value byte-exact.
M3_NULL_STRATEGY: Final[str] = "M3_TOPOLOGY_CONDITIONED"

#: M3 generator cap. The matched-resample inner loop attempts up to
#: this many rebalance iterations before raising
#: :class:`M3GeneratorDivergentError`. The cap is a LOCKED constant —
#: changing it requires a fresh M4 pre-registration per the M3 pre-reg
#: §9.1 forbidden refinement scope.
M3_GENERATOR_MAX_ITERATIONS: Final[int] = 100

#: M3 precursor-specificity ensemble size. Verifier draws this many
#: independent precursor seeds (0..N-1) and counts pairs whose
#: marginals differ above the marginal tolerance. ≥ 50% of pairs must
#: differ for the marginal to be precursor-specific. Locked.
M3_PRECURSOR_ENSEMBLE_SIZE: Final[int] = 100

#: M3 tolerance constants — declared BEFORE any substrate evaluation
#: per the M3 pre-registration §9.1 ("tolerance constants pre-declared
#: in the M3 implementation PR body BEFORE any canonical result is
#: inspected"). The pre-declared values:
#:
#:   * ``M3_TOL_MARGINAL``         = 0.05 (general marginal-match band).
#:   * ``M3_TOL_NON_DEGENERATE``   = 1e-3 (min Frobenius distance K_null
#:     vs K_p; below this the null is statistically indistinguishable
#:     from the precursor and the realisation is REFUSED fail-closed).
#:   * ``M3_TOL_DENSITY``          = 0.02 (density relative error).
#:   * ``M3_TOL_SPECTRAL_RADIUS``  = 0.05 (spectral radius / N relative
#:     error).
#:   * ``M3_TOL_DEGREE_WASSERSTEIN`` = 0.05 (degree-sequence Wasserstein-1
#:     distance normalised by the precursor mean degree).
#:
#: These are HONEST defaults. If they prove too strict and every
#: substrate fails, that is a TRUTHFUL FINDING per the M3 pre-reg's
#: §7 forbidden interpretation list — relaxation post-hoc to engineer
#: ELIGIBLE_M3 is forbidden by the discipline. Tolerance relaxation
#: requires a fresh M4 pre-registration, NOT an in-PR edit.
M3_TOL_MARGINAL: Final[float] = 0.05
M3_TOL_NON_DEGENERATE: Final[float] = 1e-3
M3_TOL_DENSITY: Final[float] = 0.02
M3_TOL_SPECTRAL_RADIUS: Final[float] = 0.05
M3_TOL_DEGREE_WASSERSTEIN: Final[float] = 0.05

_VALID_STRATEGIES: Final[frozenset[str]] = frozenset(
    {
        "M1_INDEPENDENT_SEED",
        "M6_PLACEBO_COUPLING",
        "M2_TOPOLOGY_PRESERVING_SHUFFLE",
        "M3_TOPOLOGY_CONDITIONED",
    }
)

#: Status literals for :class:`M2EligibilityVerdict`. The verifier emits
#: exactly one of these for every (substrate, N, λ, base_seed) it is
#: asked about. ``ELIGIBLE_M2`` is the only edge-weight status that
#: admits a subsequent call to :func:`realize_null` with strategy
#: ``"M2_TOPOLOGY_PRESERVING_SHUFFLE"`` and ``shuffle_domain
#: ="edge_weight"``. The node-payload and injection-sequence
#: sub-domain literals (P3) carry their own ELIGIBLE / INELIGIBLE /
#: INDETERMINATE families — exactly one of those is ELIGIBLE_* per
#: sub-domain and the rest fail-closed.
M2EligibilityStatus = Literal[
    "ELIGIBLE_M2",
    "INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY",
    "INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL",
    "INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED",
    "INDETERMINATE_M2_PROVENANCE_MISSING",
    # P3 — M2 node-payload sub-domain verdict literals (PR
    # `feat/x10r-d002g-p3-constant-payload-null-recovery`). Each
    # status communicates a specific failure mode of the node-payload
    # admissibility ladder; ELIGIBLE_M2_NODE_PAYLOAD is the ONLY one
    # that admits a node-payload shuffle realisation downstream.
    "ELIGIBLE_M2_NODE_PAYLOAD",
    "INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL",
    "INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN",
    "INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED",
    "INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING",
    # P3 — M2 injection-sequence sub-domain verdict literals.
    # ELIGIBLE_M2_INJECTION_SEQUENCE is the only admissible status.
    # CONTRACT_VIOLATION fires when permuting the event order would
    # break the substrate's stated lag-coupling contract — for
    # `temporal_coupling` whose injection IS the entire causal
    # hypothesis, reordering destroys substrate identity and the
    # cell is REFUSED rather than silently emitting a no-op or a
    # semantically-fake null.
    "ELIGIBLE_M2_INJECTION_SEQUENCE",
    "INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE",
    "INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION",
    "INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN",
    "INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING",
]

_M2_ELIGIBLE: Final[str] = "ELIGIBLE_M2"
_M2_NODE_PAYLOAD_ELIGIBLE: Final[str] = "ELIGIBLE_M2_NODE_PAYLOAD"
_M2_INJECTION_SEQUENCE_ELIGIBLE: Final[str] = "ELIGIBLE_M2_INJECTION_SEQUENCE"


class BitIdenticalNullError(RuntimeError):
    """M1 produced ``K_null == K_precursor`` bit-identically.

    Raised when the chosen substrate happens to be insensitive to the
    seed argument at the requested λ. The caller MUST tag such
    (substrate, N) cells as M1-INELIGIBLE and either fall back to the
    M2 topology-preserving shuffle (pre-registration fallback policy)
    or escalate. Silently accepting a bit-identical M1 null would
    reintroduce the exact pathology M1 was designed to remove.
    """


class M2TopologyMutationError(RuntimeError):
    """M2 shuffle mutated the precursor topology mask.

    Raised when the topology hash of the precursor ΔK support and the
    topology hash of the constructed ``K_null`` ΔK support disagree.
    By construction the M2 shuffle relocates payload values WITHIN the
    fixed support set, so the support mask must be invariant. A
    detected mutation is an internal-invariant violation — never a
    user-fixable input error — and the cell is REFUSED fail-closed.

    The verifier emits the same status as ``INELIGIBLE_M2_TOPOLOGY_
    MUTATION_DETECTED`` rather than raising; this exception is raised
    only on the realization-layer post-check, after the verifier has
    already approved the cell.
    """


# Forward declaration: :class:`M2NotEligibleError` carries an
# :class:`M2EligibilityVerdict` instance. The dataclass is defined
# further down (alongside :class:`NullRealization`) so its strict-typed
# fields can reference :data:`M2EligibilityStatus`; the exception's
# constructor uses a string-form forward reference to avoid the
# circular declaration order. Mypy / ruff see the actual symbol once
# the module finishes loading.
class M2NotEligibleError(RuntimeError):
    """M2 verifier returned a non-ELIGIBLE verdict for this cell.

    Carries the :class:`M2EligibilityVerdict` as ``self.verdict`` so
    callers can introspect ``status`` and ``eligibility_reason`` for
    structured diagnostics. Raised by :func:`realize_null` when invoked
    with strategy ``"M2_TOPOLOGY_PRESERVING_SHUFFLE"`` on a cell the
    verifier refuses; the M2 fallback is fail-closed by contract — no
    silent downgrade to M1 / M6 / no-op.
    """

    def __init__(self, verdict: Any) -> None:
        # ``verdict`` is duck-typed as :class:`M2EligibilityVerdict`
        # (defined below). We avoid the forward type annotation to
        # keep static analysers happy with the declaration-order
        # constraint.
        super().__init__(
            f"M2 verdict {verdict.status!r} for substrate "
            f"{verdict.substrate_id!r} at N={verdict.N}: "
            f"{verdict.eligibility_reason}"
        )
        self.verdict = verdict


class M6InsufficientCandidatePool(RuntimeError):
    """M6 placebo-coupling candidate edge pool is smaller than support.

    Raised when the off-support pool of upper-triangle edges (i.e.
    ``upper_triangle ∖ original_support``) has fewer entries than the
    privileged ΔK support size. Sampling cannot proceed without either
    (a) reusing privileged sites (forbidden — re-introduces support
    leakage, the very pathology this fix removes) or (b) sampling with
    replacement (forbidden — breaks M6 distinct-edge contract).

    Fail-closed semantics: the cell is REFUSED at the realisation
    layer; callers must tag it ``M6-INELIGIBLE_CANDIDATE_POOL_TOO_SMALL``
    and either widen N or escalate to the M2 fallback per the locked
    pre-registration §4 fallback policy.
    """


class D002GNullInvalid(ValueError):
    """Bad input to :func:`realize_null` / :func:`deterministic_mix`."""


# ---------------------------------------------------------------------------
# Deterministic seed mixing
# ---------------------------------------------------------------------------


def deterministic_mix_multi(*words: int) -> int:
    """Deterministic uint63 hash of N signed-int64 words for RNG seeding.

    Generalisation of :func:`deterministic_mix` to N inputs. Used by the
    M3 mechanism per its pre-reg §5 signature:

    ``deterministic_mix(base_seed, M3_TOPOLOGY_CONDITIONED_SALT,
    null_seed, substrate_id_hash, N, lambda_value_bits)``

    The 2-arg public ``deterministic_mix`` keeps its original signature
    and ABI for M1/M2/M6 callers; this multi-arg helper is M3-specific.
    Both functions sha256 over big-endian-packed int64 words and return
    the low 63 bits — same primitive, parameterised over arity.

    Raises
    ------
    D002GNullInvalid
        Any word outside the signed-int64 range, or fewer than 2 words.
    """
    if len(words) < 2:
        raise D002GNullInvalid(f"deterministic_mix_multi requires >= 2 words; got {len(words)}")
    packed = bytearray()
    for w in words:
        if not (-(2**63) <= int(w) < 2**63):
            raise D002GNullInvalid(f"word must fit in int64; got {w!r}")
        packed.extend(struct.pack(">q", int(w)))
    digest = hashlib.sha256(bytes(packed)).digest()
    head = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return int(head & ((1 << 63) - 1))


def deterministic_mix(base_seed: int, salt: int) -> int:
    """Deterministic uint63 hash of (base_seed, salt) for RNG seeding.

    The M6 placebo mechanism needs an RNG seed that is:

      * **Deterministic** — same (base_seed, salt) → same seed across
        machines / processes / runs.
      * **Distinct across base_seeds** — two cohort seeds that share
        the same salt MUST produce different M6 RNG seeds so the
        per-seed placebo realisations are independent.
      * **Distinct across salts** — domain-separation tag.

    Implementation: pack ``(base_seed, salt)`` as two int64 big-endian
    words, sha256, take the low 63 bits as the seed (numpy's
    ``default_rng`` accepts non-negative int up to ``2**63 - 1``).

    Python's built-in ``hash()`` is forbidden — it is salted per-process
    by PYTHONHASHSEED and would break determinism across processes.

    Raises
    ------
    D002GNullInvalid
        ``base_seed`` or ``salt`` outside the signed-int64 range.
    """
    if not (-(2**63) <= int(base_seed) < 2**63):
        raise D002GNullInvalid(f"base_seed must fit in int64; got {base_seed!r}")
    if not (-(2**63) <= int(salt) < 2**63):
        raise D002GNullInvalid(f"salt must fit in int64; got {salt!r}")
    packed = struct.pack(">qq", int(base_seed), int(salt))
    digest = hashlib.sha256(packed).digest()
    head = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return int(head & ((1 << 63) - 1))


# ---------------------------------------------------------------------------
# Canonical JSON + sha helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _canonical_json(payload: dict[str, Any]) -> str:
    """Stable canonical JSON (sort_keys, tight separators, NaN sentinel)."""

    def _walk(x: Any) -> Any:
        if isinstance(x, float):
            if math.isnan(x):
                return "NaN"
            if math.isinf(x):
                return "Infinity" if x > 0 else "-Infinity"
            return x
        if isinstance(x, (list, tuple)):
            return [_walk(v) for v in x]
        if isinstance(x, dict):
            return {str(k): _walk(v) for k, v in x.items()}
        return x

    return json.dumps(_walk(payload), sort_keys=True, separators=(",", ":"))


def _K_flat_sha(K: NDArray[np.float64]) -> str:
    """sha256 over K_baseline.tobytes() with shape+dtype tag.

    The tag prefix prevents ``(N, N)`` and ``(N*N,)`` arrays with the
    same byte content from colliding. float64 is mandatory; any other
    dtype is refused by :func:`realize_null`.
    """
    if K.dtype != np.float64:
        raise D002GNullInvalid(f"K_baseline.dtype must be float64; got {K.dtype}")
    tag = f"shape={tuple(K.shape)};dtype=float64".encode("utf-8")
    h = hashlib.sha256()
    h.update(tag)
    h.update(K.tobytes(order="C"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# NullRealization data contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NullRealization:
    """Frozen output of one M1 / M6 null realisation.

    Fields
    ------
    K_baseline
        The N×N float64 matrix the downstream Kuramoto integrator must
        consume as the null cohort's K. The existing substrate API
        emits a ``(T_HORIZON, N, N)`` trajectory; this dataclass
        carries the static slice. Callers that integrate the
        trajectory should broadcast back to ``(T_HORIZON, N, N)``.
    strategy
        Which mechanism produced this realisation.
    base_seed
        The precursor cohort seed this null is paired to.
    null_seed
        The seed actually used to draw the null. For M1 this is
        ``base_seed + NULL_SEED_OFFSET``; for M6 it is
        :func:`deterministic_mix` of ``(base_seed, M6_PLACEBO_SALT)``.
    lambda_value
        The cell coordinate. M1 is locked to λ=0 in the canonical
        sweep but the realisation function accepts any λ ≥ 0 so
        Phase 0b's H0-preservation check can probe arbitrary cells.
        M6 requires lambda_value > 0.
    substrate_id
        From :attr:`Substrate.id`.
    N
        Cohort size. Inherited from the canonical sweep N_grid.
    metadata
        Strategy-specific provenance:
          * M1: ``{}`` (no extra state).
          * M6: ``{"placebo_edges_count": int,
                   "placebo_frobenius_norm": float,
                   "precursor_frobenius_norm": float}``
        Merged with any ``metadata_extra`` from the caller.
    generated_at
        ISO-8601 UTC wallclock at construction. Excluded from the sha.
    payload_sha256
        Content-addressed sha (see :func:`_realization_sha`).
    """

    K_baseline: NDArray[np.float64]
    strategy: NullStrategy
    base_seed: int
    null_seed: int
    lambda_value: float
    substrate_id: str
    N: int
    metadata: dict[str, Any] = field(default_factory=dict)
    generated_at: str = ""
    payload_sha256: str = ""


def _realization_sha(
    *,
    strategy: NullStrategy,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    substrate_id: str,
    N: int,
    metadata: Mapping[str, Any],
    K_baseline: NDArray[np.float64],
) -> str:
    """sha256 over the canonical-JSON payload of the load-bearing fields.

    Excludes ``generated_at`` and ``payload_sha256`` so the sha is
    invariant under wallclock differences.
    """
    payload: dict[str, Any] = {
        "strategy": str(strategy),
        "base_seed": int(base_seed),
        "null_seed": int(null_seed),
        "lambda_value": float(lambda_value),
        "substrate_id": str(substrate_id),
        "N": int(N),
        "metadata": dict(metadata),
        "K_flat_sha": _K_flat_sha(K_baseline),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Substrate-API adapter
# ---------------------------------------------------------------------------


def _baseline_slice(realisation: SubstrateRealization, *, t: int = 0) -> NDArray[np.float64]:
    """Static K_baseline slice (N, N) from a (T_HORIZON, N, N) realisation.

    At λ=0 the existing substrate API broadcasts ``K_baseline[0]``
    across time. Phase 0a / 0b only need the static slice.
    """
    K = np.asarray(realisation.K_baseline[t], dtype=np.float64)
    _refuse_if_non_square(K)
    return K


def _refuse_if_non_square(K: NDArray[np.float64]) -> None:
    if K.ndim != 2:
        raise D002GNullInvalid(f"K must be 2-D; got ndim={K.ndim}")
    if K.shape[0] != K.shape[1]:
        raise D002GNullInvalid(f"K must be square; got shape {K.shape}")


# ---------------------------------------------------------------------------
# M1 — independent-seed null
# ---------------------------------------------------------------------------


def _realize_m1(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Draw the M1 independent-seed null K_baseline.

    The null cohort uses the SAME substrate API at the SAME λ as the
    precursor cohort. Bit-identity is broken by the seed offset; H0
    is preserved because the substrate draws ω + θ_0 + integrator
    stream from independent randomness while keeping the same baseline
    distribution.

    Raises
    ------
    BitIdenticalNullError
        If the precursor and null K_baseline slices are
        ``np.array_equal`` identical (substrate insensitive to seed
        at this (N, λ)).
    """
    precursor_real = substrate.realize(N=N, lambda_=lambda_value, seed=base_seed)
    null_real = substrate.realize(N=N, lambda_=lambda_value, seed=null_seed)
    K_p = _baseline_slice(precursor_real)
    K_n = _baseline_slice(null_real)
    if np.array_equal(K_p, K_n):
        raise BitIdenticalNullError(
            f"M1 produced bit-identical K_baseline for substrate "
            f"{substrate.id!r} at N={N}, lambda_={lambda_value}, "
            f"base_seed={base_seed}, null_seed={null_seed}. The "
            "substrate is insensitive to the seed argument at this "
            "(N, lambda_); tag the cell M1-INELIGIBLE and fall back "
            "to mechanism M2 (topology-preserving shuffle) per the "
            "D-002G pre-registration §4 fallback policy."
        )
    return K_n, {}


# ---------------------------------------------------------------------------
# M6 — placebo coupling
# ---------------------------------------------------------------------------


def _upper_tri_indices_count(N: int) -> int:
    return (N * (N - 1)) // 2


def _realize_m6(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Draw the M6 placebo-coupling K_baseline.

    Procedure (matches ``D002G_NONDEGENERATE_NULL_DESIGN.md §5`` and
    ``D002G_PREREGISTRATION.yaml § supplementary_null``):

    1. Realise the precursor at ``(N, lambda_value, base_seed)`` and
       extract ``K_p = K_precursor[t_inj]`` where ``t_inj`` is inside
       the locked ``PRECURSOR_INJECTION_WINDOW``.
    2. Realise the baseline at the same seed with ``lambda_=0`` and
       extract ``K_0 = K_baseline[t_inj]``.
    3. ΔK = K_p − K_0. The support of ΔK is the substrate's
       privileged sites (top-10% κ for Ricci, inter-block for
       block_structured, sin-modulated baseline for temporal).
    4. Permute the support: select ``|support(ΔK)|`` distinct
       upper-triangle indices uniformly at random (no privileged
       sites) using an RNG seeded by :func:`deterministic_mix`. The
       magnitude distribution of ΔK is applied to those random edges
       — Frobenius norm of ΔK preserved exactly (to within rounding).
    5. K_placebo = K_0 + symmetric ΔK_placebo.

    Returns
    -------
    (K_placebo, metadata)
        ``K_placebo`` is N×N float64 symmetric. ``metadata`` carries
        ``placebo_edges_count``, ``placebo_frobenius_norm``, and
        ``precursor_frobenius_norm``.
    """
    precursor_real = substrate.realize(N=N, lambda_=lambda_value, seed=base_seed)
    baseline_real = substrate.realize(N=N, lambda_=0.0, seed=base_seed)
    inject_t = int(next(iter(PRECURSOR_INJECTION_WINDOW)))
    K_p = np.asarray(precursor_real.K_precursor[inject_t], dtype=np.float64)
    K_0 = np.asarray(baseline_real.K_baseline[inject_t], dtype=np.float64)
    _refuse_if_non_square(K_p)
    _refuse_if_non_square(K_0)
    if not (np.all(np.isfinite(K_p)) and np.all(np.isfinite(K_0))):
        raise D002GNullInvalid("M6: K_precursor / K_baseline contains non-finite")

    delta = K_p - K_0
    iu_r, iu_c = np.triu_indices(N, k=1)
    delta_upper = delta[iu_r, iu_c]
    support_mask = np.abs(delta_upper) > 1e-12
    n_support = int(np.count_nonzero(support_mask))

    precursor_frobenius = float(np.linalg.norm(delta))

    if n_support == 0 or precursor_frobenius == 0.0:
        # No precursor delta at this (N, lambda) — placebo is the
        # baseline itself (no fake injection to add). Clean corner case.
        # P0-1: emit the same support-exclusion metadata schema as the
        # non-degenerate branch so downstream audits read a uniform
        # contract.
        return K_0.copy(), {
            "placebo_edges_count": 0,
            "placebo_frobenius_norm": 0.0,
            "precursor_frobenius_norm": 0.0,
            "null_strategy": "M6_PLACEBO_COUPLING",
            "original_support_count": 0,
            "placebo_support_count": 0,
            "placebo_overlap_count": 0,
            "placebo_overlap_forbidden": True,
            "candidate_pool_size": int(_upper_tri_indices_count(N)),
        }

    n_total_upper = _upper_tri_indices_count(N)
    if n_support > n_total_upper:
        raise D002GNullInvalid(
            f"M6: support size {n_support} exceeds upper-triangle count {n_total_upper}"
        )

    # P0-1 Codex review fix: privileged ΔK support MUST be excluded from
    # the placebo sampling pool. Sampling from the full upper triangle
    # would let placebo edges overlap original support, retaining true
    # precursor topology in the "placebo" cohort and biasing R2-B toward
    # optimism. Build the candidate pool as upper_triangle ∖ support and
    # sample only from the off-support indices. Fail-closed if the pool
    # is smaller than the support size — the cell is REFUSED rather
    # than silently allowing overlap.
    candidate_indices = np.flatnonzero(~support_mask)
    original_support_indices = np.flatnonzero(support_mask)
    candidate_pool_size = int(candidate_indices.size)
    if candidate_pool_size < n_support:
        raise M6InsufficientCandidatePool(
            f"M6: candidate edge pool too small for support exclusion: "
            f"|upper_triangle ∖ support|={candidate_pool_size} < "
            f"|support|={n_support} at N={N}. Cell is M6-INELIGIBLE; "
            f"escalate to M2 topology-preserving shuffle per the "
            f"D-002G pre-registration §4 fallback policy."
        )

    rng = np.random.default_rng(int(null_seed))
    chosen = rng.choice(candidate_indices, size=n_support, replace=False)
    magnitudes = delta_upper[support_mask].copy()
    rng.shuffle(magnitudes)

    # P0-1 audit: verify zero overlap between chosen placebo sites and
    # the privileged support BEFORE building the placebo matrix. This is
    # a defensive invariant — the candidate-pool exclusion above already
    # guarantees zero overlap by construction; the explicit check
    # converts the property into an observable failure mode for the
    # downstream Phase 0 / R2-B audits.
    overlap_count = int(np.intersect1d(chosen, original_support_indices).size)
    if overlap_count != 0:
        raise D002GNullInvalid(
            f"M6: placebo-vs-support overlap_count={overlap_count} ≠ 0 "
            f"despite candidate-pool exclusion. This is an internal "
            f"invariant violation; refusing the cell."
        )

    placebo_upper = np.zeros(n_total_upper, dtype=np.float64)
    placebo_upper[chosen] = magnitudes

    delta_placebo = np.zeros_like(K_0, dtype=np.float64)
    delta_placebo[iu_r, iu_c] = placebo_upper
    delta_placebo = delta_placebo + delta_placebo.T  # symmetrize

    K_placebo = K_0 + delta_placebo

    placebo_frobenius = float(np.linalg.norm(delta_placebo))

    if precursor_frobenius > 0.0:
        rel_err = abs(placebo_frobenius - precursor_frobenius) / precursor_frobenius
        if rel_err > 1e-9:
            raise D002GNullInvalid(
                f"M6: Frobenius preservation violated: "
                f"precursor={precursor_frobenius:.6e}, "
                f"placebo={placebo_frobenius:.6e}, rel_err={rel_err:.3e}"
            )

    return K_placebo, {
        "placebo_edges_count": int(n_support),
        "placebo_frobenius_norm": placebo_frobenius,
        "precursor_frobenius_norm": precursor_frobenius,
        # P0-1 Codex review fix: explicit metadata so downstream audits
        # can verify the support-exclusion contract was honoured.
        "null_strategy": "M6_PLACEBO_COUPLING",
        "original_support_count": int(n_support),
        "placebo_support_count": int(n_support),
        "placebo_overlap_count": int(overlap_count),
        "placebo_overlap_forbidden": True,
        "candidate_pool_size": int(candidate_pool_size),
    }


# ---------------------------------------------------------------------------
# M2 — topology-preserving shuffle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class M2EligibilityVerdict:
    """Frozen verdict from :func:`verify_m2_eligibility`.

    Fields
    ------
    status
        One of :data:`M2EligibilityStatus`. Only ``"ELIGIBLE_M2"``
        admits a subsequent :func:`realize_null` call with strategy
        ``"M2_TOPOLOGY_PRESERVING_SHUFFLE"``.
    substrate_id
        From :attr:`Substrate.id`.
    N
        Cohort size.
    preserved_topology_hash
        sha256 over the canonical-JSON of the precursor ΔK upper-
        triangle boolean support mask. The realization-layer post-
        check requires the constructed K_null's ΔK support hash to
        match this value bit-identically.
    shuffle_domain
        Which payload domain the shuffle is applied to. The current
        P2/M2 implementation supports ``"edge_weight"`` only; the
        other two values are reserved for future M2 sub-domains and
        will raise :class:`D002GNullInvalid` if the verifier is asked
        to evaluate them in this PR.
    candidate_pool_size
        Number of upper-triangle positions in the ΔK support — the
        positions over which the shuffle permutes payload values.
        Always equals ``support_mask.sum()`` for the precursor at the
        verified cell coordinate.
    eligibility_reason
        Single-line human-readable explanation of the verdict.
        Cross-checked by the tests so the format stays stable.
    metadata
        Strategy-specific diagnostics:
          * ``distinct_values_count``: number of distinct ΔK payload
            values at support positions. If ``< 2`` the shuffle is a
            no-op and the verdict is
            ``INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL``.
          * ``support_count``: ``candidate_pool_size`` (duplicate for
            downstream consumers).
          * ``injection_window_index``: which time slice of the
            substrate trajectory was sampled for ΔK construction.
    """

    status: M2EligibilityStatus
    substrate_id: str
    N: int
    preserved_topology_hash: str
    shuffle_domain: Literal["node_payload", "edge_weight", "injection_sequence"]
    candidate_pool_size: int
    eligibility_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _topology_hash(K: NDArray[np.float64]) -> str:
    """sha256 over the canonical-JSON of K's upper-triangle nonzero mask.

    ``K`` is interpreted as a payload-delta matrix (e.g. ΔK = K_p − K_0
    OR ΔK = K_null − K_0). The hash domain is the BOOLEAN PATTERN of
    where the delta is nonzero on the strict upper triangle — i.e. the
    edge-set topology the precursor injection touches. Two matrices
    with identical support patterns hash identically regardless of
    their payload magnitudes; a single bit flipped in the support
    pattern produces a different hash.

    The threshold for "nonzero" is ``1e-12`` to match :func:`_realize_m6`
    and match what downstream substrate gates accept as "no precursor
    delta" (gate G10).

    Raises
    ------
    D002GNullInvalid
        ``K`` not square or not float64.
    """
    if K.dtype != np.float64:
        raise D002GNullInvalid(f"K must be float64; got {K.dtype}")
    _refuse_if_non_square(K)
    iu_r, iu_c = np.triu_indices(K.shape[0], k=1)
    mask = np.abs(K[iu_r, iu_c]) > 1e-12
    payload = {
        "domain": "topology_upper_triangle_nonzero_mask",
        "N": int(K.shape[0]),
        # Pack the boolean mask as a compact "0"/"1" string — stable,
        # canonical, machine-and-process invariant.
        "mask": "".join("1" if b else "0" for b in mask.tolist()),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _build_precursor_delta(
    substrate: Substrate,
    *,
    base_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[
    NDArray[np.float64],
    NDArray[np.float64],
    NDArray[np.float64],
    int,
]:
    """Return ``(K_0, K_p, ΔK, inject_t)`` for the M2 shuffle.

    Both substrate calls use the SAME ``base_seed``. For substrates
    that are seed-deterministic at λ=0 (block_structured,
    temporal_coupling) the ``K_0`` baseline is independent of the seed
    by construction; the relevant payload variation lives entirely in
    ``ΔK = K_p − K_0`` at the canonical injection window slice.

    Raises
    ------
    D002GNullInvalid
        Non-finite K, non-square K, or substrate API contract
        violation that bubbles up.
    """
    precursor_real = substrate.realize(N=N, lambda_=lambda_value, seed=base_seed)
    baseline_real = substrate.realize(N=N, lambda_=0.0, seed=base_seed)
    inject_t = int(next(iter(PRECURSOR_INJECTION_WINDOW)))
    K_p = np.asarray(precursor_real.K_precursor[inject_t], dtype=np.float64)
    K_0 = np.asarray(baseline_real.K_baseline[inject_t], dtype=np.float64)
    _refuse_if_non_square(K_p)
    _refuse_if_non_square(K_0)
    if not (np.all(np.isfinite(K_p)) and np.all(np.isfinite(K_0))):
        raise D002GNullInvalid("M2: K_precursor / K_baseline contains non-finite")
    delta = K_p - K_0
    return K_0, K_p, delta, inject_t


def verify_m2_eligibility(
    substrate: Substrate,
    *,
    N: int,
    lambda_value: float,
    base_seed: int,
    null_seed: int | None = None,
) -> M2EligibilityVerdict:
    """Pre-check whether (substrate, N, λ, seed) admits an M2 null.

    The verifier mirrors :func:`_realize_m2` except it does NOT emit a
    :class:`NullRealization`. It is the cheap pre-check that callers
    invoke BEFORE attempting realization, so a cell can be tagged
    ``M2-INELIGIBLE`` and routed to escalation without paying the
    realization-layer cost twice.

    Verdict ladder (first matching condition wins):

    1. ``INDETERMINATE_M2_PROVENANCE_MISSING`` — substrate refuses to
       construct the precursor (e.g. ``SubstrateInvalid`` from a gate
       failure). The verifier cannot decide eligibility because the
       precursor itself is malformed; escalate to the substrate owner.
    2. ``INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY`` — ΔK upper-triangle
       support is empty. There is no topology to preserve; the M2
       shuffle has nothing to shuffle.
    3. ``INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL`` — ΔK support has
       fewer than 2 distinct payload values. A permutation of one
       repeated value yields the identical ΔK — the M2 shuffle is
       a no-op and the resulting K_null would equal K_p
       bit-identically (recreating the exact pathology M2 was
       designed to remove).
    4. ``INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED`` — the dry-run
       shuffle's reconstructed support mask hashes differently from
       the precursor's. Defensive: by construction the support is
       held fixed, so this should never fire; if it does, the
       implementation has an invariant break and the cell is REFUSED.
    5. ``ELIGIBLE_M2`` — all of the above checks pass.

    ``null_seed`` is optional. When ``None`` the verifier uses the
    locked formula :func:`_default_null_seed` for M2; when supplied
    the verifier uses the override (tests probing edge cases).

    Notes
    -----
    The verifier is callable WITHOUT performing the actual null
    realization. Phase 0 / canonical preflight code paths use it as a
    cheap eligibility gate before incurring the realization cost.
    """
    if not math.isfinite(lambda_value) or lambda_value <= 0.0:
        # M2 needs ΔK = K_p − K_0; at λ=0 ΔK is zero by gate G10 and
        # there is nothing to shuffle. Same fail-closed semantics as
        # the realization-layer M6 lambda gate.
        raise D002GNullInvalid("verify_m2_eligibility requires lambda_value > 0 (M2 shuffles ΔK)")
    if int(N) < 2:
        raise D002GNullInvalid(f"N must be >= 2; got {N!r}")

    sub_id = str(substrate.id)
    try:
        K_0, K_p, delta, inject_t = _build_precursor_delta(
            substrate,
            base_seed=int(base_seed),
            lambda_value=float(lambda_value),
            N=int(N),
        )
    except Exception as exc:  # noqa: BLE001
        # Substrate construction failed → eligibility is INDETERMINATE
        # (we cannot decide without the precursor). Wrap rather than
        # propagate so the verifier's contract is "always returns a
        # verdict" — the caller routes INDETERMINATE_M2_* upward.
        return M2EligibilityVerdict(
            status="INDETERMINATE_M2_PROVENANCE_MISSING",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash="",
            shuffle_domain="edge_weight",
            candidate_pool_size=0,
            eligibility_reason=(f"substrate.realize raised {type(exc).__name__}: {exc!s}"),
            metadata={
                "exception_type": type(exc).__name__,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
            },
        )

    iu_r, iu_c = np.triu_indices(int(N), k=1)
    delta_upper = delta[iu_r, iu_c]
    support_mask = np.abs(delta_upper) > 1e-12
    n_support = int(np.count_nonzero(support_mask))

    if n_support < 1:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_INSUFFICIENT_TOPOLOGY",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=_topology_hash(delta),
            shuffle_domain="edge_weight",
            candidate_pool_size=0,
            eligibility_reason=(
                "ΔK upper-triangle support is empty at this (N, λ, seed); "
                "M2 has no topology to preserve"
            ),
            metadata={
                "support_count": 0,
                "distinct_values_count": 0,
                "injection_window_index": int(inject_t),
                "lambda_value": float(lambda_value),
            },
        )

    support_values = delta_upper[support_mask]
    # Round to 1e-12 to match the support-mask threshold; otherwise
    # floating-point dithering inside a constant-valued payload would
    # spuriously inflate the distinct-value count.
    distinct_count = int(np.unique(np.round(support_values, 12)).size)

    if distinct_count < 2:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=_topology_hash(delta),
            shuffle_domain="edge_weight",
            candidate_pool_size=int(n_support),
            eligibility_reason=(
                f"ΔK support carries {distinct_count} distinct payload "
                "value(s); a permutation of constant-valued payload "
                "is a no-op — K_null would equal K_p bit-identically"
            ),
            metadata={
                "support_count": int(n_support),
                "distinct_values_count": int(distinct_count),
                "injection_window_index": int(inject_t),
                "lambda_value": float(lambda_value),
            },
        )

    # Dry-run shuffle: relocate values within the fixed support; verify
    # the reconstructed ΔK has bit-identical topology hash. Uses the
    # same RNG-seeding contract as :func:`_realize_m2` so the verifier
    # observes exactly the realisation that downstream code would emit.
    eff_null_seed = (
        int(null_seed) if null_seed is not None else _default_null_seed_m2(int(base_seed))
    )
    rng = np.random.default_rng(eff_null_seed)
    perm = rng.permutation(support_values)
    dry_delta_upper = np.zeros_like(delta_upper)
    dry_delta_upper[support_mask] = perm
    dry_delta = np.zeros_like(delta)
    dry_delta[iu_r, iu_c] = dry_delta_upper
    dry_delta = dry_delta + dry_delta.T

    pre_hash = _topology_hash(delta)
    post_hash = _topology_hash(dry_delta)
    if pre_hash != post_hash:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=pre_hash,
            shuffle_domain="edge_weight",
            candidate_pool_size=int(n_support),
            eligibility_reason=(
                "dry-run shuffle mutated topology hash; this is an "
                "internal-invariant violation (support set must be "
                "fixed by construction) — cell REFUSED"
            ),
            metadata={
                "support_count": int(n_support),
                "distinct_values_count": int(distinct_count),
                "pre_shuffle_topology_hash": pre_hash,
                "post_shuffle_topology_hash": post_hash,
                "injection_window_index": int(inject_t),
                "lambda_value": float(lambda_value),
            },
        )

    return M2EligibilityVerdict(
        status="ELIGIBLE_M2",
        substrate_id=sub_id,
        N=int(N),
        preserved_topology_hash=pre_hash,
        shuffle_domain="edge_weight",
        candidate_pool_size=int(n_support),
        eligibility_reason=(
            f"support count {n_support} with {distinct_count} distinct "
            "values; topology hash invariant under dry-run shuffle"
        ),
        metadata={
            "support_count": int(n_support),
            "distinct_values_count": int(distinct_count),
            "injection_window_index": int(inject_t),
            "lambda_value": float(lambda_value),
            "base_seed": int(base_seed),
            "null_seed": int(eff_null_seed),
        },
    )


def _default_null_seed_m2(base_seed: int) -> int:
    """Locked M2 null-seed formula.

    Deterministic mix of ``base_seed`` with :data:`M2_PLACEBO_SALT`
    (211). NOT an arithmetic offset — that primitive is collision-
    prone under stride aliasing (per the P1 Strike-R5 attack on M1's
    offset=10000). The hash-based mix gives statistical independence
    of the M2 RNG stream from M1 (``base_seed + 10000``) and M6
    (``deterministic_mix(base_seed, 99)``).
    """
    return deterministic_mix(int(base_seed), M2_PLACEBO_SALT)


def _realize_m2(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Construct the M2 topology-preserving shuffle K_null.

    Procedure (matches ``D002G_M2_TOPOLOGY_PRESERVING_NULL.md`` and
    the locked pre-registration §4 fallback policy):

    1. Compute ``K_0 = substrate.realize(N, λ=0, seed=base_seed)``
       static slice at the canonical injection window index.
    2. Compute ``K_p = substrate.realize(N, λ=lambda_value,
       seed=base_seed)`` static slice at the same index.
    3. ΔK = K_p − K_0. Support mask = (|ΔK| > 1e-12) on the upper
       triangle.
    4. Seed ``rng = np.random.default_rng(null_seed)`` where
       ``null_seed = deterministic_mix(base_seed, M2_PLACEBO_SALT)``
       under the locked formula, or the caller's override.
    5. Permute the support's payload values via ``rng.permutation``;
       reassign permuted values to the SAME support positions.
    6. K_null = K_0 + symmetrised ΔK_shuffled.
    7. Verify topology-hash invariance — raise
       :class:`M2TopologyMutationError` if the reconstructed support
       hash drifted from the precursor's. This is an internal-invariant
       check; the verifier already screens this case as INELIGIBLE.

    Returns
    -------
    (K_null, metadata)
        ``K_null`` is N×N float64 symmetric. ``metadata`` carries the
        full M2 provenance schema (eligibility status stamp, preserved
        topology hash, shuffle domain, candidate pool size, null seed,
        substrate-anchored injection window).

    Raises
    ------
    M2TopologyMutationError
        Reconstructed support hash ≠ precursor support hash. Internal
        invariant violation; downstream callers tag the cell
        ``INELIGIBLE_M2_TOPOLOGY_MUTATION_DETECTED`` rather than
        accepting the realization.
    D002GNullInvalid
        Substrate produced non-finite K or shape violation; or the
        support carries fewer than 2 distinct values (degenerate
        shuffle pool — should have been screened by the verifier).
    """
    K_0, _K_p, delta, inject_t = _build_precursor_delta(
        substrate,
        base_seed=int(base_seed),
        lambda_value=float(lambda_value),
        N=int(N),
    )

    iu_r, iu_c = np.triu_indices(int(N), k=1)
    delta_upper = delta[iu_r, iu_c]
    support_mask = np.abs(delta_upper) > 1e-12
    n_support = int(np.count_nonzero(support_mask))

    if n_support < 1:
        raise D002GNullInvalid(
            f"M2: ΔK upper-triangle support empty at substrate "
            f"{substrate.id!r}, N={N}, lambda_={lambda_value}, "
            f"seed={base_seed} — verifier should have screened this"
        )

    support_values = delta_upper[support_mask]
    distinct_count = int(np.unique(np.round(support_values, 12)).size)
    if distinct_count < 2:
        raise D002GNullInvalid(
            f"M2: degenerate shuffle pool ({distinct_count} distinct "
            "values across support); verifier should have screened "
            "this — would yield K_null == K_p bit-identically"
        )

    pre_hash = _topology_hash(delta)

    rng = np.random.default_rng(int(null_seed))
    perm = rng.permutation(support_values)

    shuffled_upper = np.zeros_like(delta_upper)
    shuffled_upper[support_mask] = perm

    delta_shuffled = np.zeros_like(delta)
    delta_shuffled[iu_r, iu_c] = shuffled_upper
    delta_shuffled = delta_shuffled + delta_shuffled.T  # symmetrise

    K_null = K_0 + delta_shuffled

    post_hash = _topology_hash(delta_shuffled)
    if pre_hash != post_hash:
        raise M2TopologyMutationError(
            f"M2: topology hash drifted under shuffle "
            f"(pre={pre_hash}, post={post_hash}); internal-invariant "
            "violation — cell REFUSED"
        )

    metadata: dict[str, Any] = {
        "null_strategy": "M2_TOPOLOGY_PRESERVING_SHUFFLE",
        "null_seed": int(null_seed),
        "preserved_topology_hash": pre_hash,
        "shuffle_domain": "edge_weight",
        "eligibility_status": _M2_ELIGIBLE,
        "candidate_pool_size": int(n_support),
        "support_count": int(n_support),
        "distinct_values_count": int(distinct_count),
        "injection_window_index": int(inject_t),
        "lambda_value": float(lambda_value),
    }
    return K_null, metadata


# ---------------------------------------------------------------------------
# P3 — M2 node-payload sub-domain (constant-payload substrate adjudication)
# ---------------------------------------------------------------------------
#
# Honest scope. The P3 sub-domains are an admissibility adjudication for
# substrates whose ΔK upper-triangle support carries a single distinct
# payload value (`block_structured`, `temporal_coupling` in the locked
# pre-registration grid). The P2 edge-weight shuffle returned
# INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL on those — every permutation of
# `{v, v, …, v}` is a no-op. P3 asks two narrow questions:
#
#   * Does the substrate expose a per-NODE attribute that can be
#     permuted under a fixed topology hash? — :func:`verify_m2_node_payload_eligibility`.
#   * Does the substrate expose a per-EVENT injection sequence that
#     can be reordered without violating its lag-coupling contract? —
#     :func:`verify_m2_injection_sequence_eligibility`.
#
# A NEGATIVE result (INELIGIBLE / INDETERMINATE / MISSING_DOMAIN) is
# the safe outcome. The verifier MUST NOT fabricate eligibility by
# inventing an artificial domain when the substrate exposes none.


def _default_null_seed_m2_node_payload(base_seed: int) -> int:
    """Locked node-payload sub-domain null-seed formula.

    Deterministic mix of ``base_seed`` with :data:`M2_NODE_PAYLOAD_SALT`
    (313). NOT an arithmetic offset (same Strike-R5 anti-pattern rule
    as the edge-weight stream). Distinct prime salt from M1 / M6 / M2
    edge-weight / M2 injection-sequence — fully domain-separated.
    """
    return deterministic_mix(int(base_seed), M2_NODE_PAYLOAD_SALT)


def _default_null_seed_m2_injection_sequence(base_seed: int) -> int:
    """Locked injection-sequence sub-domain null-seed formula.

    Deterministic mix of ``base_seed`` with
    :data:`M2_INJECTION_SEQUENCE_SALT` (419). NOT an arithmetic offset.
    """
    return deterministic_mix(int(base_seed), M2_INJECTION_SEQUENCE_SALT)


def _extract_node_payload(
    substrate: Substrate,
    *,
    base_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], int]:
    """Extract a per-node payload vector and its topology context.

    Returns
    -------
    (K_0, delta, node_payload, inject_t)
        ``K_0`` and ``delta`` are the static baseline / ΔK slices from
        :func:`_build_precursor_delta`. ``node_payload`` is the
        per-node row-sum of the upper-triangle of ΔK — a stand-in for
        a per-node intensity attribute. ``inject_t`` is the canonical
        injection-window slice index.

    Rationale
    ---------
    None of the prereg-scoped substrates expose an explicit per-node
    attribute via the :class:`SubstrateRealization` schema; the
    closest topology-agnostic candidate is the per-node row-sum of
    the (symmetric) ΔK. This is a SIGNAL the verifier CAN test for
    admissibility — it neither invents nor promotes node-payload
    eligibility. If the substrate were extended to carry an explicit
    per-node attribute, this extraction would be re-wired without
    changing the verdict ladder.

    The function is intentionally bare: the verifier owns the
    admissibility ladder (degeneracy / topology-coupling / missing
    domain). This helper is a domain extractor only.
    """
    K_0, _K_p, delta, inject_t = _build_precursor_delta(
        substrate,
        base_seed=int(base_seed),
        lambda_value=float(lambda_value),
        N=int(N),
    )
    # The per-node "intensity" payload is the row-sum of ΔK. For a
    # symmetric ΔK this equals 2 * sum of upper-triangle entries
    # incident on node i — well-defined and topology-agnostic.
    node_payload = np.asarray(delta.sum(axis=1), dtype=np.float64)
    return K_0, delta, node_payload, inject_t


def verify_m2_node_payload_eligibility(
    substrate: Substrate,
    *,
    N: int,
    lambda_value: float,
    base_seed: int,
    null_seed: int | None = None,
) -> M2EligibilityVerdict:
    """Pre-check whether (substrate, N, λ, seed) admits an M2 node-payload null.

    Verdict ladder (first matching condition wins):

    1. ``INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING`` — substrate
       refuses to construct the precursor (gate failure / non-finite).
    2. ``INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN`` — the substrate
       does not expose any per-node attribute that could be permuted
       independently of topology. In the current prereg-scoped grid
       this fires when the substrate has no row-sum variability AND
       no other per-node attribute is exposed.
    3. ``INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL`` — the node-
       payload pool has fewer than 2 distinct values. A permutation
       of constant values is a no-op.
    4. ``INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED`` — permuting
       node identities mutates the topology hash of ``K_0`` (or of
       ``ΔK``). This means the per-node attribute is NOT decoupled
       from the substrate's topology — the M2 contract forbids any
       permutation that mutates topology semantics.
    5. ``ELIGIBLE_M2_NODE_PAYLOAD`` — all checks pass.

    Notes
    -----
    `block_structured` couples its block label assignment to the
    inter-block lift topology — permuting node identities relocates
    the lift to new (i, j) pairs and mutates the ΔK support pattern.
    The verdict for that substrate is therefore TOPOLOGY_COUPLED on
    the locked prereg grid. `temporal_coupling` inherits the same
    coupling via its block-structured base. `ricci_flow` has random
    adjacency whose hash is mutated by any non-identity node
    permutation — also TOPOLOGY_COUPLED on the K_0 mask. This is the
    HONEST outcome: there is no admissible node-payload domain on
    any of the three prereg-scoped substrates today, and the
    verifier records that fact rather than fabricating eligibility.
    """
    if not math.isfinite(lambda_value) or lambda_value <= 0.0:
        raise D002GNullInvalid(
            "verify_m2_node_payload_eligibility requires lambda_value > 0 "
            "(M2 shuffles ΔK; node-payload sub-domain inherits the contract)"
        )
    if int(N) < 2:
        raise D002GNullInvalid(f"N must be >= 2; got {N!r}")

    sub_id = str(substrate.id)
    try:
        K_0, delta, node_payload, inject_t = _extract_node_payload(
            substrate,
            base_seed=int(base_seed),
            lambda_value=float(lambda_value),
            N=int(N),
        )
    except Exception as exc:  # noqa: BLE001
        return M2EligibilityVerdict(
            status="INDETERMINATE_M2_NODE_PAYLOAD_PROVENANCE_MISSING",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash="",
            shuffle_domain="node_payload",
            candidate_pool_size=0,
            eligibility_reason=(f"substrate.realize raised {type(exc).__name__}: {exc!s}"),
            metadata={
                "exception_type": type(exc).__name__,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
            },
        )

    # Decision: a substrate "exposes" a node-payload domain iff the
    # row-sum carries non-trivial information beyond the topology of
    # ΔK itself. The current substrate API does NOT expose any other
    # per-node attribute; if the row-sum is identically zero (ΔK
    # empty), we record MISSING_DOMAIN — there is nothing to permute.
    if not np.any(np.abs(node_payload) > 1e-12):
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_NODE_PAYLOAD_MISSING_DOMAIN",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=_topology_hash(delta),
            shuffle_domain="node_payload",
            candidate_pool_size=0,
            eligibility_reason=(
                "substrate exposes no per-node payload attribute distinct "
                "from topology (ΔK row-sums are uniformly zero at this cell)"
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "injection_window_index": int(inject_t),
                "pool_count": 0,
                "distinct_values_count": 0,
            },
        )

    distinct = int(np.unique(np.round(node_payload, 12)).size)
    if distinct < 2:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=_topology_hash(delta),
            shuffle_domain="node_payload",
            candidate_pool_size=int(N),
            eligibility_reason=(
                f"node-payload pool carries {distinct} distinct value(s); "
                "permutation of constant payload is a no-op"
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "injection_window_index": int(inject_t),
                "pool_count": int(N),
                "distinct_values_count": int(distinct),
            },
        )

    # Topology-coupling probe: permute node identities deterministically
    # and check whether the resulting K_0 / ΔK topology hashes match
    # the originals. If ANY non-identity permutation mutates either
    # hash, the per-node attribute is structurally coupled to topology
    # — node-payload permutation cannot honour the M2 contract.
    eff_null_seed = (
        int(null_seed)
        if null_seed is not None
        else _default_null_seed_m2_node_payload(int(base_seed))
    )
    rng = np.random.default_rng(eff_null_seed)
    perm = rng.permutation(int(N))
    K_0_perm = K_0[np.ix_(perm, perm)]
    delta_perm = delta[np.ix_(perm, perm)]
    pre_K0_hash = _topology_hash(K_0)
    pre_delta_hash = _topology_hash(delta)
    post_K0_hash = _topology_hash(K_0_perm)
    post_delta_hash = _topology_hash(delta_perm)
    if pre_K0_hash != post_K0_hash or pre_delta_hash != post_delta_hash:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=pre_delta_hash,
            shuffle_domain="node_payload",
            candidate_pool_size=int(N),
            eligibility_reason=(
                "node identity is coupled to topology — a non-identity "
                "permutation mutates K_0 or ΔK topology hash; "
                "node-payload permutation cannot honour M2 contract"
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "injection_window_index": int(inject_t),
                "pool_count": int(N),
                "distinct_values_count": int(distinct),
                "pre_K0_topology_hash": pre_K0_hash,
                "post_K0_topology_hash": post_K0_hash,
                "pre_delta_topology_hash": pre_delta_hash,
                "post_delta_topology_hash": post_delta_hash,
            },
        )

    return M2EligibilityVerdict(
        status="ELIGIBLE_M2_NODE_PAYLOAD",
        substrate_id=sub_id,
        N=int(N),
        preserved_topology_hash=pre_delta_hash,
        shuffle_domain="node_payload",
        candidate_pool_size=int(N),
        eligibility_reason=(
            f"per-node payload exposes {distinct} distinct value(s); "
            "topology hashes invariant under node permutation"
        ),
        metadata={
            "substrate_id": sub_id,
            "lambda_value": float(lambda_value),
            "base_seed": int(base_seed),
            "null_seed": int(eff_null_seed),
            "injection_window_index": int(inject_t),
            "pool_count": int(N),
            "distinct_values_count": int(distinct),
        },
    )


def realize_m2_node_payload_null(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Construct an M2 node-payload-shuffle K_null.

    Procedure (assumes verifier has already returned ELIGIBLE_M2_NODE_PAYLOAD):

    1. Build ``(K_0, ΔK, node_payload)`` via
       :func:`_extract_node_payload`.
    2. Seed ``rng = np.random.default_rng(null_seed)``; permute node
       indices deterministically.
    3. Reassemble ``K_null = K_0 + permuted_ΔK`` where
       ``permuted_ΔK = ΔK[ix_(perm, perm)]``. The reassembly preserves
       the payload multiset by construction (just relocates rows /
       columns) and — under the contract validated by the verifier
       — preserves the topology hash.
    4. Verify topology hash invariance fail-closed; raise
       :class:`M2TopologyMutationError` on drift.

    Notes
    -----
    On the prereg-scoped grid this function is UNREACHABLE because the
    verifier always returns INELIGIBLE_* for every prereg substrate.
    It is implemented for completeness so the realisation surface
    matches the eligibility surface and future substrate extensions
    can plug in without touching the dispatch.
    """
    K_0, delta, node_payload, inject_t = _extract_node_payload(
        substrate,
        base_seed=int(base_seed),
        lambda_value=float(lambda_value),
        N=int(N),
    )
    distinct = int(np.unique(np.round(node_payload, 12)).size)
    if distinct < 2:
        raise D002GNullInvalid(
            f"M2 node-payload: degenerate pool ({distinct} distinct "
            "value(s)); verifier should have screened this"
        )

    pre_K0_hash = _topology_hash(K_0)
    pre_delta_hash = _topology_hash(delta)

    rng = np.random.default_rng(int(null_seed))
    perm = rng.permutation(int(N))
    K_0_perm = K_0[np.ix_(perm, perm)]
    delta_perm = delta[np.ix_(perm, perm)]

    post_K0_hash = _topology_hash(K_0_perm)
    post_delta_hash = _topology_hash(delta_perm)
    if pre_K0_hash != post_K0_hash or pre_delta_hash != post_delta_hash:
        raise M2TopologyMutationError(
            "M2 node-payload shuffle mutated topology hash "
            f"(K_0 pre={pre_K0_hash}, post={post_K0_hash}; "
            f"ΔK pre={pre_delta_hash}, post={post_delta_hash}) — "
            "internal-invariant violation; cell REFUSED"
        )

    K_null = K_0_perm + delta_perm
    metadata: dict[str, Any] = {
        "null_strategy": "M2_TOPOLOGY_PRESERVING_SHUFFLE",
        "shuffle_domain": "node_payload",
        "eligibility_status": _M2_NODE_PAYLOAD_ELIGIBLE,
        "null_seed": int(null_seed),
        "preserved_topology_hash": pre_delta_hash,
        "candidate_pool_size": int(N),
        "support_count": int(N),
        "distinct_values_count": int(distinct),
        "injection_window_index": int(inject_t),
        "lambda_value": float(lambda_value),
    }
    return K_null, metadata


# ---------------------------------------------------------------------------
# P3 — M2 injection-sequence sub-domain
# ---------------------------------------------------------------------------


def _extract_injection_sequence(
    substrate: Substrate,
    *,
    base_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], list[NDArray[np.float64]], list[int]]:
    """Return ``(K_baseline_traj, K_precursor_traj, per_event_deltas, event_times)``.

    The injection-event sequence is the per-time-step ΔK during the
    canonical injection window. For substrates that lift K uniformly
    across the window (current prereg grid), the sequence is the
    constant-per-event list ``[ΔK(t)]`` for ``t`` in the injection
    window.
    """
    real = substrate.realize(N=int(N), lambda_=float(lambda_value), seed=int(base_seed))
    K_base = np.asarray(real.K_baseline, dtype=np.float64)
    K_prec = np.asarray(real.K_precursor, dtype=np.float64)
    if K_base.ndim != 3 or K_prec.ndim != 3:
        raise D002GNullInvalid(
            f"injection-sequence: K trajectories must be 3-D; "
            f"got baseline={K_base.shape} precursor={K_prec.shape}"
        )
    if not (np.all(np.isfinite(K_base)) and np.all(np.isfinite(K_prec))):
        raise D002GNullInvalid("injection-sequence: K trajectories contain non-finite")
    events: list[NDArray[np.float64]] = []
    times: list[int] = []
    for t in PRECURSOR_INJECTION_WINDOW:
        d_t = K_prec[t] - K_base[t]
        if np.any(np.abs(d_t) > 1e-12):
            events.append(d_t)
            times.append(int(t))
    return K_base, K_prec, events, times


def verify_m2_injection_sequence_eligibility(
    substrate: Substrate,
    *,
    N: int,
    lambda_value: float,
    base_seed: int,
    null_seed: int | None = None,
) -> M2EligibilityVerdict:
    """Pre-check whether (substrate, N, λ, seed) admits an M2 injection-sequence null.

    Verdict ladder (first matching condition wins):

    1. ``INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING`` —
       substrate refuses to construct the precursor.
    2. ``INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN`` — the
       substrate's precursor injection has length < 2 distinct
       time slices. There is no sequence to permute.
    3. ``INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE`` — every
       event is bit-identical. Permuting an equal-event list is a
       no-op.
    4. ``INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION`` —
       the substrate is `temporal_coupling`: its injection IS the
       entire causal hypothesis and any reordering would destroy
       the substrate's identity (the lag-coupling contract). The
       cell is REFUSED rather than emit a semantically-fake null.
    5. ``ELIGIBLE_M2_INJECTION_SEQUENCE`` — all checks pass.

    Notes
    -----
    `block_structured` has no temporal dimension to its injection
    (the lift is identical across all injection-window slices). On
    the prereg grid it returns DEGENERATE or MISSING_DOMAIN.
    `temporal_coupling` returns CONTRACT_VIOLATION because the
    sinusoidal envelope + injection-window timing IS the substrate's
    causal hypothesis; permuting events would falsely report a
    non-degenerate null whose semantics differ from the precursor's.
    `ricci_flow` has no injection-event sequence beyond the same
    uniform-window lift; returns DEGENERATE.
    """
    if not math.isfinite(lambda_value) or lambda_value <= 0.0:
        raise D002GNullInvalid("verify_m2_injection_sequence_eligibility requires lambda_value > 0")
    if int(N) < 2:
        raise D002GNullInvalid(f"N must be >= 2; got {N!r}")

    sub_id = str(substrate.id)
    try:
        _K_base, _K_prec, events, times = _extract_injection_sequence(
            substrate,
            base_seed=int(base_seed),
            lambda_value=float(lambda_value),
            N=int(N),
        )
    except Exception as exc:  # noqa: BLE001
        return M2EligibilityVerdict(
            status="INDETERMINATE_M2_INJECTION_SEQUENCE_PROVENANCE_MISSING",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash="",
            shuffle_domain="injection_sequence",
            candidate_pool_size=0,
            eligibility_reason=(f"substrate.realize raised {type(exc).__name__}: {exc!s}"),
            metadata={
                "exception_type": type(exc).__name__,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
            },
        )

    n_events = len(events)
    if n_events < 2:
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_INJECTION_SEQUENCE_MISSING_DOMAIN",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash="",
            shuffle_domain="injection_sequence",
            candidate_pool_size=int(n_events),
            eligibility_reason=(
                f"substrate emits {n_events} discrete injection event(s) "
                "in the canonical window; injection-sequence sub-domain "
                "requires >= 2 distinct events to admit a permutation"
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "event_times": list(times),
                "event_count": int(n_events),
            },
        )

    # Lag-coupling contract check. `temporal_coupling` carries the
    # injection sequence as the substrate's causal hypothesis (the
    # K(t) envelope is sinusoidal and the injection window timing
    # interacts with that envelope). Permuting events would emit a
    # K_null whose semantics differ from the precursor's stated
    # hypothesis — exactly the kind of semantic-fake null this PR's
    # adjudication protocol is designed to reject.
    if sub_id == "temporal_coupling":
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash="",
            shuffle_domain="injection_sequence",
            candidate_pool_size=int(n_events),
            eligibility_reason=(
                "temporal_coupling substrate: the injection-event "
                "sequence is the substrate's stated lag-coupling "
                "contract (sinusoidal envelope × injection-window "
                "timing). Permuting events would emit a semantically-"
                "fake null with hypothesis ≠ precursor's. REFUSED."
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "event_times": list(times),
                "event_count": int(n_events),
                "contract": "sinusoidal_envelope_times_injection_window",
            },
        )

    # Degenerate-event check: events are pairwise bit-identical.
    first = events[0]
    if all(np.array_equal(first, ev) for ev in events[1:]):
        return M2EligibilityVerdict(
            status="INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE",
            substrate_id=sub_id,
            N=int(N),
            preserved_topology_hash=_topology_hash(first),
            shuffle_domain="injection_sequence",
            candidate_pool_size=int(n_events),
            eligibility_reason=(
                f"all {n_events} injection events are bit-identical; permutation is a no-op"
            ),
            metadata={
                "substrate_id": sub_id,
                "lambda_value": float(lambda_value),
                "base_seed": int(base_seed),
                "event_times": list(times),
                "event_count": int(n_events),
                "distinct_event_count": 1,
            },
        )

    eff_null_seed = (
        int(null_seed)
        if null_seed is not None
        else _default_null_seed_m2_injection_sequence(int(base_seed))
    )
    return M2EligibilityVerdict(
        status="ELIGIBLE_M2_INJECTION_SEQUENCE",
        substrate_id=sub_id,
        N=int(N),
        preserved_topology_hash=_topology_hash(first),
        shuffle_domain="injection_sequence",
        candidate_pool_size=int(n_events),
        eligibility_reason=(
            f"{n_events} injection events with non-degenerate ordering; "
            "no stated lag-coupling contract violated"
        ),
        metadata={
            "substrate_id": sub_id,
            "lambda_value": float(lambda_value),
            "base_seed": int(base_seed),
            "null_seed": int(eff_null_seed),
            "event_times": list(times),
            "event_count": int(n_events),
        },
    )


def realize_m2_injection_sequence_null(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Construct an M2 injection-sequence-shuffle K_null.

    Procedure (assumes verifier has already returned
    ELIGIBLE_M2_INJECTION_SEQUENCE):

    1. Extract event sequence via :func:`_extract_injection_sequence`.
    2. Permute event order deterministically.
    3. Re-emit the baseline K at the canonical injection slice plus
       the FIRST event from the permuted order. (For event lists with
       len == 2 the two reorderings ARE the admissible non-degenerate
       nulls; the function emits the static slice consistent with the
       :class:`NullRealization` contract.)
    4. Verify topology hash invariance of the per-event ΔK.

    Honest stance: on the locked prereg grid no substrate reaches
    this function — `temporal_coupling` is REFUSED by contract,
    `block_structured` / `ricci_flow` return DEGENERATE /
    MISSING_DOMAIN. The function is implemented for completeness so
    the realisation surface matches the eligibility surface, and so
    a future substrate that exposes a non-trivial admissible
    injection sequence can plug in without touching the dispatch.
    """
    K_base_traj, _K_prec_traj, events, times = _extract_injection_sequence(
        substrate,
        base_seed=int(base_seed),
        lambda_value=float(lambda_value),
        N=int(N),
    )
    n_events = len(events)
    if n_events < 2:
        raise D002GNullInvalid(
            f"M2 injection-sequence: {n_events} event(s); verifier should have screened this"
        )

    rng = np.random.default_rng(int(null_seed))
    perm_order = rng.permutation(n_events)
    permuted_events = [events[i] for i in perm_order]

    inject_t = int(next(iter(PRECURSOR_INJECTION_WINDOW)))
    K_0_static = np.asarray(K_base_traj[inject_t], dtype=np.float64)
    delta_first = permuted_events[0]

    pre_hash = _topology_hash(events[0])
    post_hash = _topology_hash(delta_first)
    if pre_hash != post_hash:
        raise M2TopologyMutationError(
            f"M2 injection-sequence: per-event topology hash drift "
            f"(pre={pre_hash}, post={post_hash}); REFUSED"
        )

    K_null = K_0_static + delta_first
    metadata: dict[str, Any] = {
        "null_strategy": "M2_TOPOLOGY_PRESERVING_SHUFFLE",
        "shuffle_domain": "injection_sequence",
        "eligibility_status": _M2_INJECTION_SEQUENCE_ELIGIBLE,
        "null_seed": int(null_seed),
        "preserved_topology_hash": pre_hash,
        "candidate_pool_size": int(n_events),
        "support_count": int(n_events),
        "distinct_values_count": int(n_events),
        "injection_window_index": int(inject_t),
        "event_times": list(times),
        "event_order_permutation": [int(x) for x in perm_order.tolist()],
        "lambda_value": float(lambda_value),
    }
    return K_null, metadata


# ---------------------------------------------------------------------------
# M3 — topology-conditioned independent realisation under matched-density
# resampling (pre-registered at PR #680 merge; salt 523 locked).
# ---------------------------------------------------------------------------
#
# Discipline contract. M3 is NOT a permutation of an existing precursor
# realisation. M3 draws a topology-MATCHED INDEPENDENT realisation from
# a deterministic generator whose marginals match the precursor's
# locked marginal set (degree sequence + block-label histogram + spectral
# radius / N + density). The matched marginal set is LOCKED at the M3
# pre-reg — refining it requires a fresh M4. What this implementation
# refines (per M3 §9.1 allowed scope) is the concrete estimator + the
# generator engineering, NOT the marginal definition.
#
# A TRUTHFUL INELIGIBLE_M3_* verdict on either or both
# block_structured / temporal_coupling is the operating law: M3 may not
# have the right to exist on the locked grid, and the verifier records
# that fact. Forcing ELIGIBLE_M3 to game B1 closure is the failure mode
# the pre-registration discipline exists to prevent.


M3EligibilityStatus = Literal[
    "ELIGIBLE_M3",
    "INELIGIBLE_M3_MARGINAL_MISMATCH",
    "INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC",
    "INELIGIBLE_M3_DEGENERATE_DISTANCE",
    "INELIGIBLE_M3_GENERATOR_DIVERGENT",
    "INELIGIBLE_M3_TOPOLOGY_SUMMARY_MISSING",
    "INELIGIBLE_M3_NUMERICAL_NONFINITE",
    "INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION",
    "INDETERMINATE_M3_PROVENANCE_MISSING",
]

_M3_ELIGIBLE: Final[str] = "ELIGIBLE_M3"


class M3NotEligibleError(RuntimeError):
    """M3 verifier returned a non-ELIGIBLE_M3 verdict for this cell.

    Carries the :class:`M3EligibilityVerdict` as ``self.verdict`` so
    callers can introspect ``status`` and ``eligibility_reason``.
    Raised by :func:`realize_null` when invoked with strategy
    ``"M3_TOPOLOGY_CONDITIONED"`` on a cell the verifier refuses. The
    M3 contract is fail-closed by construction — no silent downgrade
    to M1 / M2 / no-op (per pre-reg §4 Non-negotiable 7).
    """

    def __init__(self, verdict: Any) -> None:
        super().__init__(
            f"M3 verdict {verdict.status!r} for substrate "
            f"{verdict.substrate_id!r} at N={verdict.N}, "
            f"lambda_value={verdict.lambda_value}: "
            f"{verdict.eligibility_reason}"
        )
        self.verdict = verdict


class M3GeneratorDivergentError(RuntimeError):
    """M3 matched generator failed to converge to target marginals.

    Raised by :func:`topology_matched_resample` after
    :data:`M3_GENERATOR_MAX_ITERATIONS` rebalance iterations failed to
    drive every marginal inside the locked tolerance. The verifier
    catches this exception and routes it to
    ``INELIGIBLE_M3_GENERATOR_DIVERGENT``; the realisation layer
    refuses the cell.
    """


@dataclass(frozen=True)
class M3TopologySummary:
    """Frozen locked marginal set for one K matrix.

    The marginal set is LOCKED at the M3 pre-registration §2. Any change
    to the marginals requires a fresh M4 pre-registration.

    Fields
    ------
    degree_sequence
        Sorted ascending tuple of per-node row-sum magnitudes (length N).
        Captures the per-node weighted-degree distribution.
    block_label_histogram
        Tuple of integer bin counts over the substrate-defined block
        label space. For substrates without a block label exposed, the
        verifier falls back to ``(N,)`` (single bin) so the histogram
        is always defined.
    spectral_radius_over_N
        ``max(|eigvals(K)|) / N``. Captures the largest-mode coupling.
    density
        Fraction of nonzero upper-triangle entries — i.e.
        ``|{(i,j) : i<j, |K[i,j]| > 1e-12}| / (N*(N-1)/2)``.
    n_nodes
        Cohort size (matrix dimension).
    n_support_edges
        Count of |K| > 1e-12 entries on the strict upper triangle.
    summary_sha256
        sha256 over the canonical-JSON dump of all fields above
        (excluding itself). Two K matrices with identical marginals
        share this sha bit-exact.
    """

    degree_sequence: tuple[float, ...]
    block_label_histogram: tuple[int, ...]
    spectral_radius_over_N: float
    density: float
    n_nodes: int
    n_support_edges: int
    summary_sha256: str


@dataclass(frozen=True)
class M3MarginalMatchReport:
    """Frozen comparator report for one (K_p, K_null) marginal match.

    Fields
    ------
    degree_wasserstein
        Wasserstein-1 distance between the sorted degree sequences,
        normalised by the K_p mean degree (zero-mean fallback: 1.0).
    block_histogram_l1
        L1 distance between the two block-label histograms.
    spectral_radius_rel_err
        ``|ρ_null/N - ρ_p/N| / max(ρ_p/N, 1e-12)``.
    density_rel_err
        ``|d_null - d_p| / max(d_p, 1e-12)``.
    all_within_tolerance
        True iff every comparator is below its locked tolerance.
    failed_marginal
        Name of the first marginal that exceeded tolerance, or None
        if all match. Names: ``"degree_wasserstein"``,
        ``"block_histogram_l1"``, ``"spectral_radius"``, ``"density"``.
    """

    degree_wasserstein: float
    block_histogram_l1: float
    spectral_radius_rel_err: float
    density_rel_err: float
    all_within_tolerance: bool
    failed_marginal: str | None


@dataclass(frozen=True)
class M3EligibilityVerdict:
    """Frozen verdict from :func:`verify_m3_eligibility`.

    Fields
    ------
    status
        One of :data:`M3EligibilityStatus`. Only ``"ELIGIBLE_M3"`` admits
        a subsequent :func:`realize_null` call with strategy
        ``"M3_TOPOLOGY_CONDITIONED"``.
    substrate_id
        From :attr:`Substrate.id`.
    N
        Cohort size.
    lambda_value
        Cell coordinate.
    summary
        The :class:`M3TopologySummary` of the precursor K at this cell;
        None when summary extraction itself fails (substrate raised or
        K shape / numerical contract violation).
    match_report
        The :class:`M3MarginalMatchReport` for the generated K_null
        against the precursor summary; None when the generator never
        produced a candidate (e.g. summary missing / divergent).
    eligibility_reason
        Single-line human-readable explanation.
    metadata
        Strategy-specific diagnostics for downstream audits.
    """

    status: M3EligibilityStatus
    substrate_id: str
    N: int
    lambda_value: float
    summary: M3TopologySummary | None
    match_report: M3MarginalMatchReport | None
    eligibility_reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _substrate_block_labels(substrate: Substrate, N: int) -> NDArray[np.int_] | None:
    """Best-effort block-label vector for the substrate.

    Honest stance: the :class:`SubstrateRealization` schema does NOT
    expose a per-node block label today, so this helper recovers a
    label vector from substrate-id-specific knowledge:

      * ``block_structured`` — label = block index from the locked
        fractions (0.20, 0.30, 0.50). Same partition the substrate
        applies internally.
      * ``temporal_coupling`` — inherits block_structured's partition.
      * any other id — None (no block label available; histogram falls
        back to a single bin).

    Returning None is the HONEST path when the substrate exposes no
    block partition. The verifier still operates — its block-histogram
    comparator collapses to a length-1 tuple (n_nodes,) in that case.
    """
    sid = str(substrate.id)
    if sid in ("block_structured", "temporal_coupling"):
        f_core, f_mid, _f_per = BLOCK_FRACTIONS
        n_core = max(1, int(round(f_core * N)))
        n_mid = max(1, int(round(f_mid * N)))
        n_per = int(N) - n_core - n_mid
        if n_per <= 0:
            return None
        labels = np.empty(int(N), dtype=np.int_)
        labels[:n_core] = 0
        labels[n_core : n_core + n_mid] = 1
        labels[n_core + n_mid :] = 2
        return labels
    return None


def _wasserstein_1_sorted(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Wasserstein-1 distance between two equal-length 1-D samples.

    Both arrays are sorted ascending then averaged absolute-diff is
    returned. For unequal lengths the function raises — the M3 caller
    always passes equal-length degree sequences.
    """
    if a.shape != b.shape:
        raise D002GNullInvalid(f"Wasserstein-1: shape mismatch {a.shape} vs {b.shape}")
    a_sorted = np.sort(a)
    b_sorted = np.sort(b)
    return float(np.mean(np.abs(a_sorted - b_sorted)))


def extract_m3_topology_summary(
    K: NDArray[np.float64],
    *,
    substrate_block_labels: NDArray[np.int_] | None,
) -> M3TopologySummary:
    """Extract the locked marginal set from one K matrix.

    Parameters
    ----------
    K
        Symmetric float64 (N, N) coupling matrix. Must be finite.
    substrate_block_labels
        Length-N integer vector of block labels, or None. When None the
        block-label histogram falls back to a single bin of size N.

    Raises
    ------
    D002GNullInvalid
        K not float64 / non-square / non-finite, or
        ``substrate_block_labels`` length mismatch / non-integer.
    """
    if K.dtype != np.float64:
        raise D002GNullInvalid(f"K must be float64; got {K.dtype}")
    _refuse_if_non_square(K)
    if not np.all(np.isfinite(K)):
        raise D002GNullInvalid("K contains non-finite entries")
    N = int(K.shape[0])
    # Degree sequence: sorted ascending row-sum magnitudes (length N).
    row_sums = np.abs(K).sum(axis=1)
    degree_sequence = tuple(float(x) for x in np.sort(row_sums).tolist())

    # Block-label histogram. Length-1 fallback when no labels exposed.
    if substrate_block_labels is None:
        block_label_histogram: tuple[int, ...] = (int(N),)
    else:
        labels = np.asarray(substrate_block_labels)
        if labels.shape != (N,):
            raise D002GNullInvalid(
                f"substrate_block_labels must have shape ({N},); got {labels.shape}"
            )
        if not np.issubdtype(labels.dtype, np.integer):
            raise D002GNullInvalid(
                f"substrate_block_labels must be integer dtype; got {labels.dtype}"
            )
        max_lab = int(labels.max()) if N > 0 else 0
        bincount = np.bincount(labels.astype(np.int64), minlength=max_lab + 1)
        block_label_histogram = tuple(int(x) for x in bincount.tolist())

    # Spectral radius / N (use eigvalsh — K is symmetric).
    eigs = np.linalg.eigvalsh(K)
    spectral_radius_over_N = float(np.abs(eigs).max() / float(N))

    # Density on upper triangle.
    iu_r, iu_c = np.triu_indices(N, k=1)
    upper = K[iu_r, iu_c]
    support_mask = np.abs(upper) > 1e-12
    n_support_edges = int(np.count_nonzero(support_mask))
    n_upper = (N * (N - 1)) // 2
    density = float(n_support_edges) / float(n_upper) if n_upper > 0 else 0.0

    # Canonical sha over the marginal payload (excludes the sha itself).
    payload = {
        "degree_sequence": list(degree_sequence),
        "block_label_histogram": list(block_label_histogram),
        "spectral_radius_over_N": float(spectral_radius_over_N),
        "density": float(density),
        "n_nodes": int(N),
        "n_support_edges": int(n_support_edges),
    }
    summary_sha256 = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    return M3TopologySummary(
        degree_sequence=degree_sequence,
        block_label_histogram=block_label_histogram,
        spectral_radius_over_N=spectral_radius_over_N,
        density=density,
        n_nodes=N,
        n_support_edges=n_support_edges,
        summary_sha256=summary_sha256,
    )


def _compare_m3_marginals(
    target: M3TopologySummary,
    candidate: M3TopologySummary,
) -> M3MarginalMatchReport:
    """Compute marginal-distance comparator for one (target, candidate) pair."""
    target_deg = np.asarray(target.degree_sequence, dtype=np.float64)
    cand_deg = np.asarray(candidate.degree_sequence, dtype=np.float64)
    if target_deg.shape != cand_deg.shape:
        # Length mismatch → infinite Wasserstein. Drive the comparator
        # to "fail" deterministically; downstream verifier flags it.
        degree_wasserstein = float("inf")
    else:
        mean_deg = float(np.mean(target_deg)) if target_deg.size else 0.0
        denom = max(mean_deg, 1e-12)
        degree_wasserstein = _wasserstein_1_sorted(target_deg, cand_deg) / denom

    target_hist = np.asarray(target.block_label_histogram, dtype=np.int64)
    cand_hist = np.asarray(candidate.block_label_histogram, dtype=np.int64)
    if target_hist.shape == cand_hist.shape:
        block_histogram_l1 = float(np.sum(np.abs(target_hist - cand_hist)))
    else:
        # Pad to common length then compare. Treat absent bins as 0.
        max_len = max(target_hist.size, cand_hist.size)
        t_pad = np.zeros(max_len, dtype=np.int64)
        c_pad = np.zeros(max_len, dtype=np.int64)
        t_pad[: target_hist.size] = target_hist
        c_pad[: cand_hist.size] = cand_hist
        block_histogram_l1 = float(np.sum(np.abs(t_pad - c_pad)))

    spec_p = float(target.spectral_radius_over_N)
    spec_n = float(candidate.spectral_radius_over_N)
    spectral_radius_rel_err = abs(spec_n - spec_p) / max(abs(spec_p), 1e-12)

    d_p = float(target.density)
    d_n = float(candidate.density)
    density_rel_err = abs(d_n - d_p) / max(d_p, 1e-12)

    failed_marginal: str | None = None
    if not math.isfinite(degree_wasserstein) or degree_wasserstein > M3_TOL_DEGREE_WASSERSTEIN:
        failed_marginal = "degree_wasserstein"
    elif block_histogram_l1 > 0:
        # Histogram L1 must be exactly 0 — the generator preserves the
        # block-bin counts by construction. Any drift is a marginal-
        # mismatch failure.
        failed_marginal = "block_histogram_l1"
    elif spectral_radius_rel_err > M3_TOL_SPECTRAL_RADIUS:
        failed_marginal = "spectral_radius"
    elif density_rel_err > M3_TOL_DENSITY:
        failed_marginal = "density"

    all_within_tolerance = failed_marginal is None
    return M3MarginalMatchReport(
        degree_wasserstein=float(degree_wasserstein),
        block_histogram_l1=float(block_histogram_l1),
        spectral_radius_rel_err=float(spectral_radius_rel_err),
        density_rel_err=float(density_rel_err),
        all_within_tolerance=all_within_tolerance,
        failed_marginal=failed_marginal,
    )


def topology_matched_resample(
    target: M3TopologySummary,
    *,
    null_seed: int,
    rng_salt_mix: int,
) -> NDArray[np.float64]:
    """Draw an independent K matrix whose marginals match ``target``.

    Procedure (deterministic given ``(null_seed, rng_salt_mix)`` —
    no global state, no time-based seeds):

    1. Initialise empty symmetric upper-triangle K_null (N×N float64).
    2. Sample ``n_support_edges`` distinct upper-triangle positions
       weighted by a degree-product prior derived from ``target``.
    3. Assign weights drawn from the target degree-magnitude scale
       (mean row-sum / mean degree); these are the initial edge weights.
    4. Rebalance: iteratively swap or rescale edges so each marginal
       (degree-Wasserstein, spectral radius, density) sits inside its
       locked tolerance. Capped at :data:`M3_GENERATOR_MAX_ITERATIONS`.
    5. Symmetrise: K_null = (K_null + K_null.T) / 2 (already symmetric
       by construction; the explicit step guards against floating-point
       asymmetry from in-place writes).

    Returns
    -------
    K_null
        N×N float64 symmetric matrix.

    Raises
    ------
    M3GeneratorDivergentError
        After :data:`M3_GENERATOR_MAX_ITERATIONS` iterations the
        marginals are still out of tolerance.
    D002GNullInvalid
        Bad target (e.g. n_nodes < 2 or non-finite density).
    """
    N = int(target.n_nodes)
    if N < 2:
        raise D002GNullInvalid(f"M3 generator: N must be >= 2; got {N}")
    if not (0.0 <= target.density <= 1.0):
        raise D002GNullInvalid(f"M3 generator: target.density={target.density!r} outside [0, 1]")
    if not math.isfinite(target.spectral_radius_over_N):
        raise D002GNullInvalid("M3 generator: target.spectral_radius_over_N non-finite")

    # Build deterministic RNG. The seed mixes (null_seed, rng_salt_mix)
    # so different cells / substrates produce different draws while
    # same-cell same-seed replays bit-identically.
    seed = deterministic_mix_multi(int(null_seed), int(rng_salt_mix))
    rng = np.random.default_rng(seed)

    iu_r, iu_c = np.triu_indices(N, k=1)
    n_upper = iu_r.size
    n_target_edges = int(target.n_support_edges)
    if n_target_edges > n_upper:
        raise D002GNullInvalid(
            f"M3 generator: target.n_support_edges={n_target_edges} > "
            f"upper-triangle count {n_upper}"
        )

    target_degrees = np.asarray(target.degree_sequence, dtype=np.float64)
    # Reference scale = mean target degree; used to seed initial edge
    # weights. If everything is zero the trivial all-zero K matches the
    # target (degenerate-target branch handled below).
    if n_target_edges == 0:
        K_null = np.zeros((N, N), dtype=np.float64)
        return K_null

    mean_deg_target = float(np.mean(target_degrees)) if target_degrees.size else 0.0
    if mean_deg_target == 0.0:
        # Target carries zero row-sums but n_target_edges > 0 — internal
        # contradiction; fail-closed.
        raise M3GeneratorDivergentError(
            "M3 generator: target.degree_sequence sum is zero but "
            f"n_support_edges={n_target_edges} > 0 (contradictory marginals)"
        )

    # Initial edge weight: split the row-sum scale across the per-node
    # edge budget. mean weight = mean_deg_target * N / (2 * n_target_edges).
    initial_weight = float(mean_deg_target * N) / float(2 * n_target_edges)

    # Sample edge positions uniformly without replacement.
    chosen_positions = rng.choice(n_upper, size=n_target_edges, replace=False)
    # Perturb weights with a small log-normal multiplier so the degree
    # sequence is not constant by construction; rebalance below pulls
    # the Wasserstein-1 distance below tolerance.
    perturbations = np.exp(rng.normal(0.0, 0.2, size=n_target_edges))
    edge_weights = initial_weight * perturbations

    target_spectral = float(target.spectral_radius_over_N)

    substrate_labels: NDArray[np.int_] | None = None  # generator-side: no labels

    converged = False
    last_iteration_report: M3MarginalMatchReport | None = None
    iters_used = 0
    for it in range(M3_GENERATOR_MAX_ITERATIONS):
        iters_used = it + 1
        K_null = np.zeros((N, N), dtype=np.float64)
        K_null[iu_r[chosen_positions], iu_c[chosen_positions]] = edge_weights
        K_null = K_null + K_null.T  # symmetrise

        # Snap spectral radius to target by uniform rescale (cheap,
        # marginal-preserving up to spectral & density which is invariant).
        eigs = np.linalg.eigvalsh(K_null)
        rho_n = float(np.abs(eigs).max() / float(N))
        if rho_n > 0.0:
            scale = target_spectral / rho_n
            K_null = K_null * scale
            edge_weights = edge_weights * scale

        candidate_summary = extract_m3_topology_summary(
            K_null, substrate_block_labels=substrate_labels
        )
        # Block histogram check happens only when target HAS multi-bin
        # labels. The generator does NOT know substrate labels, so this
        # field is compared at the verifier level (with substrate labels
        # applied). Inside the generator we use the unlabelled target —
        # only checked when caller supplies labels in target.
        unlabeled_target_hist = (int(N),)
        target_for_compare = M3TopologySummary(
            degree_sequence=target.degree_sequence,
            block_label_histogram=unlabeled_target_hist,
            spectral_radius_over_N=target.spectral_radius_over_N,
            density=target.density,
            n_nodes=target.n_nodes,
            n_support_edges=target.n_support_edges,
            summary_sha256=target.summary_sha256,
        )
        candidate_for_compare = M3TopologySummary(
            degree_sequence=candidate_summary.degree_sequence,
            block_label_histogram=unlabeled_target_hist,
            spectral_radius_over_N=candidate_summary.spectral_radius_over_N,
            density=candidate_summary.density,
            n_nodes=candidate_summary.n_nodes,
            n_support_edges=candidate_summary.n_support_edges,
            summary_sha256=candidate_summary.summary_sha256,
        )
        report = _compare_m3_marginals(target_for_compare, candidate_for_compare)
        last_iteration_report = report

        # Density mismatch? If the candidate's |K|>1e-12 support set
        # drifted (some edges collapsed below threshold under rescale),
        # snap weights up.
        if report.failed_marginal == "density":
            edge_weights = np.maximum(edge_weights, 2e-12 * np.ones_like(edge_weights))
            continue

        # Degree-Wasserstein mismatch? Adjust per-edge weights toward
        # target's sorted degree sequence via a contraction step.
        if report.failed_marginal == "degree_wasserstein":
            cur_row_sum = np.abs(K_null).sum(axis=1)
            order_cur = np.argsort(cur_row_sum)
            target_sorted = np.sort(target_degrees)
            desired = np.empty_like(cur_row_sum)
            desired[order_cur] = target_sorted
            # Scale each node's incident edges by the desired/current
            # ratio (clamped to [0.5, 2.0] per step for stability).
            ratio_per_node = np.where(
                cur_row_sum > 1e-12,
                np.clip(desired / np.maximum(cur_row_sum, 1e-12), 0.5, 2.0),
                1.0,
            )
            # Apply the geometric mean of (ratio_i, ratio_j) to edge (i,j).
            edge_ratios = np.sqrt(
                ratio_per_node[iu_r[chosen_positions]] * ratio_per_node[iu_c[chosen_positions]]
            )
            edge_weights = edge_weights * edge_ratios
            continue

        if report.all_within_tolerance:
            converged = True
            break

        # Spectral mismatch was already snapped above. If we end up here
        # the comparator detected a residual; small jitter keeps the
        # loop from stalling.
        jitter = rng.normal(0.0, 0.01, size=n_target_edges)
        edge_weights = edge_weights * np.exp(jitter)

    if not converged:
        if last_iteration_report is None:
            raise M3GeneratorDivergentError(
                "M3 generator: no iteration produced a comparator report "
                f"(iters_used={iters_used}, max={M3_GENERATOR_MAX_ITERATIONS})"
            )
        raise M3GeneratorDivergentError(
            f"M3 generator: failed to match marginals within "
            f"{M3_GENERATOR_MAX_ITERATIONS} iterations "
            f"(failed_marginal={last_iteration_report.failed_marginal!r}, "
            f"degree_wasserstein={last_iteration_report.degree_wasserstein:.4f}, "
            f"density_rel_err={last_iteration_report.density_rel_err:.4f}, "
            f"spectral_rel_err={last_iteration_report.spectral_radius_rel_err:.4f})"
        )

    # Final symmetrisation guard against floating-point asymmetry.
    K_final = (K_null + K_null.T) / 2.0
    return K_final.astype(np.float64, copy=False)


def _default_null_seed_m3(base_seed: int) -> int:
    """Locked M3 null-seed formula — deterministic mix with salt 523.

    Distinct prime salt from M1 offset (10000), M6 (99), M2 edge_weight
    (211), M2 node_payload (313), and M2 injection_sequence (419) —
    fully domain-separated RNG stream against Strike-R5 stride attack.
    """
    return deterministic_mix(int(base_seed), M3_TOPOLOGY_CONDITIONED_SALT)


def _m3_substrate_id_hash(substrate_id: str) -> int:
    """Deterministic int63 hash of the substrate id string.

    Used in the M3 multi-arg deterministic_mix call so different
    substrates yield different RNG streams at the same (base_seed,
    null_seed, N, lambda). sha256-low-63 keeps the mixing primitive
    consistent with :func:`deterministic_mix`.
    """
    digest = hashlib.sha256(substrate_id.encode("utf-8")).digest()
    head = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return int(head & ((1 << 63) - 1))


def _m3_lambda_bits(lambda_value: float) -> int:
    """Bit-pattern of float64 lambda_value cast as signed int64.

    Provides a deterministic injection of lambda_value into the M3 mix
    without floating-point ambiguity. NaN bits are forbidden — caller
    must check finiteness first.
    """
    if not math.isfinite(lambda_value):
        raise D002GNullInvalid(f"lambda_value must be finite for M3 mix; got {lambda_value!r}")
    raw = struct.unpack(">q", struct.pack(">d", float(lambda_value)))[0]
    return int(raw)


def verify_m3_eligibility(
    substrate: Substrate,
    *,
    N: int,
    lambda_value: float,
    base_seed: int,
    null_seed: int | None = None,
) -> M3EligibilityVerdict:
    """Pre-check whether (substrate, N, λ, seed) admits an M3 null.

    The verifier walks the 5 admissibility criteria from the M3
    pre-registration §3 fail-closed:

    1. Topology marginal extractable — substrate produces a valid
       K_precursor at this cell; shape (N,N), float64, finite, symmetric.
       Failure → SHAPE_CONTRACT_VIOLATION / NUMERICAL_NONFINITE /
       PROVENANCE_MISSING / TOPOLOGY_SUMMARY_MISSING.
    2. Matched generator exists — :func:`topology_matched_resample`
       converges within :data:`M3_GENERATOR_MAX_ITERATIONS`. Divergence
       → GENERATOR_DIVERGENT.
    3. Identifiable from precursor — over 100 distinct precursor seeds,
       ≥ 50 / 100 pairs yield distinct degree marginals. Otherwise
       → NON_PRECURSOR_SPECIFIC (the marginal is not informative).
    4. Non-degenerate distance — ``||K_null − K_p||_F`` strictly above
       :data:`M3_TOL_NON_DEGENERATE`. Otherwise → DEGENERATE_DISTANCE.
    5. Topology-coupling decoupled — a non-identity node permutation
       preserves the M3 marginal summary sha (necessary, not sufficient).
       Otherwise → MARGINAL_MISMATCH.

    Notes
    -----
    Criterion 3 is the heaviest single check (100 substrate realisations).
    It is gated behind criteria 1+2 — if the substrate can't produce a
    single matched generator output, no precursor-specificity probe is
    meaningful.
    """
    if not math.isfinite(lambda_value) or lambda_value <= 0.0:
        raise D002GNullInvalid(
            "verify_m3_eligibility requires lambda_value > 0 (M3 conditions on K_precursor at λ>0)"
        )
    if int(N) < 2:
        raise D002GNullInvalid(f"N must be >= 2; got {N!r}")

    sub_id = str(substrate.id)
    eff_null_seed = (
        int(null_seed) if null_seed is not None else _default_null_seed_m3(int(base_seed))
    )

    # ---- Criterion 1: precursor extraction + shape + numerical checks
    try:
        real = substrate.realize(N=int(N), lambda_=float(lambda_value), seed=int(base_seed))
    except Exception as exc:  # noqa: BLE001
        return M3EligibilityVerdict(
            status="INDETERMINATE_M3_PROVENANCE_MISSING",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason=(f"substrate.realize raised {type(exc).__name__}: {exc!s}"),
            metadata={
                "exception_type": type(exc).__name__,
                "base_seed": int(base_seed),
                "null_seed": int(eff_null_seed),
            },
        )

    inject_t = int(next(iter(PRECURSOR_INJECTION_WINDOW)))
    # Narrowed catch — np.asarray + indexing can raise this concrete set on
    # malformed substrate output. Any other exception SHOULD propagate so an
    # unexpected failure mode surfaces as a real bug, not a silent INELIGIBLE.
    try:
        K_p = np.asarray(real.K_precursor[inject_t], dtype=np.float64)
    except (
        ValueError,
        TypeError,
        IndexError,
        KeyError,
        AttributeError,
        np.linalg.LinAlgError,
    ) as exc:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason=f"K_precursor slice failed: {type(exc).__name__}: {exc!s}",
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    if K_p.ndim != 2 or K_p.shape[0] != K_p.shape[1] or K_p.shape[0] != int(N):
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason=(f"K_precursor shape {K_p.shape} ≠ expected (N,N)=({N},{N})"),
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    if not np.all(np.isfinite(K_p)):
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_NUMERICAL_NONFINITE",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason="K_precursor contains non-finite entries",
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    # Symmetry sanity (substrate gate G enforces this; defensive double-check).
    asym = float(np.max(np.abs(K_p - K_p.T))) if N > 0 else 0.0
    if asym > 1e-9:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_SHAPE_CONTRACT_VIOLATION",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason=f"K_precursor not symmetric (max asymmetry={asym:.3e})",
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    block_labels = _substrate_block_labels(substrate, int(N))
    try:
        target_summary = extract_m3_topology_summary(K_p, substrate_block_labels=block_labels)
    except D002GNullInvalid as exc:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_TOPOLOGY_SUMMARY_MISSING",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=None,
            match_report=None,
            eligibility_reason=f"topology summary extraction failed: {exc!s}",
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    # ---- Criterion 2: matched generator converges
    rng_salt_mix = deterministic_mix_multi(
        int(base_seed),
        int(M3_TOPOLOGY_CONDITIONED_SALT),
        int(eff_null_seed),
        int(_m3_substrate_id_hash(sub_id)),
        int(N),
        int(_m3_lambda_bits(float(lambda_value))),
    )
    try:
        K_null_candidate = topology_matched_resample(
            target_summary, null_seed=eff_null_seed, rng_salt_mix=rng_salt_mix
        )
    except M3GeneratorDivergentError as exc:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_GENERATOR_DIVERGENT",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=None,
            eligibility_reason=str(exc),
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )
    except D002GNullInvalid as exc:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_GENERATOR_DIVERGENT",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=None,
            eligibility_reason=f"M3 generator rejected target: {exc!s}",
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    candidate_summary = extract_m3_topology_summary(
        K_null_candidate, substrate_block_labels=block_labels
    )
    match_report = _compare_m3_marginals(target_summary, candidate_summary)
    if not match_report.all_within_tolerance:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_MARGINAL_MISMATCH",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=match_report,
            eligibility_reason=(
                f"candidate K_null marginals fail tolerance "
                f"(failed_marginal={match_report.failed_marginal!r})"
            ),
            metadata={"base_seed": int(base_seed), "null_seed": int(eff_null_seed)},
        )

    # ---- Criterion 3: identifiable from precursor (ensemble of 100 seeds)
    summaries_for_pairwise: list[M3TopologySummary] = []
    # Narrowed catch — substrate.realize and numpy extraction can raise the
    # concrete set below; any OTHER exception type SHOULD propagate so an
    # unexpected failure mode surfaces as a real bug, not a silently-skipped
    # seed. The fail-safe semantic is preserved: any seed that legitimately
    # fails to realise → skip; the ensemble shrinks; if < 50/100 valid
    # summaries remain, admissibility criterion 3 fails closed downstream.
    _SUBSTRATE_REALIZE_EXPECTED = (
        ValueError,
        RuntimeError,
        ArithmeticError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        MemoryError,
        np.linalg.LinAlgError,
    )
    for s in range(M3_PRECURSOR_ENSEMBLE_SIZE):
        try:
            r_s = substrate.realize(N=int(N), lambda_=float(lambda_value), seed=int(s))
            K_s = np.asarray(r_s.K_precursor[inject_t], dtype=np.float64)
            if not np.all(np.isfinite(K_s)):
                continue
            summaries_for_pairwise.append(
                extract_m3_topology_summary(K_s, substrate_block_labels=block_labels)
            )
        except _SUBSTRATE_REALIZE_EXPECTED:
            # Any failed seed reduces the effective ensemble; the check
            # is "≥ 50 distinct pairs out of 100 attempted" — if we have
            # <50 valid summaries the substrate cannot meet the criterion.
            continue

    n_ens = len(summaries_for_pairwise)
    distinct_pairs = 0
    pair_count = 0
    # Pair (i, i+1) over the first n_ens-1 indices — N=100 candidates yield
    # 99 ordered pairs; the criterion requires ≥ 50 distinct (i.e. ~half).
    for i in range(n_ens - 1):
        pair_count += 1
        rep = _compare_m3_marginals(summaries_for_pairwise[i], summaries_for_pairwise[i + 1])
        if not math.isfinite(rep.degree_wasserstein) or rep.degree_wasserstein > (
            M3_TOL_MARGINAL / 10.0
        ):
            distinct_pairs += 1
    if distinct_pairs < (M3_PRECURSOR_ENSEMBLE_SIZE // 2):
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_NON_PRECURSOR_SPECIFIC",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=match_report,
            eligibility_reason=(
                f"only {distinct_pairs}/{pair_count} adjacent-seed pairs yield "
                f"degree_wasserstein > tol/10; marginal is not precursor-specific"
            ),
            metadata={
                "ensemble_size_attempted": int(M3_PRECURSOR_ENSEMBLE_SIZE),
                "ensemble_size_valid": int(n_ens),
                "distinct_pair_count": int(distinct_pairs),
                "pair_count": int(pair_count),
                "base_seed": int(base_seed),
                "null_seed": int(eff_null_seed),
            },
        )

    # ---- Criterion 4: non-degenerate Frobenius distance
    frob = float(np.linalg.norm(K_null_candidate - K_p))
    if frob < M3_TOL_NON_DEGENERATE:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_DEGENERATE_DISTANCE",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=match_report,
            eligibility_reason=(
                f"||K_null - K_p||_F = {frob:.3e} < tol_non_degenerate {M3_TOL_NON_DEGENERATE:.3e}"
            ),
            metadata={
                "frobenius_distance": float(frob),
                "base_seed": int(base_seed),
                "null_seed": int(eff_null_seed),
            },
        )

    # ---- Criterion 5: topology-coupling decoupled (necessary, not sufficient)
    # Apply a deterministic non-identity permutation. The M3 marginal
    # summary must be permutation-invariant — the degree sequence is
    # sorted, the spectral radius is permutation-invariant, the density
    # is permutation-invariant. Block-label histogram preservation
    # depends on whether the labels themselves permute with the rows.
    # We compare the UNLABELLED-fallback summary for this invariant
    # (block-label-aware coupling is detected by the substrate-side
    # node-payload verifier; M3 cares about marginal preservation under
    # row/column permutation only).
    rng = np.random.default_rng(eff_null_seed)
    perm = rng.permutation(int(N))
    if np.array_equal(perm, np.arange(int(N))):
        # Force a non-identity permutation by swapping the first two
        # entries; for N=2 the swap is the unique non-identity.
        if int(N) >= 2:
            perm = perm.copy()
            perm[0], perm[1] = perm[1], perm[0]
    K_null_perm = K_null_candidate[np.ix_(perm, perm)]
    summary_unlabelled = extract_m3_topology_summary(K_null_candidate, substrate_block_labels=None)
    summary_perm_unlabelled = extract_m3_topology_summary(K_null_perm, substrate_block_labels=None)
    # Compare via comparator (tolerance-aware) rather than sha equality.
    # Sub-ulp drift in eigvalsh / row-sum accumulation can flip the
    # canonical-JSON sha while the underlying physics is invariant; the
    # tolerance-bounded comparator is the honest invariant.
    perm_report = _compare_m3_marginals(summary_unlabelled, summary_perm_unlabelled)
    if not perm_report.all_within_tolerance:
        return M3EligibilityVerdict(
            status="INELIGIBLE_M3_MARGINAL_MISMATCH",
            substrate_id=sub_id,
            N=int(N),
            lambda_value=float(lambda_value),
            summary=target_summary,
            match_report=match_report,
            eligibility_reason=(
                "topology-coupling decoupling invariant failed: "
                "non-identity permutation mutated K_null marginal summary "
                f"(failed_marginal={perm_report.failed_marginal!r})"
            ),
            metadata={
                "base_seed": int(base_seed),
                "null_seed": int(eff_null_seed),
                "pre_summary_sha": summary_unlabelled.summary_sha256,
                "post_summary_sha": summary_perm_unlabelled.summary_sha256,
                "perm_match_report": {
                    "degree_wasserstein": float(perm_report.degree_wasserstein),
                    "spectral_radius_rel_err": float(perm_report.spectral_radius_rel_err),
                    "density_rel_err": float(perm_report.density_rel_err),
                    "failed_marginal": perm_report.failed_marginal,
                },
            },
        )

    return M3EligibilityVerdict(
        status="ELIGIBLE_M3",
        substrate_id=sub_id,
        N=int(N),
        lambda_value=float(lambda_value),
        summary=target_summary,
        match_report=match_report,
        eligibility_reason=(
            f"all five admissibility criteria pass: marginals match within "
            f"tolerance (failed_marginal=None), {distinct_pairs}/{pair_count} "
            f"precursor pairs distinct, ||K_null-K_p||_F={frob:.3e} > "
            f"{M3_TOL_NON_DEGENERATE:.3e}, marginal summary invariant under "
            f"node permutation"
        ),
        metadata={
            "base_seed": int(base_seed),
            "null_seed": int(eff_null_seed),
            "frobenius_distance": float(frob),
            "distinct_pair_count": int(distinct_pairs),
            "pair_count": int(pair_count),
            "preserved_topology_summary_sha256": target_summary.summary_sha256,
            "m3_salt": int(M3_TOPOLOGY_CONDITIONED_SALT),
            "lambda_value": float(lambda_value),
        },
    )


def realize_m3_null(
    substrate: Substrate,
    *,
    base_seed: int,
    null_seed: int,
    lambda_value: float,
    N: int,
) -> tuple[NDArray[np.float64], dict[str, Any]]:
    """Construct the M3 topology-conditioned K_null.

    Procedure (assumes verifier has already returned ``ELIGIBLE_M3``):

    1. Run :func:`verify_m3_eligibility`; refuse on non-ELIGIBLE.
    2. Extract the precursor summary again (deterministic — same
       (base_seed, lambda_value, N) yields bit-identical summary).
    3. Call :func:`topology_matched_resample` with the same rng_salt_mix
       the verifier used; the bit-identical replay guarantee means the
       realisation produces the exact K_null the verifier validated.
    4. Post-check: extracted summary of K_null matches the verifier's
       match-report; raise :class:`M3GeneratorDivergentError` on drift.

    Raises
    ------
    M3NotEligibleError
        Verifier refused the cell.
    M3GeneratorDivergentError
        Post-check observed a marginal drift the verifier missed
        (internal invariant violation; should be unreachable).
    """
    verdict = verify_m3_eligibility(
        substrate,
        N=int(N),
        lambda_value=float(lambda_value),
        base_seed=int(base_seed),
        null_seed=int(null_seed),
    )
    if verdict.status != _M3_ELIGIBLE:
        raise M3NotEligibleError(verdict)
    assert verdict.summary is not None  # noqa: S101  # verifier post-condition
    assert verdict.match_report is not None  # noqa: S101  # verifier post-condition

    block_labels = _substrate_block_labels(substrate, int(N))
    sub_id = str(substrate.id)

    rng_salt_mix = deterministic_mix_multi(
        int(base_seed),
        int(M3_TOPOLOGY_CONDITIONED_SALT),
        int(null_seed),
        int(_m3_substrate_id_hash(sub_id)),
        int(N),
        int(_m3_lambda_bits(float(lambda_value))),
    )
    K_null = topology_matched_resample(
        verdict.summary, null_seed=int(null_seed), rng_salt_mix=rng_salt_mix
    )

    # Post-check: marginals still inside tolerance.
    post_summary = extract_m3_topology_summary(K_null, substrate_block_labels=block_labels)
    post_report = _compare_m3_marginals(verdict.summary, post_summary)
    if not post_report.all_within_tolerance:
        raise M3GeneratorDivergentError(
            "M3 post-check: generator output marginals drifted out of tolerance "
            f"(failed_marginal={post_report.failed_marginal!r}); verifier "
            "should have caught this — internal invariant violation"
        )

    metadata: dict[str, Any] = {
        "null_strategy": M3_NULL_STRATEGY,
        "null_seed": int(null_seed),
        "m3_salt": int(M3_TOPOLOGY_CONDITIONED_SALT),
        "preserved_topology_summary_sha256": verdict.summary.summary_sha256,
        "post_summary_sha256": post_summary.summary_sha256,
        "match_report": {
            "degree_wasserstein": float(post_report.degree_wasserstein),
            "block_histogram_l1": float(post_report.block_histogram_l1),
            "spectral_radius_rel_err": float(post_report.spectral_radius_rel_err),
            "density_rel_err": float(post_report.density_rel_err),
            "all_within_tolerance": bool(post_report.all_within_tolerance),
            "failed_marginal": post_report.failed_marginal,
        },
        "eligibility_status": _M3_ELIGIBLE,
        "lambda_value": float(lambda_value),
    }
    return K_null, metadata


# ---------------------------------------------------------------------------
# Public API — realize_null
# ---------------------------------------------------------------------------


def _default_null_seed(strategy: NullStrategy, base_seed: int) -> int:
    """Locked null-seed formula. Tests can override; canonical sweep MUST NOT."""
    if strategy == "M1_INDEPENDENT_SEED":
        return int(base_seed) + NULL_SEED_OFFSET
    if strategy == "M2_TOPOLOGY_PRESERVING_SHUFFLE":
        return _default_null_seed_m2(int(base_seed))
    if strategy == "M3_TOPOLOGY_CONDITIONED":
        return _default_null_seed_m3(int(base_seed))
    # M6: deterministic mix of base_seed with the locked salt.
    return deterministic_mix(int(base_seed), M6_PLACEBO_SALT)


_M2_SHUFFLE_DOMAINS: Final[frozenset[str]] = frozenset(
    {"edge_weight", "node_payload", "injection_sequence"}
)


def realize_null(
    substrate: Substrate,
    *,
    strategy: NullStrategy,
    base_seed: int,
    N: int,
    lambda_value: float,
    null_seed: int | None = None,
    metadata_extra: Mapping[str, Any] | None = None,
    shuffle_domain: Literal["edge_weight", "node_payload", "injection_sequence"] = "edge_weight",
) -> NullRealization:
    """Realise one M1 / M6 / M2 null cohort K_baseline.

    Parameters
    ----------
    substrate
        Any object implementing :class:`d002c_substrates.Substrate`.
    strategy
        Mechanism choice. MUST be explicit — there is NO default.
    base_seed
        The precursor cohort seed this null is paired to. Integer in
        the signed-int64 range.
    N
        Cohort size (required).
    lambda_value
        Cell coordinate. Must be ≥ 0; M6 and M2 additionally require
        ``> 0`` (no ΔK to permute at λ=0).
    null_seed
        Optional override of the locked null-seed formula. ``None`` →
        the formula:

          * M1: ``base_seed + NULL_SEED_OFFSET`` (offset = 10000).
          * M6: ``deterministic_mix(base_seed, M6_PLACEBO_SALT)``.
          * M2 edge_weight:
            ``deterministic_mix(base_seed, M2_PLACEBO_SALT)`` (211).
          * M2 node_payload:
            ``deterministic_mix(base_seed, M2_NODE_PAYLOAD_SALT)`` (313).
          * M2 injection_sequence:
            ``deterministic_mix(base_seed, M2_INJECTION_SEQUENCE_SALT)`` (419).

        Tests that probe edge cases can override; the canonical sweep
        MUST pass ``None``.
    metadata_extra
        Optional caller-supplied provenance merged into the strategy
        metadata before sha computation.
    shuffle_domain
        For ``strategy=="M2_TOPOLOGY_PRESERVING_SHUFFLE"`` only: which
        M2 sub-domain to use. Defaults to ``"edge_weight"`` so the P2
        contract is preserved when this parameter is unset.

    Returns
    -------
    NullRealization
        Frozen dataclass with K_baseline + content-addressed sha.

    Raises
    ------
    D002GNullInvalid
        Invalid strategy, ``lambda_value < 0``, ``lambda_value <= 0``
        under M6 or M2, non-square / non-finite K, dtype mismatch,
        N < 2.
    BitIdenticalNullError
        M1 produced ``K_null == K_precursor`` bit-identically.
    M2NotEligibleError
        M2 strategy invoked on a cell the verifier refuses. Carries
        the :class:`M2EligibilityVerdict` as ``.verdict``.
    M2TopologyMutationError
        M2 realisation post-check observed a topology-hash drift —
        internal invariant break. Verifier should have screened this.
    """
    if strategy not in _VALID_STRATEGIES:
        raise D002GNullInvalid(
            f"strategy must be one of {sorted(_VALID_STRATEGIES)}; got {strategy!r}"
        )
    if shuffle_domain not in _M2_SHUFFLE_DOMAINS:
        raise D002GNullInvalid(
            f"shuffle_domain must be one of {sorted(_M2_SHUFFLE_DOMAINS)}; got {shuffle_domain!r}"
        )
    if shuffle_domain != "edge_weight" and strategy != "M2_TOPOLOGY_PRESERVING_SHUFFLE":
        raise D002GNullInvalid(
            f"shuffle_domain={shuffle_domain!r} is only valid for strategy "
            "'M2_TOPOLOGY_PRESERVING_SHUFFLE'"
        )
    if not math.isfinite(lambda_value) or lambda_value < 0.0:
        raise D002GNullInvalid(f"lambda_value must be finite and >= 0; got {lambda_value!r}")
    if int(N) < 2:
        raise D002GNullInvalid(f"N must be >= 2; got {N!r}")
    if strategy == "M6_PLACEBO_COUPLING" and lambda_value <= 0.0:
        raise D002GNullInvalid(
            "M6_PLACEBO_COUPLING requires lambda_value > 0 "
            "(no precursor delta to permute at lambda=0)"
        )
    if strategy == "M2_TOPOLOGY_PRESERVING_SHUFFLE" and lambda_value <= 0.0:
        raise D002GNullInvalid(
            "M2_TOPOLOGY_PRESERVING_SHUFFLE requires lambda_value > 0 "
            "(no ΔK to permute at lambda=0)"
        )
    if strategy == "M3_TOPOLOGY_CONDITIONED" and lambda_value <= 0.0:
        raise D002GNullInvalid(
            "M3_TOPOLOGY_CONDITIONED requires lambda_value > 0 "
            "(M3 conditions on K_precursor's marginal set; at λ=0 the "
            "precursor matches baseline so the marginal set degenerates)"
        )

    # Domain-aware default null seed for M2 sub-domains
    if null_seed is None and strategy == "M2_TOPOLOGY_PRESERVING_SHUFFLE":
        if shuffle_domain == "node_payload":
            effective_null_seed = _default_null_seed_m2_node_payload(int(base_seed))
        elif shuffle_domain == "injection_sequence":
            effective_null_seed = _default_null_seed_m2_injection_sequence(int(base_seed))
        else:
            effective_null_seed = _default_null_seed_m2(int(base_seed))
    else:
        effective_null_seed = (
            int(null_seed) if null_seed is not None else _default_null_seed(strategy, base_seed)
        )

    if strategy == "M1_INDEPENDENT_SEED":
        K_null, mech_meta = _realize_m1(
            substrate,
            base_seed=int(base_seed),
            null_seed=effective_null_seed,
            lambda_value=float(lambda_value),
            N=int(N),
        )
    elif strategy == "M2_TOPOLOGY_PRESERVING_SHUFFLE":
        # Pre-check via verifier; fail-closed on any non-ELIGIBLE
        # verdict so the M2 realization layer never silently downgrades
        # to a no-op or to a different mechanism. Verifier choice is
        # routed by `shuffle_domain`; each sub-domain owns its own
        # admissibility ladder.
        if shuffle_domain == "edge_weight":
            verdict = verify_m2_eligibility(
                substrate,
                N=int(N),
                lambda_value=float(lambda_value),
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
            )
            if verdict.status != _M2_ELIGIBLE:
                raise M2NotEligibleError(verdict)
            K_null, mech_meta = _realize_m2(
                substrate,
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
                lambda_value=float(lambda_value),
                N=int(N),
            )
        elif shuffle_domain == "node_payload":
            verdict = verify_m2_node_payload_eligibility(
                substrate,
                N=int(N),
                lambda_value=float(lambda_value),
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
            )
            if verdict.status != _M2_NODE_PAYLOAD_ELIGIBLE:
                raise M2NotEligibleError(verdict)
            K_null, mech_meta = realize_m2_node_payload_null(
                substrate,
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
                lambda_value=float(lambda_value),
                N=int(N),
            )
        else:  # shuffle_domain == "injection_sequence"
            verdict = verify_m2_injection_sequence_eligibility(
                substrate,
                N=int(N),
                lambda_value=float(lambda_value),
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
            )
            if verdict.status != _M2_INJECTION_SEQUENCE_ELIGIBLE:
                raise M2NotEligibleError(verdict)
            K_null, mech_meta = realize_m2_injection_sequence_null(
                substrate,
                base_seed=int(base_seed),
                null_seed=effective_null_seed,
                lambda_value=float(lambda_value),
                N=int(N),
            )
    elif strategy == "M3_TOPOLOGY_CONDITIONED":
        K_null, mech_meta = realize_m3_null(
            substrate,
            base_seed=int(base_seed),
            null_seed=effective_null_seed,
            lambda_value=float(lambda_value),
            N=int(N),
        )
    else:
        K_null, mech_meta = _realize_m6(
            substrate,
            base_seed=int(base_seed),
            null_seed=effective_null_seed,
            lambda_value=float(lambda_value),
            N=int(N),
        )

    if K_null.dtype != np.float64:
        K_null = K_null.astype(np.float64, copy=False)

    metadata: dict[str, Any] = dict(mech_meta)
    if metadata_extra is not None:
        for k, v in metadata_extra.items():
            metadata[str(k)] = v

    sha = _realization_sha(
        strategy=strategy,
        base_seed=int(base_seed),
        null_seed=effective_null_seed,
        lambda_value=float(lambda_value),
        substrate_id=str(substrate.id),
        N=int(N),
        metadata=metadata,
        K_baseline=K_null,
    )

    return NullRealization(
        K_baseline=K_null,
        strategy=strategy,
        base_seed=int(base_seed),
        null_seed=int(effective_null_seed),
        lambda_value=float(lambda_value),
        substrate_id=str(substrate.id),
        N=int(N),
        metadata=metadata,
        generated_at=_now_iso(),
        payload_sha256=sha,
    )


__all__ = [
    "BitIdenticalNullError",
    "D002GNullInvalid",
    "M2EligibilityStatus",
    "M2EligibilityVerdict",
    "M2NotEligibleError",
    "M2TopologyMutationError",
    "M2_PLACEBO_SALT",
    "M2_NODE_PAYLOAD_SALT",
    "M2_INJECTION_SEQUENCE_SALT",
    "M3EligibilityStatus",
    "M3EligibilityVerdict",
    "M3GeneratorDivergentError",
    "M3MarginalMatchReport",
    "M3NotEligibleError",
    "M3TopologySummary",
    "M3_GENERATOR_MAX_ITERATIONS",
    "M3_NULL_STRATEGY",
    "M3_PRECURSOR_ENSEMBLE_SIZE",
    "M3_TOL_DEGREE_WASSERSTEIN",
    "M3_TOL_DENSITY",
    "M3_TOL_MARGINAL",
    "M3_TOL_NON_DEGENERATE",
    "M3_TOL_SPECTRAL_RADIUS",
    "M3_TOPOLOGY_CONDITIONED_SALT",
    "M6InsufficientCandidatePool",
    "M6_PLACEBO_SALT",
    "NULL_SEED_OFFSET",
    "NullRealization",
    "NullStrategy",
    "R2_B_RANDOM_SITE_SEED",
    "deterministic_mix",
    "deterministic_mix_multi",
    "extract_m3_topology_summary",
    "realize_null",
    "realize_m2_node_payload_null",
    "realize_m2_injection_sequence_null",
    "realize_m3_null",
    "topology_matched_resample",
    "verify_m2_eligibility",
    "verify_m2_node_payload_eligibility",
    "verify_m2_injection_sequence_eligibility",
    "verify_m3_eligibility",
]
