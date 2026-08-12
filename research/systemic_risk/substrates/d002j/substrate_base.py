# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared data model for D-002J-P5 financial-mechanistic substrates.

A :class:`SubstrateInstance` is the frozen, hashable record returned by
every substrate's ``simulate(seed, params)`` method. It carries full
provenance (substrate id, seed, params), the latent ``state_trajectory``,
the named ``observable_outputs`` (whose keys MUST match the manifest's
``observable_outputs`` declaration for the corresponding substrate), and
free-form ``metadata`` describing the planted economic mechanism.

The substrates are GENERATIVE models, not real-data fits. Calibration to
real series is P7+ territory and is explicitly out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from numpy.typing import NDArray

SCHEMA_SUBSTRATE_INSTANCE: Final[str] = "D002J-SUBSTRATE-INSTANCE-v1"
"""Schema version stamped onto every :class:`SubstrateInstance`."""


@dataclass(frozen=True)
class SubstrateInstance:
    """Frozen record of one deterministic substrate simulation.

    Attributes
    ----------
    substrate_id:
        Canonical substrate id (matches the manifest ``substrate_id``).
    seed:
        Integer seed fed to ``numpy.random.default_rng``; same seed +
        same params => bit-identical ``state_trajectory`` and
        ``observable_outputs``.
    params:
        The resolved interpretable-parameter mapping actually used.
    state_trajectory:
        Latent economic state over time (shape: ``(T, n_state)`` or
        ``(T,)`` for scalar-state substrates).
    observable_outputs:
        Named observable series. Keys MUST equal the substrate's
        manifest ``observable_outputs`` list (asserted by P5 tests).
    metadata:
        Free-form provenance: mechanism family, schema version, planted
        shock parameters, and the forbidden-claim boundary.
    """

    substrate_id: str
    seed: int
    params: dict[str, float]
    state_trajectory: NDArray[Any]
    observable_outputs: dict[str, NDArray[Any]]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # bounds: provenance-completeness guard, not a physics clamp; a
        # substrate instance with an empty id or no observables is a
        # construction bug and must fail closed at creation time.
        if not self.substrate_id:
            raise ValueError("SubstrateInstance.substrate_id must be non-empty")
        if not self.observable_outputs:
            raise ValueError(
                f"SubstrateInstance({self.substrate_id!r}).observable_outputs "
                "must declare at least one named series"
            )
