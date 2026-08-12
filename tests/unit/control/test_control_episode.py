# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``geosync_hpc.control.control_episode``.

Falsifier probes (each test references the invariant it defends):

    Probe A: Strip the state-machine ordering check.
             -> tests 4, 7, 9, 13, 17, 18
    Probe B: Allow seq to repeat or decrease.
             -> tests 2, 21
    Probe C: Replace sha256 with a constant or weaken the chain link.
             -> tests 23, 24, 25
    Probe D: Allow phase replay on a closed episode.
             -> test 20
    Probe E: Re-introduce ``created_before_action`` / ``prior_confidence``
             / ``reentry_threshold`` field laundering.
             -> test 29
    Probe F: Pull a forbidden runtime import (trading, execution, ...).
             -> test 30
    Probe G: Skip running the comparator at ERROR_COMPUTED.
             -> tests 14, 15, 16
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest

from geosync_hpc.control import (
    ActionResultStatus,
    ControlEpisode,
    EpisodePhase,
    EpisodeRecord,
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
EPISODE_SRC: Path = REPO_ROOT / "geosync_hpc" / "control" / "control_episode.py"


def _field_names(model: Any) -> set[str]:
    return {field.name for field in dataclasses.fields(model)}


def _make_expected(
    model_seq: int = 2,
    action_seq: int = 3,
    expected_result: tuple[float, ...] = (1.0, 0.0),
) -> ExpectedResultModel:
    return ExpectedResultModel(
        action_id="a-1",
        action_type="trade",
        expected_result=expected_result,
        expected_result_variance=None,
        context_signature=(0.5, 0.5),
        model_created_seq=model_seq,
        action_started_seq=action_seq,
        error_threshold=0.1,
        rollback_threshold=0.5,
    )


def _make_observed(
    observed_seq: int = 4,
    observed_result: tuple[float, ...] = (1.0, 0.0),
) -> ObservedActionResult:
    return ObservedActionResult(
        action_id="a-1",
        observed_seq=observed_seq,
        observed_result=observed_result,
    )


def _drive_full_chain(
    *,
    intent_seq: int = 1,
    model_seq: int = 2,
    action_seq: int = 3,
    observed_seq: int = 4,
    error_seq: int = 5,
    decision_seq: int = 6,
    memory_seq: int = 7,
    expected_result: tuple[float, ...] = (1.0, 0.0),
    observed_result: tuple[float, ...] = (1.0, 0.0),
    episode_id: str = "ep-test",
) -> ControlEpisode:
    expected = _make_expected(model_seq, action_seq, expected_result)
    observed = _make_observed(observed_seq, observed_result)
    episode = start_episode(episode_id, b"intent", intent_seq)
    episode = seal_model(episode, expected, model_seq)
    episode = dispatch_action(episode, b"action", action_seq)
    episode = receive_afferentation(episode, observed, observed_seq)
    episode = compute_error(episode, error_seq)
    episode = render_decision(episode, decision_seq)
    episode = persist_memory(episode, memory_seq)
    return episode


def test_01_start_episode_requires_nonempty_episode_id() -> None:
    """1: empty episode_id is rejected."""
    with pytest.raises(ValueError):
        start_episode("", b"intent", 0)


def test_02_start_episode_requires_seq_geq_zero() -> None:
    """2: seq < 0 is rejected."""
    with pytest.raises(ValueError):
        start_episode("e", b"intent", -1)


def test_03_start_episode_genesis_record_invariants() -> None:
    """3: genesis record has phase INTENT_DECLARED and empty parent_chain_hash."""
    episode = start_episode("e", b"intent", 0)
    assert len(episode.records) == 1
    assert episode.records[0].phase is EpisodePhase.INTENT_DECLARED
    assert episode.records[0].parent_chain_hash == ""


def test_04_seal_model_before_start_raises() -> None:
    """4: seal_model on empty episode is rejected (state machine)."""
    bare = ControlEpisode(episode_id="e")
    with pytest.raises(ValueError):
        seal_model(bare, _make_expected(), 2)


def test_05_seal_model_with_none_expected_raises() -> None:
    """5: passing expected=None at seal raises ValueError."""
    episode = start_episode("e", b"intent", 1)
    with pytest.raises(ValueError):
        seal_model(episode, None, 2)  # type: ignore[arg-type]


def test_06_seal_model_seq_must_match_model_created_seq() -> None:
    """6: seq mismatch with expected.model_created_seq is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    with pytest.raises(ValueError):
        seal_model(episode, expected, 99)


def test_07_dispatch_action_before_seal_raises() -> None:
    """7: dispatch_action without prior seal_model is rejected."""
    episode = start_episode("e", b"intent", 1)
    with pytest.raises(ValueError):
        dispatch_action(episode, b"action", 2)


def test_08_dispatch_action_seq_must_match_action_started_seq() -> None:
    """8: dispatch_action seq mismatch with expected.action_started_seq."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    with pytest.raises(ValueError):
        dispatch_action(episode, b"action", 99)


def test_09_receive_afferentation_before_dispatch_raises() -> None:
    """9: receive_afferentation without prior dispatch is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    with pytest.raises(ValueError):
        receive_afferentation(episode, _make_observed(observed_seq=4), 4)


def test_10_receive_afferentation_with_none_observed_raises() -> None:
    """10: passing observed=None at afferentation raises ValueError."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    with pytest.raises(ValueError):
        receive_afferentation(episode, None, 4)  # type: ignore[arg-type]


def test_11_receive_afferentation_seq_mismatch_raises() -> None:
    """11: seq != observed.observed_seq is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    observed = _make_observed(observed_seq=4)
    with pytest.raises(ValueError):
        receive_afferentation(episode, observed, 5)


def test_12_out_of_order_afferentation_annuls_episode_with_invalid_witness() -> None:
    """12: observed_seq <= action_started_seq closes with rollback witness."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    observed = ObservedActionResult(
        action_id="a-1",
        observed_seq=3,
        observed_result=(1.0, 0.0),
    )

    rejected = receive_afferentation(episode, observed, 3)

    assert rejected.closed is True
    assert rejected.witness is not None
    assert rejected.witness.status is ActionResultStatus.INVALID_INPUT
    assert rejected.witness.rollback_required is True
    assert rejected.witness.reason.startswith("SEQUENCE_ORDER_INVALID")
    assert rejected.records[-2].phase is EpisodePhase.AFFERENTATION_RECEIVED
    assert rejected.records[-1].phase is EpisodePhase.ERROR_COMPUTED
    assert verify_chain(rejected) is True
    with pytest.raises(ValueError, match="episode is closed"):
        render_decision(rejected, rejected.records[-1].seq + 1)


def test_13_compute_error_before_afferentation_raises() -> None:
    """13: compute_error without prior afferentation is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    with pytest.raises(ValueError):
        compute_error(episode, 4)


def test_14_compute_error_invokes_comparator_and_stores_witness() -> None:
    """14: compute_error stores a non-None witness in episode.witness."""
    episode = _drive_full_chain()
    assert episode.witness is not None
    assert episode.records[4].phase is EpisodePhase.ERROR_COMPUTED


def test_15_compute_error_exact_match_yields_sanctioned() -> None:
    """15: exact-match Expected/Observed -> SANCTIONED_MATCH."""
    episode = _drive_full_chain(
        expected_result=(1.0, 0.0),
        observed_result=(1.0, 0.0),
    )
    assert episode.witness is not None
    assert episode.witness.status is ActionResultStatus.SANCTIONED_MATCH


def test_16_compute_error_far_breach_yields_rollback() -> None:
    """16: far-out observation -> ROLLBACK_REQUIRED witness."""
    episode = _drive_full_chain(
        expected_result=(1.0, 0.0),
        observed_result=(10.0, 10.0),
    )
    assert episode.witness is not None
    assert episode.witness.status is ActionResultStatus.ROLLBACK_REQUIRED


def test_17_render_decision_before_error_raises() -> None:
    """17: render_decision without prior compute_error is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    episode = receive_afferentation(episode, _make_observed(observed_seq=4), 4)
    with pytest.raises(ValueError):
        render_decision(episode, 5)


def test_18_persist_memory_before_decision_raises() -> None:
    """18: persist_memory without prior render_decision is rejected."""
    episode = start_episode("e", b"intent", 1)
    expected = _make_expected(model_seq=2, action_seq=3)
    episode = seal_model(episode, expected, 2)
    episode = dispatch_action(episode, b"action", 3)
    episode = receive_afferentation(episode, _make_observed(observed_seq=4), 4)
    episode = compute_error(episode, 5)
    with pytest.raises(ValueError):
        persist_memory(episode, 6)


def test_19_persist_memory_sets_closed_true() -> None:
    """19: persist_memory closes the episode."""
    episode = _drive_full_chain()
    assert episode.closed is True
    assert episode.records[-1].phase is EpisodePhase.MEMORY_ANCHORED


def test_20_closed_episode_rejects_all_phase_calls() -> None:
    """20: every phase function refuses on a closed episode."""
    episode = _drive_full_chain()
    expected = _make_expected(model_seq=8, action_seq=9)
    observed = _make_observed(observed_seq=10)

    with pytest.raises(ValueError):
        seal_model(episode, expected, 8)
    with pytest.raises(ValueError):
        dispatch_action(episode, b"x", 8)
    with pytest.raises(ValueError):
        receive_afferentation(episode, observed, 8)
    with pytest.raises(ValueError):
        compute_error(episode, 8)
    with pytest.raises(ValueError):
        render_decision(episode, 8)
    with pytest.raises(ValueError):
        persist_memory(episode, 8)
    fresh = start_episode("fresh", b"intent", 0)
    assert fresh.closed is False


def test_21_seq_must_strictly_increase_across_phases() -> None:
    """21: equal seq across consecutive phases is rejected."""
    episode = start_episode("e", b"intent", 5)
    expected = _make_expected(model_seq=5, action_seq=6)
    with pytest.raises(ValueError):
        seal_model(episode, expected, 5)


def test_22_determinism_identical_inputs_yield_identical_chain_hashes() -> None:
    """22: identical inputs through the full chain yield identical hashes."""
    episode_a = _drive_full_chain(episode_id="ep")
    episode_b = _drive_full_chain(episode_id="ep")
    hashes_a = tuple(r.chain_hash for r in episode_a.records)
    hashes_b = tuple(r.chain_hash for r in episode_b.records)
    assert hashes_a == hashes_b


def test_23_tamper_detection_payload_digest_alteration() -> None:
    """23: forging a payload_digest breaks verify_chain."""
    episode = _drive_full_chain()
    forged_digest = hashlib.sha256(b"forged").hexdigest()
    target = episode.records[3]
    forged_record = dataclasses.replace(target, payload_digest=forged_digest)
    forged_records = episode.records[:3] + (forged_record,) + episode.records[4:]
    forged_episode = object.__new__(ControlEpisode)
    object.__setattr__(forged_episode, "episode_id", episode.episode_id)
    object.__setattr__(forged_episode, "records", forged_records)
    object.__setattr__(forged_episode, "expected", episode.expected)
    object.__setattr__(forged_episode, "observed", episode.observed)
    object.__setattr__(forged_episode, "witness", episode.witness)
    object.__setattr__(forged_episode, "closed", episode.closed)
    assert verify_chain(forged_episode) is False
    assert verify_chain(episode) is True


def test_24_tamper_detection_chain_hash_alteration() -> None:
    """24: forging the chain_hash of a middle record breaks verify_chain."""
    episode = _drive_full_chain()
    target = episode.records[2]
    forged_chain_hash = hashlib.sha256(b"not-the-real-link").hexdigest()
    forged_record = dataclasses.replace(target, chain_hash=forged_chain_hash)
    forged_records = episode.records[:2] + (forged_record,) + episode.records[3:]
    forged_episode = object.__new__(ControlEpisode)
    object.__setattr__(forged_episode, "episode_id", episode.episode_id)
    object.__setattr__(forged_episode, "records", forged_records)
    object.__setattr__(forged_episode, "expected", episode.expected)
    object.__setattr__(forged_episode, "observed", episode.observed)
    object.__setattr__(forged_episode, "witness", episode.witness)
    object.__setattr__(forged_episode, "closed", episode.closed)
    assert verify_chain(forged_episode) is False


def test_25_genesis_and_subsequent_parent_chain_hash_links() -> None:
    """25: genesis parent_chain_hash="", others equal prior chain_hash."""
    episode = _drive_full_chain()
    assert episode.records[0].parent_chain_hash == ""
    for prior, current in zip(episode.records, episode.records[1:], strict=False):
        assert current.parent_chain_hash == prior.chain_hash


def test_26_episode_is_frozen_dataclass() -> None:
    """26: attempting to mutate records on a frozen episode raises."""
    episode = start_episode("e", b"intent", 0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(episode, "records", ())


def test_27_phase_functions_return_new_episodes_input_unchanged() -> None:
    """27: seal_model returns a NEW episode; input.records unchanged."""
    episode = start_episode("e", b"intent", 1)
    snapshot_records = episode.records
    expected = _make_expected(model_seq=2, action_seq=3)
    new_episode = seal_model(episode, expected, 2)
    assert new_episode is not episode
    assert episode.records == snapshot_records
    assert len(new_episode.records) == len(snapshot_records) + 1


def test_28_episode_phase_enum_has_seven_members_in_spec_order() -> None:
    """28: EpisodePhase enum size + order must match the spec."""
    members = list(EpisodePhase)
    assert len(members) == 7
    expected_order = [
        EpisodePhase.INTENT_DECLARED,
        EpisodePhase.MODEL_SEALED,
        EpisodePhase.ACTION_DISPATCHED,
        EpisodePhase.AFFERENTATION_RECEIVED,
        EpisodePhase.ERROR_COMPUTED,
        EpisodePhase.DECISION_RENDERED,
        EpisodePhase.MEMORY_ANCHORED,
    ]
    assert members == expected_order


def test_29_no_forbidden_legacy_fields_present() -> None:
    """29: no created_before_action / prior_confidence / reentry_threshold."""
    forbidden = {"created_before_action", "prior_confidence", "reentry_threshold"}
    for klass in (ControlEpisode, EpisodeRecord):
        leaked = _field_names(klass) & forbidden
        assert not leaked, f"{klass.__name__} leaked forbidden field: {leaked}"


def test_30_import_boundary_no_runtime_modules() -> None:
    """30: AST-parse the module and reject forbidden runtime imports."""
    forbidden = {"trading", "execution", "policy", "forecast", "nak_controller"}
    source = EPISODE_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            assert root not in forbidden, f"forbidden import-from: {module}"


def test_29b_record_payload_digest_must_be_sha256_hex() -> None:
    """29b: EpisodeRecord rejects non-hex-64 payload digests at construction."""
    with pytest.raises(ValueError):
        EpisodeRecord(
            phase=EpisodePhase.INTENT_DECLARED,
            seq=0,
            payload_digest="not-hex",
            parent_chain_hash="",
            chain_hash=hashlib.sha256(b"x").hexdigest(),
        )
