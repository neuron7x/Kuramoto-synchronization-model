# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for :mod:`core.neuro.epistemic_audit`.

These tests pin the audit-ledger schema and the routing rules
between the three transition kinds (``advance``, ``halt``,
``reset``). The schema version string is part of the persisted
contract — bumping it without an explicit migration breaks
downstream consumers, so the version constant is asserted directly.
"""

from __future__ import annotations

import pytest

from core.neuro.epistemic_audit import (
    AUDIT_SCHEMA_VERSION,
    EpistemicAuditEntry,
    advance_entry,
    reset_entry,
)
from core.neuro.epistemic_validation import (
    EpistemicConfig,
    EpistemicState,
    initial_state,
    reset_with_external_proof,
    update,
)


def _cfg(
    *,
    invariant_floor: float = 0.2,
    initial_budget: float = 100.0,
    initial_weight: float = 0.6,
    temperature: float = 1.0,
    learning_rate: float = 0.5,
    decay_factor: float = 0.1,
) -> EpistemicConfig:
    return EpistemicConfig(
        invariant_floor=invariant_floor,
        initial_budget=initial_budget,
        initial_weight=initial_weight,
        temperature=temperature,
        learning_rate=learning_rate,
        decay_factor=decay_factor,
    )


def test_schema_version_is_pinned() -> None:
    assert AUDIT_SCHEMA_VERSION == "epistemic-audit/1", (
        f"audit schema version pinned in code as {AUDIT_SCHEMA_VERSION!r}; "
        "any change is a breaking-shape migration and must move with downstream consumers."
    )


def test_advance_entry_active_to_active() -> None:
    cfg = _cfg()
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 0.0, config=cfg)
    entry: EpistemicAuditEntry = advance_entry(s0, s1)
    assert entry["schema"] == AUDIT_SCHEMA_VERSION
    assert entry["transition"] == "advance"
    assert entry["seq"] == s1.seq
    assert entry["prev_hash"] == s0.state_hash
    assert entry["next_hash"] == s1.state_hash
    assert entry["phase"] == "active"
    assert entry["halt_reason"] == ""
    assert (
        entry["cost_paid"] >= 0.0
    ), f"INV-FE2: cost_paid must be ≥ 0 for an advance transition; got {entry['cost_paid']!r}."


def test_advance_entry_active_to_halt_classifies_as_halt() -> None:
    cfg = _cfg(initial_budget=0.05, temperature=1.0)
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 1000.0, config=cfg)
    assert s1.is_halted
    entry = advance_entry(s0, s1)
    assert entry["transition"] == "halt"
    assert entry["phase"] == "halted"
    assert entry["halt_reason"] in {"budget_exhausted", "weight_collapse"}


def test_advance_entry_rejects_non_advancing_seq() -> None:
    cfg = _cfg(initial_budget=0.05)
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 1000.0, config=cfg)
    sticky = update(halted, 0.0, 0.0, config=cfg)
    assert sticky is halted, "precondition: sticky halt is identity"
    with pytest.raises(ValueError, match="must be > prev.seq"):
        advance_entry(halted, sticky)


def test_reset_entry_carries_sentinel_cost() -> None:
    cfg = _cfg(initial_budget=0.05)
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 1000.0, config=cfg)
    proof = "f" * 64
    fresh = reset_with_external_proof(halted, external_proof_hex=proof, config=cfg)
    entry = reset_entry(halted, fresh)
    assert entry["transition"] == "reset"
    assert entry["seq"] == halted.seq + 1
    assert entry["phase"] == "active"
    assert entry["halt_reason"] == ""
    assert entry["cost_paid"] == -1.0, (
        "reset_entry must set cost_paid to the -1.0 sentinel; "
        f"got {entry['cost_paid']!r}; aggregators rely on the sign to filter resets out "
        "of thermodynamic-accounting sums."
    )
    assert entry["prev_hash"] == halted.state_hash
    assert entry["next_hash"] == fresh.state_hash


def test_reset_entry_rejects_non_halted_input() -> None:
    cfg = _cfg()
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 0.0, config=cfg)  # active
    # We need a fresh state to compare against; fabricate by claim
    # the second arg is a "reset" output. The function should
    # reject because s0 (the first arg) is not halted.
    with pytest.raises(ValueError, match="not 'halted'"):
        reset_entry(s0, s1)


def test_reset_entry_rejects_seq_discontinuity() -> None:
    cfg = _cfg(initial_budget=0.05)
    s0 = initial_state(cfg)
    halted = update(s0, 0.0, 1000.0, config=cfg)
    proof = "f" * 64
    fresh = reset_with_external_proof(halted, external_proof_hex=proof, config=cfg)
    # Advance fresh by one — fresh2.seq = halted.seq + 2, breaking
    # the +1 lineage rule.
    fresh2 = update(fresh, 0.5, 0.5, config=cfg)
    with pytest.raises(ValueError, match=r"must equal halted\.seq \+ 1"):
        reset_entry(halted, fresh2)


def test_advance_entry_cost_matches_budget_delta() -> None:
    """cost_paid must equal prev.budget − next.budget exactly (INV-FE2 audit)."""
    cfg = _cfg(initial_budget=10.0)
    s0 = initial_state(cfg)
    s1 = update(s0, 0.0, 3.0, config=cfg)
    entry = advance_entry(s0, s1)
    assert entry["cost_paid"] == s0.budget - s1.budget, (
        f"cost_paid ({entry['cost_paid']!r}) does not equal "
        f"budget delta ({s0.budget - s1.budget!r}); "
        f"prev.budget={s0.budget!r}, next.budget={s1.budget!r}."
    )


def test_audit_entry_dict_is_complete() -> None:
    """Every documented field is populated; no field is silently None."""
    cfg = _cfg()
    s0 = initial_state(cfg)
    s1 = update(s0, 0.5, 0.5, config=cfg)
    entry = advance_entry(s0, s1)
    expected_keys = {
        "schema",
        "transition",
        "seq",
        "prev_hash",
        "next_hash",
        "weight",
        "budget",
        "invariant_floor",
        "phase",
        "halt_reason",
        "cost_paid",
    }
    assert set(entry.keys()) == expected_keys, (
        f"audit entry shape drift: keys={set(entry.keys())!r} "
        f"expected={expected_keys!r}; "
        "schema bump required for additive changes are caught here."
    )


def test_lineage_chain_through_audit_entries() -> None:
    """A sequence of audit entries must form an unbroken chain on prev→next hashes."""
    cfg = _cfg(initial_budget=20.0)
    state: EpistemicState = initial_state(cfg)
    entries: list[EpistemicAuditEntry] = []
    for s, f in zip(
        [0.0, 1.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 1.0, 0.0],
        strict=True,
    ):
        prev = state
        state = update(state, s, f, config=cfg)
        entries.append(advance_entry(prev, state))
    for i in range(1, len(entries)):
        assert entries[i]["prev_hash"] == entries[i - 1]["next_hash"], (
            f"chain break at audit entry index {i}: "
            f"prev_hash={entries[i]['prev_hash']!r} "
            f"!= entries[i-1].next_hash={entries[i - 1]['next_hash']!r}; "
            "audit lineage integrity broken."
        )
