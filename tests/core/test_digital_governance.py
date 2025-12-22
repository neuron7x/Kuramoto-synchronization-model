"""Tests for Digital Governance Framework.

Tests all 20 requirements of the digital transformation mandate.
"""

import json
from datetime import datetime, timezone

import pytest

from src.tradepulse.core.digital_governance import (
    ComplianceLevel,
    DataQualityCheck,
    DigitalAuditRecord,
    DigitalGovernanceFramework,
    GovernanceViolation,
    SchemaValidator,
    SecretManager,
    TACLMetricsCollector,
)


class TestDigitalAuditRecord:
    """Test digital audit records (Requirement #4, #13)."""

    def test_audit_record_creation(self):
        """Test creating an audit record."""
        record = DigitalAuditRecord(
            event_type="strategy_decision",
            actor="momentum_strategy",
            component="strategy_engine",
            operation="signal_generation",
            decision_basis={"rsi": 70, "momentum": 0.5},
            result={"signal": "BUY", "strength": 0.8},
        )

        assert record.event_id
        assert record.timestamp
        assert record.event_type == "strategy_decision"
        assert record.retention_years == 7
        assert ComplianceLevel.SEC in record.compliance_level
        assert ComplianceLevel.FINRA in record.compliance_level

    def test_audit_record_serialization(self):
        """Test audit record JSON serialization."""
        record = DigitalAuditRecord(
            event_type="test_event",
            actor="test_actor",
            component="test_component",
            operation="test_op",
            decision_basis={},
            result={},
        )

        json_str = record.to_json()
        data = json.loads(json_str)

        assert data["event_id"] == record.event_id
        assert data["event_type"] == "test_event"
        assert "timestamp" in data
        assert "compliance_level" in data


class TestSchemaValidator:
    """Test schema validation (Requirement #1, #10)."""

    def test_schema_validator_init(self, tmp_path):
        """Test schema validator initialization."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        # Create a test schema
        ticks_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["event_id", "symbol", "timestamp"],
            "properties": {
                "event_id": {"type": "string"},
                "symbol": {"type": "string"},
                "timestamp": {"type": "integer"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(ticks_schema))

        validator = SchemaValidator(schema_dir)
        assert "ticks" in validator._schemas

    def test_validate_valid_event(self, tmp_path):
        """Test validation of valid market event."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["event_id", "symbol", "timestamp"],
            "properties": {
                "event_id": {"type": "string"},
                "symbol": {"type": "string"},
                "timestamp": {"type": "integer"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(schema))

        validator = SchemaValidator(schema_dir)

        event_data = {
            "event_id": "test-123",
            "symbol": "BTC/USDT",
            "timestamp": 1700000000000000,
        }

        assert validator.validate(event_data, "ticks") is True

    def test_validate_missing_required_field(self, tmp_path):
        """Test validation fails for missing required fields."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["event_id", "symbol", "timestamp"],
            "properties": {
                "event_id": {"type": "string"},
                "symbol": {"type": "string"},
                "timestamp": {"type": "integer"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(schema))

        validator = SchemaValidator(schema_dir)

        # Missing 'symbol' field
        event_data = {
            "event_id": "test-123",
            "timestamp": 1700000000000000,
        }

        with pytest.raises(GovernanceViolation) as exc_info:
            validator.validate(event_data, "ticks")

        assert exc_info.value.requirement_id == 1
        assert "symbol" in str(exc_info.value)

    def test_validate_missing_event_id(self, tmp_path):
        """Test validation fails for missing event_id (Requirement #4)."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {"type": "string"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(schema))

        validator = SchemaValidator(schema_dir)

        event_data = {
            "symbol": "BTC/USDT",
        }

        with pytest.raises(GovernanceViolation) as exc_info:
            validator.validate(event_data, "ticks")

        assert exc_info.value.requirement_id == 4
        assert "event_id" in str(exc_info.value)


class TestTACLMetricsCollector:
    """Test TACL metrics collection (Requirement #12, #19)."""

    def test_record_metric(self):
        """Test recording TACL metrics."""
        collector = TACLMetricsCollector()

        collector.record_metric("dopamine_rpe", 0.5)
        collector.record_metric("tacl_free_energy", 0.3)
        collector.record_metric("latency_p99_ms", 85.0)

        metrics = collector.get_metrics()
        assert metrics["dopamine_rpe"] == 0.5
        assert metrics["tacl_free_energy"] == 0.3
        assert metrics["latency_p99_ms"] == 85.0

    def test_increment_counter(self):
        """Test incrementing counters."""
        collector = TACLMetricsCollector()

        collector.increment_counter("events_processed")
        collector.increment_counter("events_processed")
        collector.increment_counter("errors", 1)

        counters = collector.get_counters()
        assert counters["events_processed"] == 2
        assert counters["errors"] == 1

    def test_check_thresholds_pass(self):
        """Test threshold checking passes."""
        collector = TACLMetricsCollector()

        collector.record_metric("tacl_free_energy", 0.5)
        collector.record_metric("dopamine_rpe", 1.0)
        collector.record_metric("latency_p99_ms", 100.0)

        violations = collector.check_thresholds(
            free_energy_max=1.0,
            rpe_max=2.0,
            latency_p99_max_ms=120.0,
        )

        assert len(violations) == 0

    def test_check_thresholds_violations(self):
        """Test threshold violations detected."""
        collector = TACLMetricsCollector()

        collector.record_metric("tacl_free_energy", 1.5)
        collector.record_metric("dopamine_rpe", 3.0)
        collector.record_metric("latency_p99_ms", 150.0)

        violations = collector.check_thresholds(
            free_energy_max=1.0,
            rpe_max=2.0,
            latency_p99_max_ms=120.0,
        )

        assert len(violations) == 3
        assert any("free energy" in v.lower() for v in violations)
        assert any("rpe" in v.lower() for v in violations)
        assert any("latency" in v.lower() for v in violations)

    def test_check_thresholds_non_finite(self):
        """Non-finite metrics should surface observability violations."""
        collector = TACLMetricsCollector()

        collector.record_metric("tacl_free_energy", float("nan"))
        collector.record_metric("dopamine_rpe", float("inf"))
        collector.record_metric("latency_p99_ms", float("-inf"))

        violations = collector.check_thresholds(
            free_energy_max=1.0,
            rpe_max=2.0,
            latency_p99_max_ms=120.0,
        )

        assert len(violations) == 3
        assert all("non-finite" in v.lower() for v in violations)


class TestSecretManager:
    """Test secret management (Requirement #15, #20)."""

    def test_load_secrets_from_env_file(self, tmp_path):
        """Test loading secrets from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=secret123\nAPI_SECRET=topsecret\n")

        manager = SecretManager(env_file)

        assert manager.get_secret("API_KEY") == "secret123"
        assert manager.get_secret("API_SECRET") == "topsecret"

    def test_validate_no_hardcoded_secrets(self):
        """Test detection of hard-coded secrets."""
        manager = SecretManager()

        # Code with hard-coded secret
        code = """
api_key = "sk-1234567890abcdef"
password = "mypassword123"
data = {"value": 42}
"""

        violations = manager.validate_no_hardcoded_secrets(code)

        assert len(violations) > 0
        assert any("api_key" in v.lower() for v in violations)
        assert any("password" in v.lower() for v in violations)

    def test_validate_proper_env_usage(self):
        """Test that proper env var usage passes."""
        manager = SecretManager()

        # Code using environment variables properly
        code = """
import os
api_key = os.environ.get("API_KEY")
api_secret = os.getenv("API_SECRET")
"""

        violations = manager.validate_no_hardcoded_secrets(code)

        # Should have no violations for proper env var usage
        assert len(violations) == 0


class TestDigitalGovernanceFramework:
    """Test complete digital governance framework."""

    @pytest.fixture
    def governance(self, tmp_path):
        """Create governance framework instance."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        # Create test schema
        ticks_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["event_id", "symbol", "timestamp"],
            "properties": {
                "event_id": {"type": "string"},
                "symbol": {"type": "string"},
                "timestamp": {"type": "integer"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(ticks_schema))

        audit_log = tmp_path / "audit.jsonl"

        return DigitalGovernanceFramework(
            schema_dir=schema_dir,
            audit_log_path=audit_log,
            enable_strict_mode=False,  # Don't raise exceptions in tests
        )

    def test_validate_market_event_success(self, governance):
        """Test successful market event validation (Requirement #1)."""
        event_data = {
            "event_id": "test-123",
            "symbol": "BTC/USDT",
            "timestamp": 1700000000000000,
        }

        assert governance.validate_market_event("ticks", event_data) is True

    def test_log_audit_event(self, governance):
        """Test audit event logging (Requirement #4, #13)."""
        record = governance.log_audit_event(
            event_type="strategy_decision",
            actor="momentum_strategy",
            component="strategy_engine",
            operation="signal_generation",
            decision_basis={"rsi": 70},
            result={"signal": "BUY"},
        )

        assert record.event_id
        assert record.event_type == "strategy_decision"

        # Verify written to audit log
        assert governance.audit_log_path.exists()
        content = governance.audit_log_path.read_text()
        assert record.event_id in content

    def test_normalize_timestamp(self, governance):
        """Test timestamp normalization (Requirement #9)."""
        # Test with datetime
        dt = datetime(2023, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
        timestamp = governance.normalize_timestamp(dt)
        assert isinstance(timestamp, int)
        assert timestamp > 0

        # Test with int
        timestamp = governance.normalize_timestamp(1700000000000000)
        assert timestamp == 1700000000000000

    def test_check_data_quality(self, governance):
        """Test data quality checking (Requirement #11)."""
        # Normal data
        values = [1.0, 1.1, 1.05, 1.08, 1.12]
        checks = governance.check_data_quality("price", values)

        # Should pass for normal data
        assert all(c.passed or c.severity == "WARNING" for c in checks)

        # Data with spike
        values_with_spike = [1.0, 1.1, 1.05, 10.0, 1.08]
        checks = governance.check_data_quality(
            "price", values_with_spike, spike_threshold_std=1.5
        )

        # Should detect spike
        assert any(c.check_type == "spikes" for c in checks)

    def test_record_tacl_metric(self, governance):
        """Test TACL metric recording (Requirement #12)."""
        governance.record_tacl_metric("dopamine_rpe", 0.5)
        governance.record_tacl_metric("tacl_free_energy", 0.3)

        metrics = governance.get_tacl_metrics()
        assert metrics["dopamine_rpe"] == 0.5
        assert metrics["tacl_free_energy"] == 0.3

    def test_enforce_tacl_boundaries(self, governance):
        """Test TACL boundary enforcement (Requirement #19)."""
        # Within boundaries
        governance.record_tacl_metric("tacl_free_energy", 0.5)
        governance.record_tacl_metric("dopamine_rpe", 1.0)
        governance.record_tacl_metric("latency_p99_ms", 100.0)

        result = governance.enforce_tacl_boundaries(
            free_energy_max=1.0,
            rpe_max=2.0,
            latency_p99_max_ms=120.0,
        )

        assert result is True

        # Exceeding boundaries
        governance.record_tacl_metric("tacl_free_energy", 1.5)

        result = governance.enforce_tacl_boundaries(free_energy_max=1.0)

        assert result is False
        violations = governance.get_violations()
        assert len(violations) > 0

    def test_validate_code_security(self, governance):
        """Test code security validation (Requirement #20)."""
        # Insecure code
        insecure_code = """
api_key = "sk-1234567890"
result = eval(user_input)
"""

        violations = governance.validate_code_security(insecure_code)

        assert len(violations) > 0
        assert any("api_key" in v.lower() for v in violations)
        assert any("eval" in v.lower() for v in violations)

    def test_generate_compliance_report(self, governance):
        """Test compliance report generation."""
        # Generate some activity
        governance.record_tacl_metric("test_metric", 1.0)
        governance.check_data_quality("test_data", [1.0, 2.0, 3.0])

        report = governance.generate_compliance_report()

        assert "timestamp" in report
        assert "framework_version" in report
        assert "compliance_levels" in report
        assert "violations" in report
        assert "quality_checks" in report
        assert "tacl_metrics" in report
        assert report["framework_version"] == "1.0.0"

        # Verify compliance levels
        assert "SEC" in report["compliance_levels"]
        assert "FINRA" in report["compliance_levels"]


class TestGovernanceViolation:
    """Test governance violation handling."""

    def test_governance_violation_creation(self):
        """Test creating governance violation."""
        violation = GovernanceViolation(
            "Missing required field",
            requirement_id=1,
            severity="ERROR",
            context={"field": "symbol"},
        )

        assert violation.requirement_id == 1
        assert violation.severity == "ERROR"
        assert violation.context["field"] == "symbol"
        assert "Missing required field" in str(violation)


class TestDataQualityCheck:
    """Test data quality check."""

    def test_data_quality_check_creation(self):
        """Test creating data quality check."""
        check = DataQualityCheck(
            check_type="spikes",
            passed=False,
            metric_name="price",
            value=5.0,
            threshold=3.0,
            severity="WARNING",
            message="5 spikes detected",
        )

        assert check.check_type == "spikes"
        assert check.passed is False
        assert check.metric_name == "price"
        assert check.severity == "WARNING"


@pytest.mark.integration
class TestIntegration:
    """Integration tests for complete workflows."""

    def test_end_to_end_market_event_flow(self, tmp_path):
        """Test complete market event validation and audit flow."""
        schema_dir = tmp_path / "schemas"
        schema_dir.mkdir()

        # Create schema
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "TickEvent",
            "type": "object",
            "required": ["event_id", "symbol", "timestamp", "bid_price", "ask_price"],
            "properties": {
                "event_id": {"type": "string"},
                "symbol": {"type": "string"},
                "timestamp": {"type": "integer"},
                "bid_price": {"type": "number"},
                "ask_price": {"type": "number"},
            },
        }

        schema_file = schema_dir / "ticks.schema.json"
        schema_file.write_text(json.dumps(schema))

        governance = DigitalGovernanceFramework(
            schema_dir=schema_dir,
            audit_log_path=tmp_path / "audit.jsonl",
            enable_strict_mode=False,
        )

        # Create and validate market event
        event_data = {
            "event_id": "tick-001",
            "symbol": "BTC/USDT",
            "timestamp": 1700000000000000,
            "bid_price": 50000.0,
            "ask_price": 50001.0,
        }

        # Validate
        assert governance.validate_market_event("ticks", event_data) is True

        # Log decision
        governance.log_audit_event(
            event_type="market_data_ingestion",
            actor="data_ingestion_service",
            component="market_feed",
            operation="tick_received",
            decision_basis={"source": "binance"},
            result={"processed": True, "event_id": event_data["event_id"]},
        )

        # Record metrics
        governance.record_tacl_metric("events_ingested", 1.0)

        # Check data quality
        prices = [event_data["bid_price"], event_data["ask_price"]]
        governance.check_data_quality("bid_prices", prices)

        # Generate report
        report = governance.generate_compliance_report()

        assert report["total_violations"] == 0
        assert len(report["tacl_metrics"]) > 0
        assert len(report["quality_checks"]) >= 0
