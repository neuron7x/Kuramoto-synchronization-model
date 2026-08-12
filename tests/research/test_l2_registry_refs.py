# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for L2 Ricci baseline/null/falsifier registry resolution.

Pins the P1-3 hardening invariant: an L2 Ricci session's ``baseline_id``,
``null_model_id``, and ``falsifier_id`` are provenance only if they RESOLVE to a
described entry in ``config/research/l2_ricci_registry.yaml``. An id that names
nothing is an unfalsifiable placeholder and MUST be rejected, fail-closed. The
``*_unset`` ids the ``--dry-run`` skeleton emits MUST NOT resolve.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tools" / "research" / "check_l2_registry_refs.py"
SESSION_TOOL_PATH = ROOT / "tools" / "research" / "run_l2_ricci_session.py"
REGISTRY_PATH = ROOT / "config" / "research" / "l2_ricci_registry.yaml"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load(TOOL_PATH, "_check_l2_registry_refs")
session_tool = _load(SESSION_TOOL_PATH, "_run_l2_ricci_session_for_registry")


def _write(tmp_path: Path, payload: dict[str, Any]) -> Path:
    artifact = tmp_path / "session.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    return artifact


def _resolvable_payload() -> dict[str, Any]:
    payload = session_tool.skeleton()
    payload["baseline_id"] = "no_lookahead_persistence"
    payload["null_model_id"] = "permutation_null"
    payload["falsifier_id"] = "lookahead_leak_falsifier"
    return payload


def test_registry_has_the_three_sections() -> None:
    sections = checker.load_registry(REGISTRY_PATH)
    assert set(sections) == {"baselines", "null_models", "falsifiers"}
    # Every registered entry carries a non-empty description (a stub does not
    # resolve), so the registry cannot pass ids it has not actually described.
    for entries in sections.values():
        assert entries, "each registry section must register at least one reference"
        for entry in entries.values():
            assert isinstance(entry, dict)
            assert isinstance(entry.get("description"), str)
            assert entry["description"].strip()


def test_resolvable_ids_pass(tmp_path: Path) -> None:
    artifact = _write(tmp_path, _resolvable_payload())
    assert checker.check_artifact(artifact, REGISTRY_PATH) == []


def test_skeleton_unset_ids_do_not_resolve(tmp_path: Path) -> None:
    # The --dry-run skeleton's *_unset ids must NOT resolve: a placeholder may
    # not borrow a real reference.
    artifact = _write(tmp_path, session_tool.skeleton())
    errors = checker.check_artifact(artifact, REGISTRY_PATH)
    assert any("baseline_id" in error for error in errors)
    assert any("null_model_id" in error for error in errors)
    assert any("falsifier_id" in error for error in errors)


@pytest.mark.parametrize("field", ["baseline_id", "null_model_id", "falsifier_id"])
def test_unresolvable_single_id_is_rejected(tmp_path: Path, field: str) -> None:
    payload = _resolvable_payload()
    payload[field] = "definitely_not_registered_anywhere"
    artifact = _write(tmp_path, payload)
    errors = checker.check_artifact(artifact, REGISTRY_PATH)
    assert any(field in error and "does not resolve" in error for error in errors)


def test_id_cross_section_does_not_resolve(tmp_path: Path) -> None:
    # A real null-model id placed in the baseline slot must not resolve: ids are
    # section-scoped, not a global bag.
    payload = _resolvable_payload()
    payload["baseline_id"] = "permutation_null"
    artifact = _write(tmp_path, payload)
    errors = checker.check_artifact(artifact, REGISTRY_PATH)
    assert any("baseline_id" in error for error in errors)


def test_stub_entry_without_description_does_not_resolve(tmp_path: Path) -> None:
    # A registry section that lists an id with no description is a stub; resolving
    # against it must fail (the id names a placeholder, not a reference).
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        "schema_version: 1\n"
        "baselines:\n"
        "  stub_baseline: {}\n"
        "null_models:\n"
        "  permutation_null:\n"
        "    description: real null\n"
        "falsifiers:\n"
        "  lookahead_leak_falsifier:\n"
        "    description: real falsifier\n",
        encoding="utf-8",
    )
    payload = _resolvable_payload()
    payload["baseline_id"] = "stub_baseline"
    payload["null_model_id"] = "permutation_null"
    payload["falsifier_id"] = "lookahead_leak_falsifier"
    artifact = _write(tmp_path, payload)
    errors = checker.check_artifact(artifact, registry)
    assert any("baseline_id" in error and "stub" in error for error in errors)


def test_main_exits_nonzero_on_unresolved(tmp_path: Path) -> None:
    artifact = _write(tmp_path, session_tool.skeleton())
    rc = checker.main(["--artifact", str(artifact), "--registry", str(REGISTRY_PATH)])
    assert rc == 1


def test_main_exits_zero_on_resolved(tmp_path: Path) -> None:
    artifact = _write(tmp_path, _resolvable_payload())
    rc = checker.main(["--artifact", str(artifact), "--registry", str(REGISTRY_PATH)])
    assert rc == 0
