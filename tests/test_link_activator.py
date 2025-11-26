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
