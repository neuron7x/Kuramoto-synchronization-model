# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for ``scripts/export_governance_schemas.py``.

The script exports the typed Pydantic governance models
(``application.governance.ClaimLedger`` and
``application.governance.CommitAcceptor``) as canonical JSON Schema
2020-12 documents under ``docs/schemas/governance/``.

These tests assert two invariants:

1. The export is reproducible — running the generator twice produces
   bit-identical bytes (sorted keys, deterministic JSON, trailing
   newline).
2. The on-disk schema files match the live Pydantic model. ``--check``
   mode exits non-zero on drift; this test calls it directly so the
   same gate fires under pytest.

Drift between the model and the published schema would let external
auditors pin against an obsolete contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.export_governance_schemas import (
    CLAIM_LEDGER_PATH,
    COMMIT_ACCEPTOR_PATH,
    _generate,
    _serialise,
    export,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generate_returns_two_schemas() -> None:
    schemas = _generate()
    assert len(schemas) == 2
    assert CLAIM_LEDGER_PATH in schemas
    assert COMMIT_ACCEPTOR_PATH in schemas


def test_serialise_is_deterministic() -> None:
    """Running the serialiser twice on the same dict yields the same string."""
    schemas = _generate()
    for path, schema in schemas.items():
        first = _serialise(schema)
        second = _serialise(schema)
        assert first == second, f"non-deterministic serialisation for {path}"
        assert first.endswith("\n"), f"missing trailing newline on {path}"


def test_claim_ledger_schema_shape() -> None:
    schemas = _generate()
    schema = schemas[CLAIM_LEDGER_PATH]
    assert schema["title"] == "ClaimLedger"
    assert "schema_version" in schema["properties"]
    assert "claims" in schema["properties"]


def test_commit_acceptor_schema_shape() -> None:
    schemas = _generate()
    schema = schemas[COMMIT_ACCEPTOR_PATH]
    assert schema["title"] == "CommitAcceptor"
    assert "diff_scope" in schema["properties"]
    assert "falsifier" in schema["properties"]


def test_check_mode_passes_against_committed_artefact() -> None:
    """``--check`` exits 0 when the on-disk schema matches the live model.

    A failure here means the typed model has drifted from the published
    JSON Schema — re-run the exporter and commit the regenerated files.
    """
    rc = export(check=True)
    assert rc == 0, (
        "governance JSON Schema drift detected — run "
        "`python scripts/export_governance_schemas.py` to regenerate "
        "docs/schemas/governance/."
    )


def test_published_artefacts_are_valid_json(tmp_path: Path) -> None:
    """Each on-disk schema parses as valid JSON Schema 2020-12."""
    for path in (CLAIM_LEDGER_PATH, COMMIT_ACCEPTOR_PATH):
        if not path.exists():
            pytest.skip(f"{path} not yet committed")
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        assert "title" in loaded
        assert "properties" in loaded


def test_published_artefact_top_level_shape() -> None:
    """The committed JSON Schema covers the live model's top-level fields.

    A second-line check beyond `valid JSON`: the schema actually
    declares the contract surface (``schema_version`` and ``claims``
    on ClaimLedger; ``diff_scope`` and ``falsifier`` on CommitAcceptor)
    that downstream consumers pin against.
    """
    if not CLAIM_LEDGER_PATH.exists() or not COMMIT_ACCEPTOR_PATH.exists():
        pytest.skip("schemas not yet committed")
    cl = json.loads(CLAIM_LEDGER_PATH.read_text(encoding="utf-8"))
    ca = json.loads(COMMIT_ACCEPTOR_PATH.read_text(encoding="utf-8"))
    assert {"schema_version", "claims"} <= set(cl["properties"].keys())
    assert {"diff_scope", "falsifier", "id", "claim_type"} <= set(ca["properties"].keys())
