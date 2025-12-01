from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.versioning import (
    AccessDeniedError,
    AccessGate,
    CompatibilityContract,
    FormatMigration,
    LifecycleState,
    LineageRecord,
    OperationalTag,
    SemanticVersion,
    VersioningError,
    VersionRegistry,
)


def test_semantic_version_parsing_and_ordering() -> None:
    v1 = SemanticVersion.parse("1.2.3")
    v2 = SemanticVersion.parse("1.3.0")
    v3 = SemanticVersion.parse("2.0.0")

    assert str(v1) == "1.2.3"
    assert v2 > v1
    assert v2.is_backward_compatible_with(v1)
    assert not v3.is_backward_compatible_with(v1)


def test_register_and_activate_multiple_versions() -> None:
    registry = VersionRegistry()
    contract = CompatibilityContract(
        name="fraud-model",
        schema_version=SemanticVersion.parse("1.0.0"),
        input_schema="schema://fraud-model/request@1",
        output_schema="schema://fraud-model/response@1",
    )
    tag = OperationalTag(name="sla.gold", description="Gold tier latency budget")

    v1 = registry.register_version(
        "fraud-model",
        kind="model",
        version="1.0.0",
        contract=contract,
        operational_tags=[tag],
        tags={"baseline"},
        lineage=LineageRecord(
            parent_versions=("fraud-model:0.9.0",),
            data_fingerprint="abc123",
            created_by="mlops@tradepulse",  # nosec - test data
        ),
    )

    v2 = registry.register_version(
        "fraud-model",
        kind="model",
        version="1.1.0",
        contract=contract,
        tags={"canary"},
    )

    registry.promote("fraud-model", "1.0.0", target_state=LifecycleState.STAGING)
    registry.promote("fraud-model", "1.1.0", target_state=LifecycleState.STAGING)

    registry.set_active("fraud-model", "1.0.0", active=True)
    registry.set_active("fraud-model", "1.1.0", active=True)

    active_versions = registry.active_versions(kind="model")
    assert {entry.semantic_version for entry in active_versions} == {
        SemanticVersion.parse("1.0.0"),
        SemanticVersion.parse("1.1.0"),
    }
    assert v1.operational_tags == {tag}
    assert v1.tags == {"baseline"}
    assert v2.tags == {"canary"}


def test_access_gates_enforced() -> None:
    registry = VersionRegistry()
    contract = CompatibilityContract(
        name="dataset",
        schema_version=SemanticVersion.parse("1.0.0"),
        input_schema="schema://dataset/source@1",
        output_schema="schema://dataset/record@1",
    )

    registry.register_version(
        "orders-dataset",
        kind="dataset",
        version="3.0.0",
        contract=contract,
        access_gates=[
            AccessGate(
                name="region.eu", condition=lambda ctx: ctx.get("region") == "eu"
            )
        ],
    )

    registry.promote("orders-dataset", "3.0.0", target_state=LifecycleState.STAGING)
    registry.set_active("orders-dataset", "3.0.0", active=True)

    with pytest.raises(AccessDeniedError):
        registry.ensure_access("orders-dataset", "3.0.0", context={"region": "us"})

    registry.ensure_access("orders-dataset", "3.0.0", context={"region": "eu"})


def test_contract_validation_and_migration() -> None:
    registry = VersionRegistry()
    base_contract = CompatibilityContract(
        name="signals",
        schema_version=SemanticVersion.parse("1.0.0"),
        input_schema="schema://signals/request@1",
        output_schema="schema://signals/response@1",
        additional_checks=("latency<100ms",),
    )

    registry.register_version(
        "signals",
        kind="model",
        version="1.0.0",
        contract=base_contract,
    )

    def migrate(payload: dict[str, int]) -> dict[str, int]:
        return {**payload, "new_feature": 1}

    registry.add_migration(
        "signals",
        "1.0.0",
        FormatMigration(
            source=SemanticVersion.parse("1.0.0"),
            target=SemanticVersion.parse("1.1.0"),
            apply=migrate,
        ),
    )

    compatible_contract = CompatibilityContract(
        name="signals",
        schema_version=SemanticVersion.parse("1.1.0"),
        input_schema="schema://signals/request@1",
        output_schema="schema://signals/response@1",
        additional_checks=("latency<100ms", "error_rate<0.5%"),
    )

    assert registry.validate_contract("signals", "1.0.0", against=compatible_contract)

    migrated = registry.migrate_payload("signals", "1.0.0", "1.1.0", {"a": 1})
    assert migrated["new_feature"] == 1


def test_lifecycle_transitions_and_rollbacks() -> None:
    registry = VersionRegistry()
    contract = CompatibilityContract(
        name="forecaster",
        schema_version=SemanticVersion.parse("2.0.0"),
        input_schema="schema://forecaster/request@2",
        output_schema="schema://forecaster/response@2",
    )

    registry.register_version(
        "forecaster",
        kind="model",
        version="2.1.0",
        contract=contract,
    )

    registry.promote("forecaster", "2.1.0", target_state=LifecycleState.STAGING)
    registry.promote("forecaster", "2.1.0", target_state=LifecycleState.PRODUCTION)
    registry.promote("forecaster", "2.1.0", target_state=LifecycleState.DEPRECATED)

    rollback = registry.record_rollback(
        target_version="forecaster:2.1.0",
        restored_version="forecaster:2.0.0",
        reason="Performance regression",
        performed_by="sre@tradepulse",  # nosec - test data
    )

    history = registry.rollback_history()
    assert history[-1] == rollback

    with pytest.raises(Exception):
        registry.promote("forecaster", "2.1.0", target_state=LifecycleState.DRAFT)


def test_semantic_version_bump_methods() -> None:
    """Test semantic version bumping for major, minor, and patch."""
    v1 = SemanticVersion.parse("1.2.3")

    # Patch bump (default)
    v_patch = v1.bump()
    assert str(v_patch) == "1.2.4"

    # Minor bump (explicitly set patch=False)
    v_minor = v1.bump(minor=True, patch=False)
    assert str(v_minor) == "1.3.0"

    # Major bump (explicitly set patch=False)
    v_major = v1.bump(major=True, patch=False)
    assert str(v_major) == "2.0.0"


def test_semantic_version_invalid_parsing() -> None:
    """Test that invalid semantic versions raise ValueError."""
    with pytest.raises(ValueError, match="Invalid semantic version"):
        SemanticVersion.parse("1.2")

    with pytest.raises(ValueError, match="Invalid semantic version"):
        SemanticVersion.parse("1.2.3.4")

    with pytest.raises(ValueError, match="Invalid semantic version"):
        SemanticVersion.parse("v1.2.3")


def test_version_registry_duplicate_registration() -> None:
    """Test that duplicate version registration raises error."""
    registry = VersionRegistry()
    contract = CompatibilityContract(
        name="test",
        schema_version=SemanticVersion.parse("1.0.0"),
        input_schema="in",
        output_schema="out",
    )

    registry.register_version(
        "test-model",
        kind="model",
        version="1.0.0",
        contract=contract,
    )

    with pytest.raises(VersioningError, match="already registered"):
        registry.register_version(
            "test-model",
            kind="model",
            version="1.0.0",
            contract=contract,
        )


def test_version_registry_get_nonexistent_version() -> None:
    """Test that getting a nonexistent version raises error."""
    registry = VersionRegistry()

    with pytest.raises(VersioningError, match="not registered"):
        registry.get("nonexistent", "1.0.0")


def test_operational_tag_hash_deterministic() -> None:
    """Test that OperationalTag with metadata has deterministic hash."""
    tag1 = OperationalTag(
        name="priority.high",
        description="High priority",
        metadata={"level": 1, "color": "red"},
    )
    tag2 = OperationalTag(
        name="priority.high",
        description="High priority",
        metadata={"color": "red", "level": 1},  # Same data, different order
    )

    # Hash should be the same
    assert hash(tag1) == hash(tag2)

    # Tags should be usable in sets
    tag_set = {tag1, tag2}
    assert len(tag_set) == 1


def test_lineage_record_timezone_normalization() -> None:
    """Test that LineageRecord normalizes timezone to UTC."""
    # Create with naive datetime
    naive_dt = datetime(2024, 1, 15, 12, 0, 0)
    record1 = LineageRecord(
        parent_versions=(),
        data_fingerprint="abc",
        created_by="test",
        created_at=naive_dt,
    )
    assert record1.created_at.tzinfo == timezone.utc

    # Create with non-UTC timezone
    est = timezone(timedelta(hours=-5))
    est_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=est)
    record2 = LineageRecord(
        parent_versions=(),
        data_fingerprint="def",
        created_by="test",
        created_at=est_dt,
    )
    assert record2.created_at.tzinfo == timezone.utc
    # Should be converted to UTC (12:00 EST = 17:00 UTC)
    assert record2.created_at.hour == 17
