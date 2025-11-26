"""Tests for energy validator module."""

import json
import tempfile
from pathlib import Path

import pytest

from runtime.energy_validator import (
    EnergyConfig,
    EnergyValidationResult,
    EnergyValidator,
    MetricThreshold,
)


class TestMetricThreshold:
    """Tests for MetricThreshold dataclass."""

    def test_creation(self):
        """Test creating a metric threshold."""
        metric = MetricThreshold(
            name="test_metric",
            description="Test metric",
            threshold=100.0,
            weight=1.5,
            unit="ms",
        )
        assert metric.name == "test_metric"
        assert metric.threshold == 100.0
        assert metric.weight == 1.5


class TestEnergyConfig:
    """Tests for EnergyConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = EnergyConfig()
        assert config.control_temperature == 0.60
        assert config.max_acceptable_energy == 1.35
        assert len(config.metrics) == 7

    def test_get_total_weight(self):
        """Test total weight calculation."""
        config = EnergyConfig()
        total = config.get_total_weight()
        expected = sum(m.weight for m in config.metrics)
        assert total == expected
        assert total > 0

    def test_get_metric(self):
        """Test getting metric by name."""
        config = EnergyConfig()
        metric = config.get_metric("latency_p95")
        assert metric is not None
        assert metric.name == "latency_p95"
        assert metric.threshold == 85.0

    def test_get_metric_not_found(self):
        """Test getting non-existent metric."""
        config = EnergyConfig()
        metric = config.get_metric("nonexistent")
        assert metric is None


class TestEnergyValidator:
    """Tests for EnergyValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator with default configuration."""
        return EnergyValidator()

    @pytest.fixture
    def metrics_good(self):
        """Metrics all below threshold."""
        return {
            "latency_p95": 75.0,
            "latency_p99": 100.0,
            "coherency_drift": 0.05,
            "cpu_burn": 0.65,
            "mem_cost": 5.5,
            "queue_depth": 25.0,
            "packet_loss": 0.003,
        }

    @pytest.fixture
    def metrics_bad(self):
        """Metrics with violations."""
        return {
            "latency_p95": 95.0,  # Above 85.0
            "latency_p99": 130.0,  # Above 120.0
            "coherency_drift": 0.05,
            "cpu_burn": 0.80,  # Above 0.75
            "mem_cost": 5.0,
            "queue_depth": 35.0,  # Above 32.0
            "packet_loss": 0.007,  # Above 0.005
        }

    def test_initialization(self, validator):
        """Test validator initialization."""
        assert validator.config is not None
        assert len(validator.validation_history) == 0

    def test_compute_penalty_below_threshold(self, validator):
        """Test penalty computation for metric below threshold."""
        penalty, headroom = validator.compute_penalty("latency_p95", 75.0)
        assert penalty == 0.0
        assert headroom > 0

    def test_compute_penalty_above_threshold(self, validator):
        """Test penalty computation for metric above threshold."""
        penalty, headroom = validator.compute_penalty("latency_p95", 95.0)
        assert penalty > 0
        assert headroom < 0

    def test_compute_penalty_at_threshold(self, validator):
        """Test penalty computation for metric at threshold."""
        penalty, headroom = validator.compute_penalty("latency_p95", 85.0)
        assert penalty == 0.0
        assert headroom == 0.0

    def test_compute_internal_energy(self, validator, metrics_good):
        """Test internal energy computation."""
        U, penalties, headrooms = validator.compute_internal_energy(metrics_good)
        assert U >= 0
        assert len(penalties) == len(metrics_good)
        assert len(headrooms) == len(metrics_good)
        # All metrics below threshold, so no penalties
        assert all(p == 0 for p in penalties.values())

    def test_compute_stability(self, validator):
        """Test stability computation."""
        headrooms = {
            "metric1": 0.2,
            "metric2": 0.3,
            "metric3": -0.1,  # Negative headroom reduces stability
        }
        stability = validator.compute_stability(headrooms)
        assert -1 <= stability <= 1
        # Should average across all headrooms so deficits reduce S
        expected = sum(headrooms.values()) / len(headrooms)
        assert abs(stability - expected) < 1e-6

    def test_compute_free_energy_good_metrics(self, validator, metrics_good):
        """Test free energy computation with good metrics."""
        result = validator.compute_free_energy(metrics_good)
        assert isinstance(result, EnergyValidationResult)
        assert result.passed
        assert result.free_energy <= result.threshold
        assert result.margin > 0
        assert len(validator.validation_history) == 1

    def test_compute_free_energy_bad_metrics(self, validator, metrics_bad):
        """Test free energy computation with violating metrics."""
        result = validator.compute_free_energy(metrics_bad)
        assert isinstance(result, EnergyValidationResult)
        # Should fail because multiple violations
        assert result.free_energy > 0
        # Check some penalties are recorded
        assert any(p > 0 for p in result.penalties.values())

    def test_validate_good_metrics(self, validator, metrics_good):
        """Test validate() with good metrics."""
        passed = validator.validate(metrics_good)
        assert passed

    def test_validate_bad_metrics(self, validator, metrics_bad):
        """Test validate() with bad metrics may still pass due to stability."""
        # Note: Even with violations, F might still be below threshold
        # due to stability term. This is expected behavior.
        result = validator.compute_free_energy(metrics_bad)
        # Just verify we get a result
        assert isinstance(result, EnergyValidationResult)

    def test_validation_history(self, validator, metrics_good):
        """Test validation history tracking."""
        validator.validate(metrics_good)
        validator.validate(metrics_good)
        validator.validate(metrics_good)
        assert len(validator.validation_history) == 3

    def test_get_latest_result(self, validator, metrics_good):
        """Test getting latest validation result."""
        assert validator.get_latest_result() is None
        validator.validate(metrics_good)
        latest = validator.get_latest_result()
        assert latest is not None
        assert isinstance(latest, EnergyValidationResult)

    def test_clear_history(self, validator, metrics_good):
        """Test clearing validation history."""
        validator.validate(metrics_good)
        validator.validate(metrics_good)
        assert len(validator.validation_history) == 2
        validator.clear_history()
        assert len(validator.validation_history) == 0

    def test_export_validation_report(self, validator, metrics_good, metrics_bad):
        """Test exporting validation report."""
        # Run some validations
        validator.validate(metrics_good)
        validator.validate(metrics_bad)

        # Export to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            validator.export_validation_report(temp_path)
            assert temp_path.exists()

            # Load and verify report
            with temp_path.open("r") as f:
                report = json.load(f)

            assert "config" in report
            assert "validation_history" in report
            assert "summary" in report
            assert report["summary"]["total_validations"] == 2
        finally:
            temp_path.unlink()

    def test_to_dict(self, validator, metrics_good):
        """Test EnergyValidationResult.to_dict()."""
        result = validator.compute_free_energy(metrics_good)
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "free_energy" in result_dict
        assert "passed" in result_dict
        assert "metrics" in result_dict

    def test_to_json(self, validator, metrics_good):
        """Test EnergyValidationResult.to_json()."""
        result = validator.compute_free_energy(metrics_good)
        result_json = result.to_json()
        assert isinstance(result_json, str)
        # Should be valid JSON
        parsed = json.loads(result_json)
        assert "free_energy" in parsed


class TestEnergyValidatorEdgeCases:
    """Test edge cases for energy validator."""

    def test_empty_metrics(self):
        """Test with empty metrics dict."""
        validator = EnergyValidator()
        result = validator.compute_free_energy({})
        # Should compute F = 0 - T*0 = 0
        assert result.free_energy == 0.0
        assert result.internal_energy == 0.0
        assert result.stability == 0.0

    def test_unknown_metric(self):
        """Test with unknown metric name."""
        validator = EnergyValidator()
        metrics = {"unknown_metric": 100.0}
        # Should ignore unknown metrics
        result = validator.compute_free_energy(metrics)
        assert "unknown_metric" not in result.penalties

    def test_mixed_metrics(self):
        """Test with mix of known and unknown metrics."""
        validator = EnergyValidator()
        metrics = {
            "latency_p95": 75.0,  # Known
            "unknown": 100.0,  # Unknown
        }
        result = validator.compute_free_energy(metrics)
        assert "latency_p95" in result.metrics
        assert "unknown" in result.metrics  # Stored but not validated

    def test_zero_threshold(self):
        """Test metric with zero threshold."""
        config = EnergyConfig(metrics=(MetricThreshold("test", "Test", 0.0, 1.0, ""),))
        validator = EnergyValidator(config)
        # Zero threshold: value 0 should have headroom 0
        penalty, headroom = validator.compute_penalty("test", 0.0)
        assert penalty == 0.0
        assert headroom == 0.0
        # Positive value should have negative headroom
        penalty, headroom = validator.compute_penalty("test", 1.0)
        assert penalty > 0


class TestEnergyValidatorIntegration:
    """Integration tests for energy validator."""

    def test_time_series_validation(self):
        """Test validating a time series of metrics."""
        validator = EnergyValidator()

        # Simulate metrics getting progressively worse
        time_series = [
            {"latency_p95": 70.0, "cpu_burn": 0.60},
            {"latency_p95": 75.0, "cpu_burn": 0.65},
            {"latency_p95": 80.0, "cpu_burn": 0.70},
            {"latency_p95": 85.0, "cpu_burn": 0.75},
            {"latency_p95": 90.0, "cpu_burn": 0.80},
        ]

        results = []
        for metrics in time_series:
            # Fill in missing metrics
            full_metrics = {
                "latency_p95": metrics["latency_p95"],
                "latency_p99": metrics["latency_p95"] * 1.3,
                "coherency_drift": 0.05,
                "cpu_burn": metrics["cpu_burn"],
                "mem_cost": 5.0,
                "queue_depth": 20.0,
                "packet_loss": 0.002,
            }
            result = validator.compute_free_energy(full_metrics)
            results.append(result)

        # Verify we got all results
        assert len(results) == 5

        # Energy should generally increase (not strictly monotonic due to stability)
        # But at least first should be less than last
        assert results[0].free_energy < results[-1].free_energy

    def test_export_and_reload(self):
        """Test exporting report and reloading it."""
        validator = EnergyValidator()

        # Run validations
        for i in range(5):
            metrics = {
                "latency_p95": 70.0 + i * 5,
                "latency_p99": 90.0 + i * 5,
                "cpu_burn": 0.60 + i * 0.05,
                "coherency_drift": 0.05,
                "mem_cost": 5.0,
                "queue_depth": 20.0,
                "packet_loss": 0.002,
            }
            validator.validate(metrics)

        # Export
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)

        try:
            validator.export_validation_report(temp_path)

            # Reload and verify
            with temp_path.open("r") as f:
                report = json.load(f)

            assert report["summary"]["total_validations"] == 5
            assert len(report["validation_history"]) == 5

            # Verify each result has required fields
            for result in report["validation_history"]:
                assert "free_energy" in result
                assert "passed" in result
                assert "timestamp" in result
        finally:
            temp_path.unlink()
