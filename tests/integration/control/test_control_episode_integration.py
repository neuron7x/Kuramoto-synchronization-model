# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for the ControlEpisode chronology proof.

Each test exercises the full seven-phase chain through real data
classes plus the canonical ledger validator subprocess.
"""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from geosync_hpc.control import (
    ActionResultStatus,
    ControlEpisode,
    EpisodePhase,
    ExpectedResultModel,
    ObservedActionResult,
    compute_error,
    dispatch_action,
    persist_memory,
    receive_afferentation,
    render_decision,
    seal_model,
    start_episode,
    verify_chain,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[3]


def _build_chain(
    *,
    expected_result: tuple[float, ...],
    observed_result: tuple[float, ...],
    expected_variance: tuple[float, ...] | None = None,
    intent_seq: int = 1,
    model_seq: int = 2,
    action_seq: int = 3,
    observed_seq: int = 4,
    error_seq: int = 5,
    decision_seq: int = 6,
    memory_seq: int = 7,
) -> ControlEpisode:
    expected = ExpectedResultModel(
        action_id="trade-9001",
        action_type="market-buy",
        expected_result=expected_result,
        expected_result_variance=expected_variance,
        context_signature=(0.5, 0.5),
        model_created_seq=model_seq,
        action_started_seq=action_seq,
        error_threshold=0.1,
        rollback_threshold=0.5,
    )
    observed = ObservedActionResult(
        action_id="trade-9001",
        observed_seq=observed_seq,
        observed_result=observed_result,
    )
    episode = start_episode("episode-9001", b"intent-payload", intent_seq)
    episode = seal_model(episode, expected, model_seq)
    episode = dispatch_action(episode, b"action-payload", action_seq)
    episode = receive_afferentation(episode, observed, observed_seq)
    episode = compute_error(episode, error_seq)
    episode = render_decision(episode, decision_seq)
    episode = persist_memory(episode, memory_seq)
    return episode


def test_full_chain_sanctioned_match_end_to_end() -> None:
    """All seven phases drive cleanly through to a SANCTIONED witness."""
    episode = _build_chain(
        expected_result=(1.0, 0.0),
        observed_result=(1.0, 0.0),
        expected_variance=(0.01, 0.01),
    )
    assert episode.closed is True
    assert episode.witness is not None
    assert episode.witness.status is ActionResultStatus.SANCTIONED_MATCH
    assert len(episode.records) == 7
    phases = tuple(r.phase for r in episode.records)
    assert phases == (
        EpisodePhase.INTENT_DECLARED,
        EpisodePhase.MODEL_SEALED,
        EpisodePhase.ACTION_DISPATCHED,
        EpisodePhase.AFFERENTATION_RECEIVED,
        EpisodePhase.ERROR_COMPUTED,
        EpisodePhase.DECISION_RENDERED,
        EpisodePhase.MEMORY_ANCHORED,
    )
    assert verify_chain(episode) is True


def test_full_chain_rollback_path() -> None:
    """Large deviation -> ROLLBACK_REQUIRED, chain still verifies."""
    episode = _build_chain(
        expected_result=(1.0, 0.0),
        observed_result=(20.0, -20.0),
    )
    assert episode.witness is not None
    assert episode.witness.status is ActionResultStatus.ROLLBACK_REQUIRED
    # The verdict is rollback, not chain corruption.
    assert verify_chain(episode) is True


def test_out_of_order_phase_rejected() -> None:
    """compute_error before afferentation surfaces a ValueError in real chain."""
    expected = ExpectedResultModel(
        action_id="trade-1",
        action_type="market-buy",
        expected_result=(1.0,),
        expected_result_variance=None,
        context_signature=(0.5,),
        model_created_seq=2,
        action_started_seq=3,
        error_threshold=0.1,
        rollback_threshold=0.5,
    )
    episode = start_episode("ep", b"intent", 1)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    with pytest.raises(ValueError):
        compute_error(episode, 4)


def test_tamper_detection_end_to_end() -> None:
    """Forging payload_digest of one record -> verify_chain returns False."""
    episode = _build_chain(
        expected_result=(1.0, 0.0),
        observed_result=(1.0, 0.0),
    )
    assert verify_chain(episode) is True

    target = episode.records[2]
    forged_digest = hashlib.sha256(b"bogus").hexdigest()
    forged_record = dataclasses.replace(target, payload_digest=forged_digest)
    forged_records = episode.records[:2] + (forged_record,) + episode.records[3:]
    forged_episode = object.__new__(ControlEpisode)
    object.__setattr__(forged_episode, "episode_id", episode.episode_id)
    object.__setattr__(forged_episode, "records", forged_records)
    object.__setattr__(forged_episode, "expected", episode.expected)
    object.__setattr__(forged_episode, "observed", episode.observed)
    object.__setattr__(forged_episode, "witness", episode.witness)
    object.__setattr__(forged_episode, "closed", episode.closed)
    assert verify_chain(forged_episode) is False
    # Original still passes.
    assert verify_chain(episode) is True


def test_chain_proves_chronology_against_seq_lie() -> None:
    """Caller cannot launder a contradictory model_created_seq claim."""
    expected = ExpectedResultModel(
        action_id="trade-1",
        action_type="market-buy",
        expected_result=(1.0,),
        expected_result_variance=None,
        context_signature=(0.5,),
        model_created_seq=2,
        action_started_seq=3,
        error_threshold=0.1,
        rollback_threshold=0.5,
    )
    episode = start_episode("ep", b"intent", 1)
    # Caller claims seal_model.seq=99 but expected.model_created_seq=2.
    with pytest.raises(ValueError):
        seal_model(episode, expected, 99)


def test_comparator_witness_payload_cross_bind() -> None:
    """ERROR_COMPUTED.payload_digest == DECISION_RENDERED.payload_digest."""
    episode = _build_chain(
        expected_result=(1.0, 0.0),
        observed_result=(1.0, 0.0),
    )
    error_record = next(r for r in episode.records if r.phase is EpisodePhase.ERROR_COMPUTED)
    decision_record = next(r for r in episode.records if r.phase is EpisodePhase.DECISION_RENDERED)
    assert error_record.payload_digest == decision_record.payload_digest


def test_memory_anchors_chain_root() -> None:
    """MEMORY_ANCHORED payload_digest == sha256 of prior chain_hash bytes."""
    episode = _build_chain(
        expected_result=(1.0, 0.0),
        observed_result=(1.0, 0.0),
    )
    decision_record = episode.records[-2]
    memory_record = episode.records[-1]
    assert memory_record.phase is EpisodePhase.MEMORY_ANCHORED
    expected_digest = hashlib.sha256(decision_record.chain_hash.encode("utf-8")).hexdigest()
    assert memory_record.payload_digest == expected_digest


def test_ledger_validator_still_passes() -> None:
    """The acceptor ledger validator still succeeds (exit 0)."""
    validator = REPO_ROOT / "tools" / "archive" / "validate_action_result_acceptor.py"
    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    detail = f"validator failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.returncode == 0, detail
