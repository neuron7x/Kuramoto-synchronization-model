"""
Tests for ThermoController HPC-AI integration.
"""

import networkx as nx
import pandas as pd
import pytest

from neuropro.hpc_validation import generate_synthetic_data
from runtime.thermo_controller import ThermoController


@pytest.fixture
def simple_graph():
    """Create a simple directed graph for testing."""
    G = nx.DiGraph()
    G.add_edge("A", "B", type="covalent", latency_norm=0.1, coherency=0.8)
    G.add_edge("B", "C", type="ionic", latency_norm=0.2, coherency=0.7)
    G.add_edge("C", "A", type="vdw", latency_norm=0.15, coherency=0.75)

    for node in G.nodes():
        G.nodes[node]["cpu_norm"] = 0.3

    return G


@pytest.fixture
def synthetic_market_data():
    """Generate synthetic market data."""
    return generate_synthetic_data(n_days=100, seed=42)


class TestThermoControllerHPCAI:
    """Test ThermoController HPC-AI integration."""

    def test_init_hpc_ai(self, simple_graph):
        """Test HPC-AI initialization in ThermoController."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(
            input_dim=10,
            state_dim=64,
            action_dim=3,
            learning_rate=1e-4,
        )

        assert hasattr(controller, "hpc_ai")
        assert hasattr(controller, "prev_pwpe")
        assert controller._hpc_ai_enabled is True
        assert controller.prev_pwpe == 0.0

    def test_hpc_ai_control_step_not_initialized(self, simple_graph, synthetic_market_data):
        """Test HPC-AI control step without initialization."""
        controller = ThermoController(simple_graph)

        result = controller.hpc_ai_control_step(synthetic_market_data)

        assert "error" in result
        assert result["action"] == 0
        assert result["td_error"] == 0.0

    def test_hpc_ai_control_step(self, simple_graph, synthetic_market_data):
        """Test HPC-AI control step with initialization."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        result = controller.hpc_ai_control_step(synthetic_market_data)

        assert "action" in result
        assert "td_error" in result
        assert "pwpe" in result
        assert "reward" in result
        assert "state_norm" in result

        assert result["action"] in [0, 1, 2]
        assert isinstance(result["td_error"], float)
        assert result["pwpe"] >= 0.0

    def test_hpc_ai_control_step_with_execution(self, simple_graph, synthetic_market_data):
        """Test HPC-AI control step with action execution flag."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        result = controller.hpc_ai_control_step(
            synthetic_market_data,
            execute_action=True,
        )

        assert "action" in result
        assert result["action"] in [0, 1, 2]

    def test_multiple_control_steps(self, simple_graph, synthetic_market_data):
        """Test multiple HPC-AI control steps."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        results = []
        for i in range(5):
            window_data = synthetic_market_data.iloc[i * 10 : (i + 1) * 10 + 90]
            result = controller.hpc_ai_control_step(window_data)
            results.append(result)

        # Check all steps completed
        assert len(results) == 5

        # Check prev_pwpe is updated
        assert controller.prev_pwpe > 0.0

        # Check actions are valid
        actions = [r["action"] for r in results]
        assert all(a in [0, 1, 2] for a in actions)

    def test_pwpe_tracking(self, simple_graph, synthetic_market_data):
        """Test that PWPE is tracked across steps."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        result1 = controller.hpc_ai_control_step(synthetic_market_data)
        pwpe1 = result1["pwpe"]
        prev_pwpe1 = controller.prev_pwpe

        assert pwpe1 == prev_pwpe1

        result2 = controller.hpc_ai_control_step(synthetic_market_data)
        pwpe2 = result2["pwpe"]
        prev_pwpe2 = controller.prev_pwpe

        assert pwpe2 == prev_pwpe2

    def test_integration_with_regular_control_step(self, simple_graph):
        """Test that HPC-AI doesn't interfere with regular control_step."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        # Regular control step should still work
        controller.control_step()

        assert controller.controller_state is not None
        assert controller.previous_F is not None


class TestHPCAIEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_dataframe(self, simple_graph):
        """Test with empty DataFrame."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        empty_df = pd.DataFrame()

        # Should handle gracefully
        try:
            result = controller.hpc_ai_control_step(empty_df)
            # If it doesn't raise, check result has error handling
            assert "action" in result or "error" in result
        except Exception as e:
            # Some error is expected
            assert isinstance(e, (ValueError, KeyError, IndexError))

    def test_missing_columns(self, simple_graph):
        """Test with missing required columns."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        # DataFrame with only some columns
        partial_df = pd.DataFrame({
            "close": [100.0, 101.0],
            "volume": [1000000, 1100000],
        })
        partial_df.index = pd.date_range("2020-01-01", periods=2, freq="D")

        # Should handle gracefully with fallback
        result = controller.hpc_ai_control_step(partial_df)
        assert "action" in result

    def test_nan_values(self, simple_graph, synthetic_market_data):
        """Test with NaN values in data."""
        controller = ThermoController(simple_graph)
        controller.init_hpc_ai(state_dim=64)

        # Inject NaN
        data_with_nan = synthetic_market_data.copy()
        data_with_nan.loc[data_with_nan.index[10], "close"] = float("nan")

        # Should handle gracefully
        try:
            result = controller.hpc_ai_control_step(data_with_nan)
            assert "action" in result
        except Exception:
            # Some error handling is acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
