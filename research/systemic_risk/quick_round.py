# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Research-speed ergonomics — one-call round through the Canonical Seven.

Closes the speed-of-thought gap of the audit. The full canonical
pipeline normally requires constructing five protocol-shaped
dataclasses (firewall, leakage, ladder, fragility, replication)
plus a :class:`GovernanceFSM`; that ceremony is appropriate for
production audit but slow during interactive research.

This module ships a single function

    quick_round(*, fsm_before, ...)  → CanonicalSevenOutcome

that accepts plain Python booleans / tuples / floats for the five
canonical evidence channels. It builds the protocol-shaped wrappers
internally and forwards to :func:`canonical_seven.run_canonical_seven`.

Pure-function API; no I/O. The slow path
:func:`run_canonical_seven` remains the production entry point.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical_seven import (
    CanonicalSevenInputs,
    CanonicalSevenOutcome,
    run_canonical_seven,
)
from .governance_fsm import GovernanceFSM

__all__ = [
    "quick_round",
]


# Shims must use ordinary (non-frozen) dataclasses so mypy treats
# their attributes as *settable* — this is what the `*ResultLike`
# Protocols in death_conditions.py expect at the type-check level.
# At runtime nothing mutates them; the shims are constructed once and
# discarded inside :func:`quick_round`.
@dataclass
class _LadderShim:
    losing_paths: tuple[str, ...]


@dataclass
class _LeakageShim:
    detected: bool


@dataclass
class _FragilityShim:
    fragile: bool


@dataclass
class _ReplicationShim:
    matched: bool


@dataclass
class _FirewallShim:
    passed_all: bool


def quick_round(
    *,
    fsm_before: GovernanceFSM,
    losing_paths: tuple[str, ...] | None = None,
    leakage_detected: bool | None = None,
    fragile: bool | None = None,
    replication_matched: bool | None = None,
    firewall_passed_all: bool | None = None,
) -> CanonicalSevenOutcome:
    """Run one canonical round from primitive inputs.

    Each evidence channel is independently optional; missing channels
    are treated as "no signal" by the death engine (the corresponding
    trigger does not fire).

    Parameters
    ----------
    fsm_before
        Current :class:`GovernanceFSM` of the claim.
    losing_paths
        Tuple of prosecutor names not beaten by the candidate. Empty
        tuple = "no losing paths". ``None`` = "ladder not run yet".
    leakage_detected
        ``True`` if any leakage sentinel fired. ``None`` = sentinel
        not run.
    fragile
        ``True`` if the parameter-fragility audit flipped the
        verdict. ``None`` = not run.
    replication_matched
        ``True`` if the rerun matched primary; ``False`` triggers
        KILL. ``None`` = capsule not run.
    firewall_passed_all
        ``True`` if the 8-gate firewall accepted the panel.
        ``None`` = firewall not run.

    Returns
    -------
    CanonicalSevenOutcome
        Same outcome shape as :func:`run_canonical_seven`.

    Examples
    --------
    A rerun-mismatch alone drives the FSM to ``REJECTED``::

        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            replication_matched=False,
        )
        assert out.fsm_after.state == "REJECTED"

    A clean round leaves state unchanged::

        out = quick_round(
            fsm_before=GovernanceFSM.initial(),
            losing_paths=(),
            leakage_detected=False,
            fragile=False,
            replication_matched=True,
            firewall_passed_all=True,
        )
        assert out.transition.action == "NONE"
    """
    inputs = CanonicalSevenInputs(
        firewall=(
            _FirewallShim(passed_all=firewall_passed_all)
            if firewall_passed_all is not None
            else None
        ),
        leakage=(_LeakageShim(detected=leakage_detected) if leakage_detected is not None else None),
        ladder=(_LadderShim(losing_paths=losing_paths) if losing_paths is not None else None),
        fragility=(_FragilityShim(fragile=fragile) if fragile is not None else None),
        replication=(
            _ReplicationShim(matched=replication_matched)
            if replication_matched is not None
            else None
        ),
    )
    return run_canonical_seven(inputs=inputs, fsm_before=fsm_before)
