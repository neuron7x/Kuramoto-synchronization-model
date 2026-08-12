# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""OPS-001 recovery drill — executes the two load-bearing fail-closed recovery
paths and emits a deterministic evidence report.

Drills:
  1. Cryptobiosis phase-transition survival (core.neuro.cryptobiosis):
     ACTIVE → DORMANT (position multiplier EXACTLY 0.0, INV-CB1) under acute
     distress, then a staged, non-decreasing rehydration ramp back to ACTIVE
     (INV-CB4). Proves the system can exit and re-enter the threat space.
  2. Kill-switch failover (runtime.kill_switch): activate → halted + audited →
     deactivate → recovered + audited, on an isolated non-persistent manager.

The report is deterministic (no wall-clock, no RNG) so its SHA-256 is stable.
Run: ``python -m tools.readiness.run_recovery_drill`` (writes the artifact and
exits non-zero if any drill invariant fails — fail-closed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.neuro.cryptobiosis import (
    CryptobiosisConfig,
    CryptobiosisController,
    CryptobiosisState,
)
from runtime.kill_switch import KillSwitchManager, KillSwitchReason

ARTIFACT = Path("governance/evidence/ops001_recovery_drill_report.json")


def _cryptobiosis_drill() -> dict[str, Any]:
    """ACTIVE → DORMANT → REHYDRATING → ACTIVE under an acute-then-clearing shock."""
    cfg = CryptobiosisConfig(entry_threshold=0.85, exit_threshold=0.60, n_rehydration_stages=4)
    ctrl = CryptobiosisController(cfg)

    trajectory: list[dict[str, Any]] = []
    # Acute distress shock, then a sustained clearing of the threat.
    distress_sequence = [0.10, 0.95, 0.95, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
    dormant_multiplier_exact_zero = True
    rehydration_multipliers: list[float] = []

    for tick, distress in enumerate(distress_sequence):
        ctrl.update(distress)
        state = ctrl.state
        mult = ctrl.multiplier
        if state == CryptobiosisState.DORMANT and mult != 0.0:
            dormant_multiplier_exact_zero = False
        if state == CryptobiosisState.REHYDRATING:
            rehydration_multipliers.append(mult)
        trajectory.append(
            {"tick": tick, "distress": distress, "state": state.name, "multiplier": mult}
        )

    reached_dormant = any(s["state"] == "DORMANT" for s in trajectory)
    recovered_active = trajectory[-1]["state"] == "ACTIVE" and trajectory[-1]["multiplier"] == 1.0
    rehydration_monotone = all(
        b >= a for a, b in zip(rehydration_multipliers, rehydration_multipliers[1:])
    )

    checks = {
        "reached_dormant_under_shock": reached_dormant,
        "INV-CB1_dormant_multiplier_exact_zero": dormant_multiplier_exact_zero,
        "INV-CB4_rehydration_ramp_non_decreasing": rehydration_monotone,
        "INV-CB7_hysteresis_exit_below_entry": cfg.exit_threshold < cfg.entry_threshold,
        "recovered_to_active_full_size": recovered_active,
    }
    return {
        "drill": "cryptobiosis_phase_transition_survival",
        "runbook": "docs/runbook_disaster_recovery.md",
        "trajectory": trajectory,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _kill_switch_drill() -> dict[str, Any]:
    """activate → halted + audited → deactivate → recovered + audited (isolated)."""
    mgr = KillSwitchManager(cooldown_seconds=0.0, persist_path=None, _force_new=True)

    pre_active = mgr.is_active()
    activated = mgr.activate(reason=KillSwitchReason.MANUAL, source="ops001_drill", force=True)
    halted = mgr.is_active()
    deactivated = mgr.deactivate(reason="drill_recovery", source="ops001_drill")
    recovered = not mgr.is_active()

    audit = mgr.get_audit_log(limit=10)
    actions = [str(event.get("action")) for event in audit]

    checks = {
        "starts_inactive": not pre_active,
        "activation_halts_system": activated and halted,
        "deactivation_recovers_system": deactivated and recovered,
        "activate_event_audited": "activate" in actions,
        "deactivate_event_audited": "deactivate" in actions,
    }
    return {
        "drill": "kill_switch_failover",
        "runbook": "docs/runbook_kill_switch_failover.md",
        "audit_actions": actions,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_report() -> dict[str, Any]:
    crypto = _cryptobiosis_drill()
    kill = _kill_switch_drill()
    return {
        "artifact": "ops001_recovery_drill_report",
        "readiness_entry": "OPS-001",
        "schema": "readiness.evidence.v1",
        "drills": [crypto, kill],
        "all_passed": bool(crypto["passed"] and kill["passed"]),
    }


def main() -> int:
    report = build_report()
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "path": str(ARTIFACT)}))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
