# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the link activator."""

from runtime.link_activator import LinkActivator, ProtocolType


def test_metallic_bond_prefers_crdt() -> None:
    activator = LinkActivator(enable_rdma=True, enable_crdt=True)
    result = activator.apply("metallic", "A", "B")
    assert result.success
    assert result.protocol_used in {ProtocolType.CRDT, ProtocolType.GOSSIP}


def test_ionic_bond_fallbacks_to_grpc_when_rdma_disabled() -> None:
    activator = LinkActivator(enable_rdma=False, enable_crdt=True)
    result = activator.apply("ionic", "Trader", "Risk")
    assert result.success
    assert result.protocol_used == ProtocolType.GRPC


def test_activation_history_tracks_attempts() -> None:
    activator = LinkActivator()
    activator.apply("metallic", "A", "B")
    activator.apply("vdw", "C", "D")
    history = activator.get_activation_history()
    assert len(history) == 2
    assert history[0]["bond_type"] == "metallic"
    assert history[1]["bond_type"] == "vdw"


def test_total_cost_accumulates_successes() -> None:
    activator = LinkActivator()
    activator.apply("metallic", "A", "B")
    activator.apply("ionic", "C", "D")
    assert activator.get_total_cost() > 0


def test_activation_metadata_is_recorded_in_history() -> None:
    """`metadata or {}` in the history record must STORE what the caller passed.

    Under `Or -> And`, `metadata or {}` becomes `metadata and {}` -> `{}` whenever metadata is
    truthy, silently dropping the diagnostic context from every activation record that carried
    any. The activation history is the audit trail for link setup; an audit trail that discards
    the diagnostics on exactly the calls that supplied them is worse than none.
    """
    activator = LinkActivator(enable_rdma=True, enable_crdt=True)
    activator.apply("metallic", "A", "B", metadata={"trace_id": "abc-123", "attempt": 2})

    history = activator.get_activation_history()
    assert history[-1]["metadata"] == {"trace_id": "abc-123", "attempt": 2}


def test_activation_metadata_defaults_to_empty_dict() -> None:
    """Matched control: the fall-through is correct when the caller passes nothing."""
    activator = LinkActivator(enable_rdma=True, enable_crdt=True)
    activator.apply("metallic", "A", "B")

    assert activator.get_activation_history()[-1]["metadata"] == {}
