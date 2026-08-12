# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/session/ingest_session_dump.py."""

from __future__ import annotations

from pathlib import Path

from tools.session.ingest_session_dump import (
    IngestionStatus,
    ingest_dump,
    write_ledger_entry,
)

_GOOD_DUMP = """\
# Session Dump 2026-04-27

closure: CLOSED
remaining_uncertainty: lint-imports not yet wired

## Decisions
- Adopt manifest-backed regression detector
- Flip false-confidence advisory to fail-closed

## Accepted claims
- 71 historical findings recorded with reasons
- Detector now blocks NEW findings

## Rejected claims
- "advisory CI is sufficient"

## PR numbers
- #472, #473

## Lie blocked
- advisory CI = silent acceptance of historical state

## Falsifier
- removed one C10 entry → detector re-emitted that finding

## Next tasks
- wire lint-imports
"""


_INVALID_CLOSED_NO_FALSIFIER = """\
closure: CLOSED
remaining_uncertainty: none

## Decisions
- did the thing

## Lie blocked
- thing was lying
"""


_PARTIAL_DUMP = """\
closure: PARTIAL
remaining_uncertainty: P10 module exists but chain only wires P1..P6

## Decisions
- ship P10 standalone

## PR numbers
- #471
"""


_INVALID_NO_CLOSURE = """\
## Decisions
- did stuff
## Falsifier
- broke and restored
"""


def test_good_dump_yields_ok_closed() -> None:
    report = ingest_dump(_GOOD_DUMP, session_id="2026-04-27-T1", ingested_at="2026-04-27T15:00:00Z")
    assert report.status is IngestionStatus.OK_CLOSED
    assert report.record is not None
    assert report.record.closure_status == "CLOSED"
    assert "Adopt manifest-backed regression detector" in report.record.decisions
    assert 472 in report.record.pr_numbers and 473 in report.record.pr_numbers
    assert any("advisory CI" in line for line in report.record.lie_blocked)
    assert report.record.falsifier  # non-empty


def test_closed_without_falsifier_rejected() -> None:
    """Falsifier surface from brief: CLOSED without falsifier → INVALID."""
    report = ingest_dump(
        _INVALID_CLOSED_NO_FALSIFIER,
        session_id="bad",
        ingested_at="2026-04-27T15:00:00Z",
    )
    assert report.status is IngestionStatus.INVALID
    assert any("falsifier" in e for e in report.errors)


def test_partial_status_with_uncertainty_accepted() -> None:
    report = ingest_dump(
        _PARTIAL_DUMP,
        session_id="2026-04-27-T2",
        ingested_at="2026-04-27T15:00:00Z",
    )
    assert report.status is IngestionStatus.OK_PARTIAL
    assert report.record is not None
    assert report.record.remaining_uncertainty.startswith("P10 module exists")


def test_no_closure_status_rejected() -> None:
    report = ingest_dump(
        _INVALID_NO_CLOSURE,
        session_id="bad",
        ingested_at="2026-04-27T15:00:00Z",
    )
    assert report.status is IngestionStatus.INVALID
    assert any("closure_status" in e for e in report.errors)


def test_pr_numbers_extracted_from_mixed_text() -> None:
    dump = """\
closure: CLOSED
remaining_uncertainty: none

## PR numbers
- merged #455 and 461 today, then #462 follow-up

## Falsifier
- mutation re-introduced lie
"""
    report = ingest_dump(dump, session_id="x", ingested_at="2026-04-27T15:00:00Z")
    assert report.record is not None
    assert 455 in report.record.pr_numbers
    assert 461 in report.record.pr_numbers
    assert 462 in report.record.pr_numbers


def test_partial_without_uncertainty_rejected() -> None:
    dump = """\
closure: PARTIAL

## Decisions
- partial work
"""
    report = ingest_dump(dump, session_id="x", ingested_at="2026-04-27T15:00:00Z")
    assert report.status is IngestionStatus.INVALID


def test_blocked_with_uncertainty_accepted() -> None:
    dump = """\
closure: BLOCKED
remaining_uncertainty: upstream stub fix required

## Decisions
- pause
"""
    report = ingest_dump(dump, session_id="x", ingested_at="2026-04-27T15:00:00Z")
    assert report.status is IngestionStatus.OK_BLOCKED


def test_write_ledger_entry_persists_yaml(tmp_path: Path) -> None:
    report = ingest_dump(
        _GOOD_DUMP,
        session_id="2026-04-27-T1",
        ingested_at="2026-04-27T15:00:00Z",
    )
    path = write_ledger_entry(report, tmp_path / "ledger")
    assert path is not None
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "schema_version" in text
    assert "session_id" in text


def test_invalid_record_does_not_write_ledger(tmp_path: Path) -> None:
    report = ingest_dump(
        _INVALID_CLOSED_NO_FALSIFIER,
        session_id="bad",
        ingested_at="2026-04-27T15:00:00Z",
    )
    path = write_ledger_entry(report, tmp_path / "ledger")
    assert path is None


def test_deterministic_at_same_input() -> None:
    a = ingest_dump(_GOOD_DUMP, session_id="x", ingested_at="2026-04-27T15:00:00Z")
    b = ingest_dump(_GOOD_DUMP, session_id="x", ingested_at="2026-04-27T15:00:00Z")
    assert a.to_dict() == b.to_dict()
