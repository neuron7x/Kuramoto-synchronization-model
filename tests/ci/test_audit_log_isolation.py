# SPDX-License-Identifier: MIT
"""Non-vacuous regression: pytest may not append into tracked audit evidence."""

from __future__ import annotations

from pathlib import Path

from observability.audit.trail import get_access_audit_trail, get_system_audit_trail

ROOT = Path(__file__).resolve().parents[2]


def test_canonical_audit_sinks_are_isolated_from_source_tree() -> None:
    access = get_access_audit_trail().path.resolve()
    system = get_system_audit_trail().path.resolve()
    assert access != (ROOT / "observability/audit/access.jsonl").resolve()
    assert system != (ROOT / "observability/audit/system.jsonl").resolve()
    assert access.parent.is_dir()
    assert system.parent.is_dir()
