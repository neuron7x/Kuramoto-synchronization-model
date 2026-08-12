# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Bind the four manifold contracts into one immutable physics-evidence capsule.

:class:`PhysicsEvidenceCapsuleShape` is the seam where a Physics v2 run becomes a
single, deterministic, replayable evidence object. It binds:

* a :class:`~physics_contracts.manifold.contracts.MarketCausalGraphSnapshot`
  (by ``snapshot_id``),
* a :class:`~physics_contracts.manifold.ricci_trace.RicciFlowTrace`
  (by ``trace_digest``),
* a :class:`~physics_contracts.manifold.sync_frame.SynchronizationManifoldFrame`
  (by ``frame_digest``),
* a :class:`~physics_contracts.manifold.negative_controls.PhysicsNegativeControlReport`
  (by ``report_digest``),

and reuses the already-shipped evidence machinery — the
``analytics.signals.claim_maturity`` ladder, the
``instrument_validation.verdict.Verdict`` enum, and the contracts-layer
``EvidenceCapsuleShape`` (whose fail-closed real-data-tier rule we delegate to)
— rather than forking a parallel capsule.

Fail-closed falsifiers (every one raises ``ValueError``):

* no dataset hash, or no replay command;
* a law in ``laws_exercised`` with no registered witness (when a witness set is
  supplied by the readiness gate);
* an empty ``falsifiers_passed`` set (a claim with no executed falsifier);
* a claim-maturity tier above what the evidence supports (real-data tier without
  real data; alternatives-eliminated tier without surviving the null battery).

The capsule digest is a deterministic content address: it changes if *any* bound
input changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from analytics.signals.claim_maturity import LADDER
from instrument_validation.verdict import Verdict
from physics_contracts.manifold.contracts import (
    EvidenceCapsuleShape,
    LicensedDataStatus,
    canonical_digest,
    resolve_data_status,
)

__all__ = [
    "PhysicsEvidenceCapsuleShape",
    "bind_physics_evidence",
]

_LADDER_RANK: Final[dict[str, int]] = {state: i for i, state in enumerate(LADDER)}
# Lowest tier that asserts the candidate beat its negative-control battery.
_ALTERNATIVES_ELIMINATED_RANK: Final[int] = _LADDER_RANK["ALTERNATIVES_ELIMINATED"]
_VALID_VERDICTS: Final[frozenset[str]] = frozenset(v.value for v in Verdict)


@dataclass(frozen=True, slots=True)
class PhysicsEvidenceCapsuleShape:
    """Immutable, deterministic binding of the four manifold contracts.

    The component objects are referenced by their content-address digests so the
    capsule is small, comparable, and changes whenever any bound input changes.
    """

    run_id: str
    dataset_fingerprint: str
    code_sha: str
    snapshot_id: str
    ricci_trace_digest: str
    sync_frame_digest: str
    comparison_report_digest: str
    laws_exercised: tuple[str, ...]
    falsifiers_passed: tuple[str, ...]
    falsifiers_failed: tuple[str, ...]
    claim_maturity: str
    verdict: str
    replay_command: str
    data_status: LicensedDataStatus

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id),
            ("dataset_fingerprint", self.dataset_fingerprint),
            ("code_sha", self.code_sha),
            ("snapshot_id", self.snapshot_id),
            ("ricci_trace_digest", self.ricci_trace_digest),
            ("sync_frame_digest", self.sync_frame_digest),
            ("comparison_report_digest", self.comparison_report_digest),
        ):
            if not value:
                raise ValueError(
                    f"PhysicsEvidenceCapsuleShape VIOLATED: required field {name!r} is empty"
                )
        if not self.replay_command:
            raise ValueError(
                "PhysicsEvidenceCapsuleShape VIOLATED: replay_command is empty — "
                "an evidence capsule with no replay command is not reproducible"
            )
        if not self.laws_exercised:
            raise ValueError(
                "PhysicsEvidenceCapsuleShape VIOLATED: laws_exercised is empty — "
                "a physics capsule must name the laws it exercised"
            )
        if not self.falsifiers_passed:
            raise ValueError(
                "PhysicsEvidenceCapsuleShape VIOLATED: falsifiers_passed is empty — "
                "a claim with no executed falsifier has no witness"
            )
        if self.claim_maturity not in _LADDER_RANK:
            raise ValueError(
                f"PhysicsEvidenceCapsuleShape VIOLATED: claim_maturity {self.claim_maturity!r} "
                "is not a known claim-maturity ladder tier"
            )
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"PhysicsEvidenceCapsuleShape VIOLATED: verdict {self.verdict!r} "
                f"not in {sorted(_VALID_VERDICTS)}"
            )

    @property
    def capsule_digest(self) -> str:
        """Deterministic content-address; changes if any bound input changes."""

        return canonical_digest(
            {
                "run_id": self.run_id,
                "dataset_fingerprint": self.dataset_fingerprint,
                "code_sha": self.code_sha,
                "snapshot_id": self.snapshot_id,
                "ricci_trace_digest": self.ricci_trace_digest,
                "sync_frame_digest": self.sync_frame_digest,
                "comparison_report_digest": self.comparison_report_digest,
                "laws_exercised": sorted(self.laws_exercised),
                "falsifiers_passed": sorted(self.falsifiers_passed),
                "falsifiers_failed": sorted(self.falsifiers_failed),
                "claim_maturity": self.claim_maturity,
                "verdict": self.verdict,
                "replay_command": self.replay_command,
                "data_status": self.data_status.value,
            }
        )


def bind_physics_evidence(
    *,
    run_id: str,
    dataset_fingerprint: str,
    code_sha: str,
    config_hash: str,
    snapshot_id: str,
    ricci_trace_digest: str,
    sync_frame_digest: str,
    comparison_report_digest: str,
    laws_exercised: tuple[str, ...],
    falsifiers_passed: tuple[str, ...],
    falsifiers_failed: tuple[str, ...],
    claim_maturity: str,
    verdict: str,
    replay_command: str,
    nulls_survived: bool,
    witnessed_laws: frozenset[str] | None = None,
) -> PhysicsEvidenceCapsuleShape:
    """Bind the manifold contracts into a fail-closed evidence capsule.

    Beyond the structural checks in ``__post_init__`` this enforces the two
    cross-cutting evidence falsifiers:

    * **law without witness** — when ``witnessed_laws`` is supplied (by the
      readiness gate, which holds the law→witness index), every law in
      ``laws_exercised`` must appear in it.
    * **claim tier above evidence tier** — the real-data-tier rule is delegated
      to ``EvidenceCapsuleShape`` (real-data maturity requires available data),
      and an ``ALTERNATIVES_ELIMINATED``-or-higher tier additionally requires
      that the negative-control battery was actually survived.
    """

    data_status = resolve_data_status(dataset_fingerprint)

    if witnessed_laws is not None:
        unwitnessed = sorted(law for law in laws_exercised if law not in witnessed_laws)
        if unwitnessed:
            raise ValueError(
                "PhysicsEvidenceCapsuleShape VIOLATED: laws_exercised contains laws with no "
                f"registered witness: {unwitnessed}"
            )

    # Delegate the real-data-tier fail-closed rule to the shipped contract: it
    # raises if a DATA_UNAVAILABLE run asserts a real-data maturity tier.
    EvidenceCapsuleShape(
        run_id=run_id,
        dataset_fingerprint=dataset_fingerprint,
        config_hash=config_hash,
        code_commit=code_sha,
        laws_exercised=laws_exercised,
        falsifiers_passed=falsifiers_passed,
        falsifiers_failed=falsifiers_failed,
        comparison_report_digest=comparison_report_digest,
        claim_maturity=claim_maturity,
        data_status=data_status,
    )

    # Claim tier above evidence tier: alternatives-eliminated and above assert
    # the candidate beat its nulls; refuse that tier if it did not.
    if _LADDER_RANK.get(claim_maturity, -1) >= _ALTERNATIVES_ELIMINATED_RANK and not nulls_survived:
        raise ValueError(
            "PhysicsEvidenceCapsuleShape VIOLATED: claim_maturity "
            f"{claim_maturity!r} asserts the negative-control battery was survived, "
            "but nulls_survived=False — claim tier above evidence tier"
        )

    return PhysicsEvidenceCapsuleShape(
        run_id=run_id,
        dataset_fingerprint=dataset_fingerprint,
        code_sha=code_sha,
        snapshot_id=snapshot_id,
        ricci_trace_digest=ricci_trace_digest,
        sync_frame_digest=sync_frame_digest,
        comparison_report_digest=comparison_report_digest,
        laws_exercised=laws_exercised,
        falsifiers_passed=falsifiers_passed,
        falsifiers_failed=falsifiers_failed,
        claim_maturity=claim_maturity,
        verdict=verdict,
        replay_command=replay_command,
        data_status=data_status,
    )
