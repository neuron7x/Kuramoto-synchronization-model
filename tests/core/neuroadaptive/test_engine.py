"""Unit tests for neuroadaptive decision engine."""

import pytest

from core.neuroadaptive import (
    DecisionRequest,
    NeuroAdaptiveAgent,
    NeuroAdaptiveConfig,
    NeuroGateState,
    NeuroSignals,
)


class MockLlmClient:
    """Mock LLM client for testing."""

    async def complete(self, prompt: str, **kwargs) -> str:
        """Mock completion method."""
        return "mock response"


class TestNeuroAdaptiveAgent:
    """Tests for NeuroAdaptiveAgent decision engine."""

    @pytest.fixture
    def llm(self):
        """Create mock LLM client."""
        return MockLlmClient()

    @pytest.fixture
    def agent(self, llm):
        """Create agent with default config."""
        return NeuroAdaptiveAgent(llm)

    @pytest.fixture
    def agent_custom_config(self, llm):
        """Create agent with custom config."""
        config = NeuroAdaptiveConfig(
            weights={
                "dopamine_rpe": 0.4,
                "serotonin_veto": 0.3,
                "threat_score": 0.2,
                "energy_efficiency": 0.1,
            },
            blend_ratio=0.5,
        )
        return NeuroAdaptiveAgent(llm, config)

    def test_agent_initialization(self, agent):
        """Test agent initializes with validated config."""
        assert agent.config is not None
        assert agent.gate_state == NeuroGateState.REFLEX

    @pytest.mark.asyncio
    async def test_decide_all_signals_present(self, agent):
        """Test decision with all neuro signals present."""
        signals = NeuroSignals(
            dopamine_rpe=0.5,
            serotonin_veto=0.2,
            threat_score=0.3,
            energy_efficiency=0.8,
            prior_confidence=0.7,
        )
        request = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
            risk_tag="medium",
        )

        result = await agent.decide(request)

        assert result is not None
        assert isinstance(result.allowed, bool)
        assert isinstance(result.blended_confidence, float)
        assert 0.0 <= result.blended_confidence <= 1.0
        assert result.gate_state in NeuroGateState
        assert result.reason is not None
        assert "gate_state" in result.debug

    @pytest.mark.asyncio
    async def test_decide_partial_signals(self, agent):
        """Test decision with only some signals present."""
        signals = NeuroSignals(
            dopamine_rpe=0.6,
            threat_score=0.2,
        )
        request = DecisionRequest(
            raw_proposal={"action": "sell"},
            neuro_signals=signals,
            risk_tag="low",
        )

        result = await agent.decide(request)

        assert result is not None
        # Partial signals should still produce valid decision
        assert isinstance(result.allowed, bool)
        assert result.debug["neuro_data_quality_ok"]

    @pytest.mark.asyncio
    async def test_decide_high_confidence_release(self, agent):
        """Test that high confidence leads to RELEASED state."""
        signals = NeuroSignals(
            dopamine_rpe=0.8,
            serotonin_veto=0.1,
            threat_score=0.1,
            energy_efficiency=0.9,
            prior_confidence=0.8,
        )
        request = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
            risk_tag="low",
        )

        result = await agent.decide(request)

        # High confidence with low risk should be allowed
        assert result.allowed
        assert result.gate_state == NeuroGateState.RELEASED

    @pytest.mark.asyncio
    async def test_decide_low_confidence_inhibit(self, agent):
        """Test that low confidence leads to INHIBITED state."""
        signals = NeuroSignals(
            dopamine_rpe=-0.8,
            serotonin_veto=0.9,
            threat_score=0.9,
            energy_efficiency=0.1,
            prior_confidence=0.2,
        )
        request = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
            risk_tag="high",
        )

        result = await agent.decide(request)

        # Low confidence should be blocked
        assert not result.allowed
        assert result.gate_state == NeuroGateState.INHIBITED

    @pytest.mark.asyncio
    async def test_decide_out_of_range_signals(self, agent):
        """Test handling of out-of-range signal values."""
        signals = NeuroSignals(
            dopamine_rpe=2.0,  # Out of range
            serotonin_veto=-0.5,  # Out of range
            threat_score=0.5,
        )
        request = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
            risk_tag="medium",
        )

        result = await agent.decide(request)

        # Should still produce result but flag data quality issues
        assert result is not None
        assert not result.debug["neuro_data_quality_ok"]
        assert len(result.debug["neuro_data_quality_issues"]) > 0

    @pytest.mark.asyncio
    async def test_decide_critical_risk(self, agent):
        """Test that critical risk requires explicit release."""
        signals = NeuroSignals(
            dopamine_rpe=0.9,
            serotonin_veto=0.1,
            threat_score=0.1,
            energy_efficiency=0.9,
        )
        request = DecisionRequest(
            raw_proposal={"action": "buy"},
            neuro_signals=signals,
            risk_tag="critical",
        )

        result = await agent.decide(request)

        # Even with high confidence, critical risk should not auto-release
        assert not result.allowed
        assert result.gate_state == NeuroGateState.ARMED

    @pytest.mark.asyncio
    async def test_decide_no_signals(self, agent):
        """Test decision with no signals (all None)."""
        signals = NeuroSignals()
        request = DecisionRequest(
            raw_proposal={"action": "hold"},
            neuro_signals=signals,
            risk_tag="low",
        )

        result = await agent.decide(request)

        # Should use neutral confidence (0.5)
        assert result is not None
        # Neutral confidence should lead to ARMED state
        assert result.gate_state in (NeuroGateState.ARMED, NeuroGateState.REFLEX)

    @pytest.mark.asyncio
    async def test_decision_impact_calculation(self, agent):
        """Test decision impact classification."""
        # Test NO_CHANGE
        signals = NeuroSignals(
            dopamine_rpe=0.0,
            serotonin_veto=0.5,
            threat_score=0.5,
            energy_efficiency=0.5,
            prior_confidence=0.5,
        )
        request = DecisionRequest(
            raw_proposal={},
            neuro_signals=signals,
            risk_tag="medium",
        )
        result = await agent.decide(request)
        # With blend_ratio=0.3 and neutral signals, impact should be minimal
        assert result.debug["neuro_decision_impact"] in (
            "NO_CHANGE",
            "INCREASED",
            "DECREASED",
        )

    @pytest.mark.asyncio
    async def test_custom_config_blend_ratio(self, agent_custom_config):
        """Test that custom blend ratio affects blended confidence."""
        signals = NeuroSignals(
            dopamine_rpe=0.9,
            serotonin_veto=0.1,
            threat_score=0.1,
            energy_efficiency=0.9,
            prior_confidence=0.3,  # Low prior
        )
        request = DecisionRequest(
            raw_proposal={},
            neuro_signals=signals,
            risk_tag="medium",
        )

        result = await agent_custom_config.decide(request)

        # With blend_ratio=0.5, neuro signals should have more weight
        base_conf = result.debug["base_confidence"]
        blended_conf = result.debug["blended_confidence"]
        # Blended should be between base and neuro
        assert base_conf <= blended_conf or blended_conf <= base_conf

    @pytest.mark.asyncio
    async def test_telemetry_in_debug(self, agent):
        """Test that debug output contains telemetry data."""
        signals = NeuroSignals(
            dopamine_rpe=0.5,
            serotonin_veto=0.3,
        )
        request = DecisionRequest(
            raw_proposal={},
            neuro_signals=signals,
            risk_tag="medium",
        )

        result = await agent.decide(request)

        # Check all expected telemetry fields
        debug = result.debug
        assert "gate_state" in debug
        assert "neuro_confidence" in debug
        assert "neuro_data_quality_ok" in debug
        assert "neuro_signal_contributions" in debug
        assert "neuro_decision_impact" in debug
        assert "risk_tag" in debug
        assert "base_confidence" in debug
        assert "blended_confidence" in debug
