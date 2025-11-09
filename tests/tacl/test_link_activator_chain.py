# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for link_activator activation chain and protocol fallback behavior."""
from __future__ import annotations

import pytest

from tradepulse.runtime.link_activator import LinkActivator, ProtocolType


class TestLinkActivatorChain:
    """Test suite for link activation chain and fallback behavior."""

    def test_metallic_bond_protocol_chain(self) -> None:
        """Verify metallic bond uses correct protocol fallback chain."""
        activator = LinkActivator(enable_rdma=True, enable_crdt=True)
        result = activator.apply("metallic", "src_node", "dst_node")

        assert result.success is True
        # Metallic should prefer high-performance protocols
        assert result.protocol_used in [
            ProtocolType.RDMA,
            ProtocolType.SHARED_MEMORY,
        ]
        assert result.cost > 0
        assert result.latency_estimate_us > 0

    def test_ionic_bond_protocol_chain(self) -> None:
        """Verify ionic bond uses correct protocol fallback chain."""
        activator = LinkActivator(enable_rdma=True, enable_crdt=True)
        result = activator.apply("ionic", "src_node", "dst_node")

        assert result.success is True
        # Ionic should use eventually consistent protocols
        assert result.protocol_used in [ProtocolType.CRDT, ProtocolType.GOSSIP]

    def test_covalent_bond_protocol_chain(self) -> None:
        """Verify covalent bond uses correct protocol fallback chain."""
        activator = LinkActivator(enable_rdma=False, enable_crdt=False)
        result = activator.apply("covalent", "src_node", "dst_node")

        assert result.success is True
        # Covalent should fall back to gRPC when RDMA disabled
        assert result.protocol_used == ProtocolType.GRPC

    def test_hydrogen_bond_protocol_chain(self) -> None:
        """Verify hydrogen bond uses appropriate protocols."""
        activator = LinkActivator()
        result = activator.apply("hydrogen", "src_node", "dst_node")

        assert result.success is True
        # Hydrogen bonds are weaker, should use lighter protocols
        assert result.protocol_used in [
            ProtocolType.LOCAL_QUEUE,
            ProtocolType.LOCAL_LEDGER,
        ]

    def test_vdw_bond_protocol_chain(self) -> None:
        """Verify van der Waals bond uses appropriate protocols."""
        activator = LinkActivator()
        result = activator.apply("vdw", "src_node", "dst_node")

        assert result.success is True
        # VdW are weakest, should use local protocols
        assert result.protocol_used in [
            ProtocolType.LOCAL_QUEUE,
            ProtocolType.LOCAL_LEDGER,
        ]

    def test_unknown_bond_type_error(self) -> None:
        """Verify that unknown bond types are handled gracefully."""
        activator = LinkActivator()
        result = activator.apply("unknown_bond", "src", "dst")

        assert result.success is False
        assert result.protocol_used is None
        assert "unknown bond type" in result.error.lower()

    def test_activation_history_tracking(self) -> None:
        """Verify that activation history is properly tracked."""
        activator = LinkActivator()

        # Perform several activations
        activator.apply("metallic", "a", "b")
        activator.apply("ionic", "b", "c")
        activator.apply("covalent", "c", "d")

        history = activator.get_activation_history()
        assert len(history) == 3
        assert history[0]["bond_type"] == "metallic"
        assert history[1]["bond_type"] == "ionic"
        assert history[2]["bond_type"] == "covalent"

    def test_total_cost_accumulation(self) -> None:
        """Verify that total cost is properly accumulated."""
        activator = LinkActivator()

        initial_cost = activator.get_total_cost()
        assert initial_cost == 0.0

        # Perform activations
        activator.apply("metallic", "a", "b")
        activator.apply("ionic", "b", "c")

        total_cost = activator.get_total_cost()
        assert total_cost > 0.0
        assert total_cost == sum(
            entry["cost"]
            for entry in activator.get_activation_history()
            if entry["success"]
        )

    def test_rdma_disabled_fallback(self) -> None:
        """Verify fallback behavior when RDMA is disabled."""
        activator = LinkActivator(enable_rdma=False)
        result = activator.apply("metallic", "a", "b")

        assert result.success is True
        # Should fall back to shared memory
        assert result.protocol_used == ProtocolType.SHARED_MEMORY

    def test_crdt_disabled_fallback(self) -> None:
        """Verify fallback behavior when CRDT is disabled."""
        activator = LinkActivator(enable_crdt=False)
        result = activator.apply("ionic", "a", "b")

        assert result.success is True
        # Should fall back to gossip
        assert result.protocol_used == ProtocolType.GOSSIP

    def test_metadata_preservation(self) -> None:
        """Verify that metadata is properly preserved in activation history."""
        activator = LinkActivator()
        metadata = {"experiment_id": "exp_123", "iteration": 5}

        result = activator.apply("metallic", "a", "b", metadata=metadata)

        history = activator.get_activation_history()
        assert len(history) == 1
        assert history[0]["metadata"] == metadata

    @pytest.mark.integration
    def test_mfd_guard_integration(self) -> None:
        """Verify that MFD guard properly blocks activations when energy budget exceeded."""
        # Create activator with very low energy budget
        activator = LinkActivator(F_baseline=0.0001, epsilon=0.00001)

        # First few activations should succeed
        results = []
        for i in range(10):
            result = activator.apply("metallic", f"node_{i}", f"node_{i+1}")
            results.append(result)

        # Should have some successful activations
        successful = [r for r in results if r.success]
        assert len(successful) > 0

        # Should also have some blocked by MFD guard
        blocked = [r for r in results if not r.success and "MFD" in r.error]
        assert len(blocked) > 0

    def test_protocol_cost_consistency(self) -> None:
        """Verify that protocol costs are consistent with estimates."""
        activator = LinkActivator()

        for bond_type in ["metallic", "ionic", "covalent", "hydrogen", "vdw"]:
            result = activator.apply(bond_type, "a", "b")
            if result.success and result.protocol_used:
                # Verify cost matches protocol cost table
                expected_cost = activator.PROTOCOL_COSTS[result.protocol_used]
                assert result.cost == expected_cost

    def test_latency_estimate_consistency(self) -> None:
        """Verify that latency estimates are consistent."""
        activator = LinkActivator()

        for bond_type in ["metallic", "ionic", "covalent", "hydrogen", "vdw"]:
            result = activator.apply(bond_type, "a", "b")
            if result.success and result.protocol_used:
                # Verify latency matches estimate table
                expected_latency = activator.LATENCY_ESTIMATES_US[result.protocol_used]
                assert result.latency_estimate_us == expected_latency


@pytest.mark.L5
class TestLinkActivatorResilience:
    """Resilience and stress tests for link activator."""

    def test_rapid_activation_chain(self) -> None:
        """Test rapid succession of activations."""
        activator = LinkActivator()

        # Perform many rapid activations
        for i in range(100):
            result = activator.apply("metallic", f"node_{i}", f"node_{i+1}")
            assert result.success is True or "MFD" in result.error

        # Verify history is complete
        history = activator.get_activation_history()
        assert len(history) == 100

    def test_mixed_bond_types_chain(self) -> None:
        """Test chain of mixed bond types."""
        activator = LinkActivator()
        bond_types = ["metallic", "ionic", "covalent", "hydrogen", "vdw"]

        for i, bond_type in enumerate(bond_types * 10):
            result = activator.apply(bond_type, f"n{i}", f"n{i+1}")
            # Should either succeed or be blocked by MFD
            assert result.success or "MFD" in result.error or "unknown" in result.error.lower()

        history = activator.get_activation_history()
        assert len(history) == 50
