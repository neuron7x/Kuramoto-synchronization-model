#!/usr/bin/env python3
"""Deterministic AAR-PRO smoke check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from geosync_hpc.control import (
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
    compute_error,
    dispatch_action,
    persist_memory,
    prescribe_recovery,
    receive_afferentation,
    render_decision,
    seal_action_result_evidence,
    seal_model,
    start_episode,
    verify_chain,
)


def build_smoke_verdict() -> dict[str, bool | int | str]:
    """Run one sealed-prediction episode and return a deterministic summary."""

    expected = ExpectedResultModel(
        action_id="aar-pro-smoke-1",
        action_type="regime_observe",
        expected_result=(1.0, 0.0, -1.0),
        expected_result_variance=(1.0, 1.0, 1.0),
        context_signature=(0.25, 0.5, 0.75),
        model_created_seq=1,
        action_started_seq=2,
        error_threshold=0.1,
        rollback_threshold=1.0,
    )
    observed = ObservedActionResult(
        action_id="aar-pro-smoke-1",
        observed_seq=3,
        observed_result=(1.0, 0.0, -1.0),
        reverse_afferentation_present=True,
    )
    witness = accept_action_result(expected, observed)
    evidence = seal_action_result_evidence(expected, observed, witness)
    recovery = prescribe_recovery(witness)

    episode = start_episode("aar-pro-smoke-episode", b"intent:regime_observe", 0)
    episode = seal_model(episode, expected, 1)
    episode = dispatch_action(episode, b"dispatch:regime_observe", 2)
    episode = receive_afferentation(episode, observed, 3)
    episode = compute_error(episode, 4)
    episode = render_decision(episode, 5)
    episode = persist_memory(episode, 6)

    return {
        "accepted": witness.accepted,
        "chain_verified": verify_chain(episode),
        "evidence_digest": evidence.evidence_digest,
        "episode_closed": episode.closed,
        "last_phase": episode.records[-1].phase.value,
        "model_update_allowed": recovery.model_update_allowed,
        "phase_count": len(episode.records),
        "rollback_required": witness.rollback_required,
        "recovery_action": recovery.actions[0].value,
        "schema_version": "AAR-PRO-V1-SMOKE",
        "status": witness.status.value,
    }


def main() -> None:
    print(json.dumps(build_smoke_verdict(), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
