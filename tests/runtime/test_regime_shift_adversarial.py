# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from runtime.behavior_contract import ActionClass, SystemState, get_current_state, tacl_gate


def test_regime_shift_blocks_systemic_action() -> None:
    state = get_current_state(F_current=1.3, F_baseline=1.0)
    assert state is SystemState.CRISIS

    decision = tacl_gate(
        module_name="thermo_controller",
        action_class=ActionClass.A2_SYSTEMIC,
        system_state=state,
        F_now=1.0,
        F_next=1.0,
        epsilon=0.1,
        recovery_path=True,
        dual_approved=True,
    )

    assert decision.allowed is False
    assert decision.reason == "crisis_downgrade"
