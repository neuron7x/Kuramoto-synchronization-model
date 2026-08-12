# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import numpy as np

from rl.core.actor_critic import ActorCriticFHMC
from runtime.thermo_controller import FHMC


def test_actorcritic_action_shape():
    fhmc = FHMC.from_yaml("configs/fhmc.yaml")
    agent = ActorCriticFHMC(128, 8, fhmc)
    state = np.zeros(128, dtype=np.float32)
    action = agent.act(state)
    assert action.shape == (8,)
