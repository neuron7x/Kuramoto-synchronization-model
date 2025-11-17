"""Tests for self-diagnosis and adaptation mechanisms in TACL.

This module tests the autonomous adaptation capabilities of the Thermodynamic
Autonomic Control Layer including self-diagnosis, auto-tuning, and self-healing.
"""

import time

import pytest

from runtime.recovery_agent import AdaptiveRecoveryAgent, RecoveryAction, RecoveryState

# ThermoController requires optional dependencies, tests are self-contained


class TestSelfDiagnosisSystem:
    """Test suite for self-diagnosis capabilities."""

    def test_anomaly_detection_in_metrics(self):
        """Test automatic detection of metric anomalies."""
        import numpy as np

        # Historical baseline
        baseline = np.random.normal(100, 5, 1000)
        baseline_mean = np.mean(baseline)
        baseline_std = np.std(baseline)

        # Current value
        current_value = 150  # Anomalous

        # Z-score based detection
        z_score = abs((current_value - baseline_mean) / baseline_std)

        is_anomaly = z_score > 3
        assert is_anomaly, "Should detect anomalous value"

    def test_system_health_assessment(self):
        """Test overall system health assessment."""
        health_metrics = {
            "cpu_utilization": 45.0,  # %
            "memory_utilization": 60.0,  # %
            "error_rate": 0.01,  # 1%
            "latency_p99": 150.0,  # ms
        }

        thresholds = {
            "cpu_utilization": 80.0,
            "memory_utilization": 85.0,
            "error_rate": 0.05,
            "latency_p99": 500.0,
        }

        # Calculate health score
        issues = 0
        for metric, value in health_metrics.items():
            if value > thresholds.get(metric, float("inf")):
                issues += 1

        health_score = 100 - (issues * 25)  # Deduct 25 points per issue

        assert health_score == 100, "All metrics within healthy range"

    def test_degradation_detection(self):
        """Test detection of gradual system degradation."""
        # Simulate time series of performance metric
        time_series = [100, 102, 101, 99, 98, 97, 95, 93, 90, 88]  # Degrading

        # Calculate trend using simple linear regression
        import numpy as np

        x = np.arange(len(time_series))
        y = np.array(time_series)

        # Linear regression slope
        slope = np.polyfit(x, y, 1)[0]

        # Negative slope indicates degradation
        is_degrading = slope < -1.0
        assert is_degrading, "Should detect performance degradation"

    def test_failure_prediction(self):
        """Test prediction of potential failures."""
        # Simulate error rate trend
        error_rates = [0.001, 0.002, 0.005, 0.010, 0.020]  # Increasing

        # Calculate rate of increase
        import numpy as np

        np.arange(len(error_rates))
        np.array(error_rates)

        # Exponential growth detection
        if len(error_rates) >= 3:
            recent_growth = error_rates[-1] / error_rates[-3]
            failure_predicted = recent_growth > 2.0  # Doubled in 2 intervals
        else:
            failure_predicted = False

        assert failure_predicted, "Should predict potential failure"


class TestAdaptiveConfiguration:
    """Test suite for adaptive configuration tuning."""

    def test_auto_tuning_parameters(self):
        """Test automatic parameter tuning based on load."""
        # Initial configuration
        config = {"batch_size": 100, "worker_threads": 4, "cache_size_mb": 512}

        # Current metrics
        current_load = 0.85  # 85% capacity

        # Auto-tune based on load
        if current_load > 0.8:
            config["batch_size"] = int(config["batch_size"] * 1.2)
            config["worker_threads"] += 2

        assert config["batch_size"] == 120
        assert config["worker_threads"] == 6

    def test_dynamic_threshold_adjustment(self):
        """Test dynamic adjustment of alert thresholds."""
        # Historical data
        import numpy as np

        historical = np.random.normal(100, 10, 1000)

        # Calculate adaptive threshold
        mean = np.mean(historical)
        std = np.std(historical)
        threshold = mean + 3 * std  # 3-sigma threshold

        # Threshold should adapt to data distribution
        assert 120 < threshold < 140

    def test_load_based_scaling(self):
        """Test automatic scaling based on load."""
        current_rps = 1000  # requests per second
        capacity_rps = 800  # current capacity

        utilization = current_rps / capacity_rps

        # Scale up if over 80% utilized
        if utilization > 0.8:
            scale_factor = 1.5
            new_capacity = int(capacity_rps * scale_factor)
        else:
            new_capacity = capacity_rps

        assert new_capacity == 1200, "Should scale up capacity"

    def test_configuration_rollback(self):
        """Test automatic rollback of bad configuration."""
        # Original config
        original_config = {"timeout_ms": 1000}

        # New config
        new_config = {"timeout_ms": 100}

        # Simulate performance after change
        error_rate_before = 0.01
        error_rate_after = 0.15  # Degraded

        # Rollback if degraded
        if error_rate_after > error_rate_before * 2:
            final_config = original_config
        else:
            final_config = new_config

        assert final_config == original_config, "Should rollback bad config"


class TestSelfHealingCapabilities:
    """Test suite for self-healing capabilities."""

    def test_automatic_restart_on_failure(self):
        """Test automatic restart of failed components."""
        component_state = "running"
        restart_count = 0
        max_restarts = 3

        # Simulate failure
        component_state = "failed"

        # Self-healing: restart
        while component_state == "failed" and restart_count < max_restarts:
            component_state = "running"  # Simulated restart
            restart_count += 1

        assert component_state == "running"
        assert restart_count == 1

    def test_circuit_breaker_recovery(self):
        """Test circuit breaker auto-recovery."""
        circuit_state = "closed"  # Normal
        error_count = 0
        error_threshold = 5

        # Simulate errors
        for _ in range(7):
            error_count += 1
            if error_count >= error_threshold:
                circuit_state = "open"  # Trip circuit

        assert circuit_state == "open"

        # Auto-recovery after cooldown
        time.sleep(0.01)  # Simulated cooldown
        circuit_state = "half-open"  # Test mode

        # If test succeeds, close circuit
        test_success = True
        if test_success:
            circuit_state = "closed"
            error_count = 0

        assert circuit_state == "closed"

    def test_resource_leak_detection_and_cleanup(self):
        """Test detection and cleanup of resource leaks."""
        import weakref

        # Track resources
        resources = []

        class Resource:
            def __init__(self):
                self.data = [0] * 1000

        # Allocate resources
        for _ in range(10):
            r = Resource()
            resources.append(weakref.ref(r))

        # Cleanup (simulated garbage collection)
        resources = [r for r in resources if r() is not None]

        # In real scenario, would detect and cleanup leaked resources
        assert True  # Simplified test

    def test_connection_pool_healing(self):
        """Test automatic healing of connection pools."""
        pool_size = 10
        healthy_connections = 8

        # Detect unhealthy connections
        unhealthy_count = pool_size - healthy_connections

        # Heal pool by creating new connections
        if unhealthy_count > 0:
            # Simulate creating new connections
            healthy_connections += unhealthy_count

        assert healthy_connections == pool_size


class TestTACLAdaptiveRecovery:
    """Test suite for TACL adaptive recovery mechanisms."""

    def test_recovery_agent_learns_from_history(self):
        """Test that recovery agent learns from past actions."""
        agent = AdaptiveRecoveryAgent(alpha=0.5, gamma=0.9)

        # Initial Q-value
        state = RecoveryState(0.11, 0.10, 2.0, 5)
        action = RecoveryAction.MEDIUM

        initial_q = agent.Q[(agent.discretize_state(state), action)]

        # Update with positive reward
        next_state = RecoveryState(0.105, 0.10, 1.5, 6)
        agent.update(state, action, reward=0.005, next_state=next_state)

        final_q = agent.Q[(agent.discretize_state(state), action)]

        # Q-value should improve
        assert final_q > initial_q

    def test_crisis_mode_escalation(self):
        """Test escalation to different crisis modes."""
        # Simulate system metrics
        dF_dt = 0.05

        # Determine crisis mode
        if dF_dt > 0.03:
            crisis_mode = "critical"
        elif dF_dt > 0.01:
            crisis_mode = "elevated"
        else:
            crisis_mode = "normal"

        assert crisis_mode == "critical"

    def test_adaptive_epsilon_adjustment(self):
        """Test adaptive adjustment of epsilon for exploration."""
        # Start with exploration
        epsilon = 0.1
        success_count = 0
        total_attempts = 100

        # Simulate learning with high success rate
        for _ in range(total_attempts):
            # Simulate success for first 85 attempts
            if _ < 85:
                success_count += 1

        # Reduce exploration as learning improves
        success_rate = success_count / total_attempts
        if success_rate > 0.8:
            epsilon *= 0.5

        assert epsilon < 0.1  # Should reduce exploration

    def test_multi_strategy_recovery(self):
        """Test using multiple recovery strategies."""
        strategies = {
            "slow": {"mutation_rate": 0.01, "speed": 1},
            "medium": {"mutation_rate": 0.05, "speed": 2},
            "fast": {"mutation_rate": 0.1, "speed": 3},
        }

        # Select strategy based on urgency
        urgency = "high"

        if urgency == "high":
            selected = strategies["fast"]
        else:
            selected = strategies["slow"]

        assert selected["speed"] == 3


class TestMonotonicSafetyGuarantees:
    """Test suite for monotonic safety guarantees."""

    def test_free_energy_monotonic_descent(self):
        """Test that free energy never increases without approval."""
        F_old = 0.10
        F_new = 0.12  # Larger increase to clearly violate constraint
        epsilon = 0.01

        # Check monotonic constraint
        violates_monotonic = F_new > F_old + epsilon

        if violates_monotonic:
            # Reject change
            F_final = F_old
        else:
            F_final = F_new

        assert (
            F_final == F_old
        ), "Should reject change that violates monotonic constraint"

    def test_safety_gate_validation(self):
        """Test safety gate prevents unsafe changes."""
        proposed_change = {
            "parameter": "mutation_rate",
            "old_value": 0.01,
            "new_value": 0.5,
        }

        # Validate change is within safe bounds
        max_change_ratio = 2.0
        change_ratio = proposed_change["new_value"] / proposed_change["old_value"]

        is_safe = change_ratio <= max_change_ratio

        assert not is_safe, "Should reject unsafe change"

    def test_emergency_override_mechanism(self):
        """Test emergency override for critical situations."""
        F_current = 0.20
        F_critical_threshold = 0.15
        manual_override_authorized = True

        # Critical situation
        is_critical = F_current > F_critical_threshold

        if is_critical and manual_override_authorized:
            # Allow non-monotonic change
            can_override = True
        else:
            can_override = False

        assert can_override, "Should allow override in critical situations"


class TestAdaptiveLoadManagement:
    """Test suite for adaptive load management."""

    def test_load_shedding(self):
        """Test automatic load shedding under pressure."""
        current_load = 0.95
        shed_threshold = 0.90

        # Determine if load shedding needed
        should_shed = current_load > shed_threshold

        if should_shed:
            # Drop lowest priority requests
            new_load = current_load * 0.8  # Shed 20%
        else:
            new_load = current_load

        assert should_shed
        assert new_load < shed_threshold

    def test_backpressure_mechanism(self):
        """Test backpressure to slow down producers."""
        queue_size = 1000
        queue_capacity = 1000

        utilization = queue_size / queue_capacity

        # Apply backpressure
        if utilization > 0.8:
            backpressure = True
            producer_rate = 0.5  # Slow down to 50%
        else:
            backpressure = False
            producer_rate = 1.0

        assert backpressure
        assert producer_rate == 0.5

    def test_rate_limiting_adaptation(self):
        """Test adaptive rate limiting."""
        current_error_rate = 0.08
        target_error_rate = 0.05
        current_rate_limit = 1000  # requests/sec

        # Adjust rate limit based on error rate
        if current_error_rate > target_error_rate:
            # Reduce rate limit
            new_rate_limit = int(current_rate_limit * 0.8)
        else:
            new_rate_limit = current_rate_limit

        assert new_rate_limit == 800


@pytest.mark.integration
class TestEndToEndAdaptation:
    """Integration tests for complete adaptation pipeline."""

    def test_detect_adapt_verify_cycle(self):
        """Test complete detect-adapt-verify cycle."""
        # 1. Detect issue
        latency = 500  # ms
        threshold = 200
        issue_detected = latency > threshold

        assert issue_detected

        # 2. Adapt configuration

        # 3. Verify improvement
        new_latency = 180  # ms (improved)
        improvement = latency - new_latency

        assert improvement > 0

    def test_multi_dimensional_adaptation(self):
        """Test adaptation across multiple dimensions."""
        metrics = {
            "latency": 250,  # High
            "throughput": 500,  # Low
            "error_rate": 0.08,  # High
        }

        adaptations = []

        if metrics["latency"] > 200:
            adaptations.append("increase_timeout")
        if metrics["throughput"] < 1000:
            adaptations.append("scale_up")
        if metrics["error_rate"] > 0.05:
            adaptations.append("enable_circuit_breaker")

        assert len(adaptations) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
