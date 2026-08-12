# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from . import ht1a, ht1b, ht2a, ht2c, ht3, ht7
from .dynamics import clamp
from .types import ParamDeltas, ReceptorActivation, ReceptorContext, ReceptorState


class ReceptorBank:
    """Aggregate receptor activations and parameter deltas."""

    def __init__(self, enabled_list: Optional[Sequence[str]] = None) -> None:
        ordered = [
            ("5ht3", ht3),
            ("5ht1b", ht1b),
            ("5ht2c", ht2c),
            ("5ht1a", ht1a),
            ("5ht7", ht7),
            ("5ht2a", ht2a),
        ]
        if enabled_list is not None:
            wanted = {name.lower() for name in enabled_list}
            ordered = [item for item in ordered if item[0].lower() in wanted]
        self._receptors: List[Tuple[str, object]] = ordered
        self._state: Dict[str, ReceptorState] = {
            name: ReceptorState() for name, _ in self._receptors
        }

    def run(self, ctx: ReceptorContext) -> Tuple[ReceptorActivation, ParamDeltas]:
        activations: ReceptorActivation = {}
        aggregate = ParamDeltas()
        for name, module in self._receptors:
            state = self._state[name]
            activation = module.compute_activation(ctx, state)
            activation = clamp(activation, 0.0, 1.0)
            activations[name] = activation
            deltas = module.compute_deltas(ctx, activation)
            aggregate = aggregate.combine(deltas)
            self._state[name] = state
        return activations, aggregate
