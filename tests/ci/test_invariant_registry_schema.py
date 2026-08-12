from __future__ import annotations

from pathlib import Path

from scripts.check_invariant_registry_schema import DEFAULT_REGISTRY, validate_registry


def _write_registry(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_live_invariant_registry_satisfies_schema_contract() -> None:
    result = validate_registry(DEFAULT_REGISTRY)

    assert result["rows"] >= 90
    assert result["quality_score"] == 1.0
    assert result["errors"] == []


def test_schema_gate_rejects_missing_required_field(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "INVARIANTS.yaml",
        """
        group:
          row:
            id: INV-X1
            type: universal
            statement: ok
            priority: P0
        """,
    )

    result = validate_registry(registry)

    assert result["quality_score"] < 1.0
    assert any("missing required field test_type" in err for err in result["errors"])


def test_schema_gate_rejects_duplicate_ids(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "INVARIANTS.yaml",
        """
        a:
          x:
            id: INV-X1
            type: universal
            statement: ok
            test_type: property_test
            priority: P0
        b:
          y:
            id: INV-X1
            type: universal
            statement: ok
            test_type: property_test
            priority: P0
        """,
    )

    result = validate_registry(registry)

    assert any("duplicate invariant id INV-X1" in err for err in result["errors"])


def test_schema_gate_rejects_unresolved_related_reference(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "INVARIANTS.yaml",
        """
        group:
          row:
            id: INV-X1
            type: universal
            statement: ok
            test_type: property_test
            priority: P0
            related: [INV-MISSING]
        """,
    )

    result = validate_registry(registry)

    assert any(
        "unresolved related invariant 'INV-MISSING'" in err
        for err in result["errors"]
    )


def test_schema_gate_accepts_valid_fixture(tmp_path: Path) -> None:
    registry = _write_registry(
        tmp_path / "INVARIANTS.yaml",
        """
        group:
          row:
            id: INV-X1
            type: conservation
            statement: ok
            test_type: conservation
            priority: P1
            related: INV-X2
          row_2:
            id: INV-X2
            type: algebraic
            statement: ok
            test_type: property_test
            priority: P0
        """,
    )

    result = validate_registry(registry)

    assert result["rows"] == 2
    assert result["quality_score"] == 1.0
    assert result["errors"] == []
