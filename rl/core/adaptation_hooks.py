# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Catalog of adaptation hooks used by the RL stack."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdaptationHook:
    """Structured description of an adaptation hook."""

    name: str
    location: str
    trigger: str
    description: str


def list_adaptation_hooks() -> tuple[AdaptationHook, ...]:
    """Return the known adaptation hooks for RL adaptation pipelines."""

    return (
        AdaptationHook(
            name="safe_update_gate",
            location="rl.core.safe_update.SafeUpdateGate.evaluate",
            trigger="before parameter updates on each learning step",
            description="Risk-gated scale/rollback controller for online updates.",
        ),
        AdaptationHook(
            name="fractional_update",
            location="geosync_hpc.multifractal_opt.fractional_update",
            trigger="when applying gradients to policy/value parameters",
            description="Levy-stable fractional update used for adaptive parameter shifts.",
        ),
        AdaptationHook(
            name="ape_update",
            location="rl.core.habit_head.ape_update",
            trigger="after observing action prediction errors",
            description="Habit head update for value-free action preferences.",
        ),
        AdaptationHook(
            name="fhmc_sleep_replay",
            location="fhmc.sleep_engine.observe_transition",
            trigger="on every online transition",
            description="Sleep engine memory ingestion for offline consolidation.",
        ),
    )


__all__ = ["AdaptationHook", "list_adaptation_hooks"]
