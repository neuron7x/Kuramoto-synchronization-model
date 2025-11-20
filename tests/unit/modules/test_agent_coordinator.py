"""
Tests for Agent Coordinator Module
"""

import pytest

from modules.agent_coordinator import (
    AgentCoordinator,
    AgentMetadata,
    AgentStatus,
    AgentType,
    Priority,
)


class MockAgentHandler:
    """Mock agent handler for testing"""

    def __init__(self, name):
        self.name = name
        self.call_count = 0

    def process(self, task):
        self.call_count += 1
        return {"status": "success", "handler": self.name}


class TestAgentCoordinator:
    """Test suite for AgentCoordinator"""

    def test_initialization(self):
        """Test coordinator initialization"""
        coordinator = AgentCoordinator(max_concurrent_tasks=10)

        assert coordinator.max_concurrent_tasks == 10
        assert len(coordinator._agents) == 0
        assert len(coordinator._task_queue) == 0

    def test_register_agent(self):
        """Test agent registration"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        metadata = coordinator.register_agent(
            agent_id="agent_1",
            agent_type=AgentType.TRADING,
            name="Test Agent",
            description="Test trading agent",
            handler=handler,
            capabilities={"trade", "analyze"},
            priority=Priority.HIGH,
        )

        assert isinstance(metadata, AgentMetadata)
        assert metadata.agent_id == "agent_1"
        assert metadata.agent_type == AgentType.TRADING
        assert metadata.priority == Priority.HIGH
        assert "trade" in metadata.capabilities

    def test_register_duplicate_agent(self):
        """Test duplicate agent registration fails"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )

        with pytest.raises(ValueError):
            coordinator.register_agent(
                "agent_1", AgentType.TRADING, "Agent 1 Duplicate", "Desc", handler
            )

    def test_unregister_agent(self):
        """Test agent unregistration"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )
        assert "agent_1" in coordinator._agents

        coordinator.unregister_agent("agent_1")
        assert "agent_1" not in coordinator._agents

    def test_submit_task(self):
        """Test task submission"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )

        task_id = coordinator.submit_task(
            agent_id="agent_1",
            task_type="analyze",
            payload={"symbol": "BTCUSD"},
            priority=Priority.HIGH,
        )

        assert task_id.startswith("task_")
        assert len(coordinator._task_queue) == 1

    def test_submit_task_unregistered_agent(self):
        """Test task submission for unregistered agent fails"""
        coordinator = AgentCoordinator()

        with pytest.raises(ValueError):
            coordinator.submit_task(
                agent_id="nonexistent", task_type="test", payload={}
            )

    def test_task_priority_ordering(self):
        """Test tasks are ordered by priority"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )

        # Submit tasks with different priorities
        coordinator.submit_task("agent_1", "task_low", {}, Priority.LOW)
        coordinator.submit_task("agent_1", "task_high", {}, Priority.HIGH)
        coordinator.submit_task("agent_1", "task_normal", {}, Priority.NORMAL)

        # High priority should be first
        assert coordinator._task_queue[0].priority == Priority.HIGH

    def test_make_decision_resource_allocation(self):
        """Test resource allocation decision"""
        coordinator = AgentCoordinator()
        handler1 = MockAgentHandler("agent1")
        handler2 = MockAgentHandler("agent2")

        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Agent 1",
            "Desc",
            handler1,
            priority=Priority.HIGH,
        )
        coordinator.register_agent(
            "agent_2",
            AgentType.RISK_MANAGER,
            "Agent 2",
            "Desc",
            handler2,
            priority=Priority.NORMAL,
        )

        decision = coordinator.make_decision(
            decision_type="resource_allocation", context={}
        )

        assert decision.decision_type == "resource_allocation"
        assert len(decision.affected_agents) == 2

        # Check resources were allocated
        assert sum(coordinator._resource_allocation.values()) > 0

    def test_make_decision_emergency_stop(self):
        """Test emergency stop decision"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )

        decision = coordinator.make_decision(
            decision_type="emergency_stop", context={"reason": "critical_error"}
        )

        assert decision.priority == Priority.EMERGENCY
        assert decision.action == "stop_all"

        # All agents should be stopped
        assert coordinator._agents["agent_1"].status == AgentStatus.STOPPED

    def test_update_agent_status(self):
        """Test agent status update"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Description", handler
        )

        coordinator.update_agent_status("agent_1", AgentStatus.ACTIVE)
        assert coordinator._agents["agent_1"].status == AgentStatus.ACTIVE

    def test_get_agent_info(self):
        """Test getting agent information"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1",
            AgentType.TRADING,
            "Agent 1",
            "Description",
            handler,
            capabilities={"trade", "analyze"},
        )

        info = coordinator.get_agent_info("agent_1")

        assert info is not None
        assert info["agent_id"] == "agent_1"
        assert info["type"] == AgentType.TRADING.value
        assert "trade" in info["capabilities"]

    def test_get_agent_info_nonexistent(self):
        """Test getting info for nonexistent agent"""
        coordinator = AgentCoordinator()

        info = coordinator.get_agent_info("nonexistent")
        assert info is None

    def test_get_system_health(self):
        """Test system health calculation"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Desc", handler
        )
        coordinator.register_agent(
            "agent_2", AgentType.RISK_MANAGER, "Agent 2", "Desc", handler
        )

        health = coordinator.get_system_health()

        assert "health_score" in health
        assert "total_agents" in health
        assert health["total_agents"] == 2

    def test_get_coordination_summary(self):
        """Test coordination summary"""
        coordinator = AgentCoordinator()
        handler = MockAgentHandler("test_agent")

        coordinator.register_agent(
            "agent_1", AgentType.TRADING, "Agent 1", "Desc", handler
        )

        summary = coordinator.get_coordination_summary()

        assert "registered_agents" in summary
        assert "system_health" in summary
        assert summary["registered_agents"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
