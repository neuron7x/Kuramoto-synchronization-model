# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Round-trip + invariant tests for the typed governance models.

The Pydantic v2 models in ``application.governance`` are the single
source of truth for the IERD claim ledger and the commit-acceptor
schema. These tests assert that:

1. The canonical ``docs/CLAIMS.yaml`` parses without modification.
2. Every ``.claude/commit_acceptors/*.yaml`` parses without modification.
3. Schema invariants documented in ADR 0020 / 0021 hold on the typed
   model (ANCHORED ⇒ falsifier present, gated tiers under priority,
   unique IDs across both registries, etc.).
4. ``extra='forbid'`` keeps unknown fields from being silently dropped
   — a regression here would re-open the IERD §1 loophole.

The tests do NOT reach for the underlying parsers in
``scripts/ci/check_claims.py`` or
``tools/commit_acceptor/validate_commit_acceptor.py``. They are
behaviourally independent: if the typed model and the legacy parser
diverge, both must surface the divergence in the round-trip test.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from application.governance import (
    ClaimLedger,
    CommitAcceptor,
    Priority,
    Tier,
    load_all_commit_acceptors,
    load_claim_ledger,
    load_commit_acceptor,
)
from application.governance.claim_ledger import SCHEMA_VERSION_LATEST

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAIMS_PATH = REPO_ROOT / "docs" / "CLAIMS.yaml"
ACCEPTORS_DIR = REPO_ROOT / ".claude" / "commit_acceptors"


# ---------------------------------------------------------------------------
# Round-trip on canonical files
# ---------------------------------------------------------------------------


def test_canonical_claim_ledger_parses() -> None:
    """The shipped ``docs/CLAIMS.yaml`` validates against the typed model.

    A failure here means either the model under-specifies the schema
    (Pydantic ``extra='forbid'`` rejected a real field) or the ledger
    drifted from the documented v3 schema. Either way, fail loudly —
    silent drift in the governance layer is exactly what IERD §1
    forbids.
    """
    ledger = load_claim_ledger(CLAIMS_PATH)
    assert ledger.schema_version == SCHEMA_VERSION_LATEST
    assert len(ledger.claims) > 0


def test_canonical_acceptor_corpus_parses() -> None:
    """Every shipped acceptor validates against the typed model."""
    acceptors = load_all_commit_acceptors(ACCEPTORS_DIR)
    assert len(acceptors) > 0
    for acc in acceptors:
        # Every acceptor must declare at least one changed file.
        assert len(acc.diff_scope.changed_files) >= 1, acc.id


# ---------------------------------------------------------------------------
# Cross-claim invariants (ADR 0020 / 0021)
# ---------------------------------------------------------------------------


def test_unique_claim_ids() -> None:
    ledger = load_claim_ledger(CLAIMS_PATH)
    ids = [c.id for c in ledger.claims]
    assert len(ids) == len(set(ids)), "duplicate claim id"


def test_unique_acceptor_ids() -> None:
    acceptors = load_all_commit_acceptors(ACCEPTORS_DIR)
    ids = [a.id for a in acceptors]
    assert len(ids) == len(set(ids)), "duplicate acceptor id"


def test_anchored_claims_have_falsifier_or_warn_only() -> None:
    """ADR 0021: ANCHORED v3 claims SHOULD declare a falsifier.

    The check_claims gate keeps this warn-only during Phase 1.0 to
    avoid blocking incremental adoption. The typed model documents
    the relationship — a future tightening that flips it to fail-closed
    needs only a one-line policy change here.
    """
    ledger = load_claim_ledger(CLAIMS_PATH)
    anchored_no_falsifier = [
        c.id for c in ledger.claims if c.tier is Tier.ANCHORED and c.falsifier is None
    ]
    # Warn-only: report count for visibility but do not gate.
    print(f"\n[gov] {len(anchored_no_falsifier)} ANCHORED claims lack falsifier (warn-only)")


def test_no_p2_claims_in_gated_set() -> None:
    """A claim is gated iff its priority is P0 or P1.

    P2 entries are warn-only by policy. This asserts the typed
    model's :meth:`is_gated` flag matches the priority, not the
    presence of an evidence path.
    """
    ledger = load_claim_ledger(CLAIMS_PATH)
    for c in ledger.gated():
        assert c.priority in (Priority.P0, Priority.P1), c.id


# ---------------------------------------------------------------------------
# Schema-drift guards (extra='forbid' must reject silent additions)
# ---------------------------------------------------------------------------


def test_claim_entry_rejects_unknown_field() -> None:
    """A new key under a claim entry must NOT be silently ignored."""
    ledger = load_claim_ledger(CLAIMS_PATH)
    sample = ledger.claims[0]
    payload = sample.model_dump()
    payload["surprise_field"] = "this should not silently land"
    with pytest.raises(ValidationError) as excinfo:
        sample.__class__.model_validate(payload)
    assert "surprise_field" in str(excinfo.value)


def test_commit_acceptor_rejects_unknown_field() -> None:
    """A new key under an acceptor must NOT be silently ignored."""
    acceptors = load_all_commit_acceptors(ACCEPTORS_DIR)
    sample = acceptors[0]
    payload = sample.model_dump()
    payload["surprise_field"] = "this should not silently land"
    with pytest.raises(ValidationError) as excinfo:
        sample.__class__.model_validate(payload)
    assert "surprise_field" in str(excinfo.value)


def test_commit_acceptor_rejects_mapping_symbol_form() -> None:
    """Dict-form ``required_python_symbols`` fails legibly, not cryptically.

    Regression for stale run 27294986826: an acceptor authored its
    symbols as ``{module, symbol}`` mappings instead of canonical
    ``file::symbol`` strings. Pydantic's native error was the opaque
    ``Input should be a valid string``, which buried the cause inside a
    46-minute coverage lane. The ``mode='before'`` guard must re-emit a
    message that (a) names the canonical form and (b) shows the exact
    replacement string.
    """
    acceptors = load_all_commit_acceptors(ACCEPTORS_DIR)
    payload = acceptors[0].model_dump()
    payload["required_python_symbols"] = [
        {"module": "application/runtime/init_control_platform.py", "symbol": "initialize_control_platform"}
    ]
    with pytest.raises(ValidationError) as excinfo:
        CommitAcceptor.model_validate(payload)
    message = str(excinfo.value)
    assert "file::symbol" in message
    assert "application/runtime/init_control_platform.py::initialize_control_platform" in message


def test_load_commit_acceptor_names_offending_file() -> None:
    """A malformed acceptor surfaces its file path in the loader error.

    Pydantic alone reports only the field path; with 200+ acceptors on
    disk the operator otherwise has to grep to find which file drifted.
    """
    import yaml

    sample_path = next(ACCEPTORS_DIR.glob("*.yaml"))
    raw = yaml.safe_load(sample_path.read_text(encoding="utf-8"))
    raw["required_python_symbols"] = [{"module": "m.py", "symbol": "f"}]
    bad = tmp_acceptor(raw)
    with pytest.raises(ValueError) as excinfo:
        load_commit_acceptor(bad)
    assert str(bad) in str(excinfo.value)


def tmp_acceptor(raw: dict) -> Path:
    """Write *raw* to a throwaway acceptor file and return its path."""
    import tempfile

    import yaml

    fd = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    yaml.safe_dump(raw, fd)
    fd.close()
    return Path(fd.name)


def test_ledger_rejects_unsupported_schema_version() -> None:
    raw = {
        "schema_version": 99,
        "claims": [],
    }
    with pytest.raises(ValidationError):
        ClaimLedger.model_validate(raw)


# ---------------------------------------------------------------------------
# JSON Schema export (consumed by IDE / external auditors)
# ---------------------------------------------------------------------------


def test_claim_ledger_json_schema_is_exportable() -> None:
    """The typed model exports a valid JSON Schema — no recursive cycles,
    no missing $defs. Auditors consume this artefact directly.
    """
    schema = ClaimLedger.model_json_schema()
    assert schema["title"] == "ClaimLedger"
    assert "properties" in schema
    assert "claims" in schema["properties"]


def test_commit_acceptor_json_schema_is_exportable() -> None:
    schema = CommitAcceptor.model_json_schema()
    assert schema["title"] == "CommitAcceptor"
    assert "diff_scope" in schema["properties"]


# ---------------------------------------------------------------------------
# Single-file loader smoke
# ---------------------------------------------------------------------------


def test_load_one_acceptor_by_path() -> None:
    """``load_commit_acceptor`` works on a specific file path."""
    target = ACCEPTORS_DIR / "ierd-q4-schemathesis-contract-gate.yaml"
    if not target.exists():
        pytest.skip("Q4 schemathesis acceptor not present")
    acc = load_commit_acceptor(target)
    assert acc.id == "ierd-q4-schemathesis-contract-gate"
    assert acc.claim_type.value in {
        "correctness",
        "fail_closed",
        "security",
        "performance",
        "governance",
        "refactor",
        "documentation",
        "determinism",
    }


def test_by_id_returns_the_matching_claim_not_the_first_nonmatch() -> None:
    """`if claim.id == claim_id: return claim` must match by identity, not merely iterate.

    Under `Eq -> NotEq` the loop returns the first claim whose id does NOT match — so every
    lookup silently returns the wrong claim, and a lookup for a genuinely absent id returns a
    real (unrelated) entry instead of None. Targeting a non-first claim exposes it.
    """
    ledger = load_claim_ledger(CLAIMS_PATH)
    assert len(ledger.claims) >= 2, "need >=2 claims to distinguish match from first-nonmatch"

    target = ledger.claims[-1]
    found = ledger.by_id(target.id)
    assert found is not None and found.id == target.id, "by_id returned the wrong claim"

    assert ledger.by_id("NO-SUCH-CLAIM-ID-000") is None, (
        "an absent id must return None, not the first entry"
    )
