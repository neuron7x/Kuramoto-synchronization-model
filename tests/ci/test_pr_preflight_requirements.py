# SPDX-License-Identifier: MIT
"""Requirements traceability gate for the PR preflight runner.

Keeps tools/ci/pr_preflight_requirements.json honest: every MUST requirement is
well-formed, and every linked code path and linked test resolves to a real file
and (for tests) a real test function. Decorative traceability that points at
deleted or renamed tests fails here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "tools" / "ci" / "pr_preflight_requirements.json"

_REQUIRED_IDS = {f"REQ-PREFLIGHT-{n:03d}" for n in range(1, 11)}
_VERIFICATION_METHODS = {"unit_test", "behavioral_test", "schema_test", "shell_test"}
_FAILURE_STATUSES = {"FAIL", "BLOCKED"}


def _requirements() -> list[dict[str, Any]]:
    return json.loads(REQUIREMENTS.read_text(encoding="utf-8"))["requirements"]


def test_requirements_file_is_well_formed() -> None:
    reqs = _requirements()
    ids = {r["id"] for r in reqs}
    assert _REQUIRED_IDS <= ids, f"missing required ids: {sorted(_REQUIRED_IDS - ids)}"
    for r in reqs:
        assert r["priority"] == "MUST"
        assert r["statement"].strip()
        assert r["verification_method"] in _VERIFICATION_METHODS
        assert r["failure_status"] in _FAILURE_STATUSES
        assert r["acceptance_criteria"], f"{r['id']} has no acceptance criteria"
        assert r["linked_tests"], f"{r['id']} has no linked tests"
        assert r["linked_code"], f"{r['id']} has no linked code"


def test_linked_code_paths_exist() -> None:
    for r in _requirements():
        for ref in r["linked_code"]:
            path = ref.split("::", 1)[0]
            assert (ROOT / path).exists(), f"{r['id']} links missing code: {path}"


def test_linked_tests_resolve_to_real_functions() -> None:
    for r in _requirements():
        for ref in r["linked_tests"]:
            assert "::" in ref, f"{r['id']} linked test must be file::function: {ref}"
            path, func = ref.split("::", 1)
            test_file = ROOT / path
            assert test_file.exists(), f"{r['id']} links missing test file: {path}"
            source = test_file.read_text(encoding="utf-8")
            assert f"def {func}(" in source, f"{r['id']} links missing test: {ref}"
