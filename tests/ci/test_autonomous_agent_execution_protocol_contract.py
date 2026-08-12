# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Surface-contract test for the Autonomous Agent Execution Protocol.

Manifest-driven (``docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.contract.json``):
the protocol document must carry every required section (number-agnostic heading
regex), governance link, normative clause, perturbation axis, PR-disclosure
field, and verb the contract pins. This is the falsifier for the governance
contract: deleting or weakening any required clause in the document, or dropping
a perturbation axis / disclosure field, makes this test fail closed — exactly
the drift the protocol forbids.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_DOC_REL = "docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.md"
_CONTRACT_REL = "docs/governance/AUTONOMOUS_AGENT_EXECUTION_PROTOCOL.contract.json"
_CONTRACT = json.loads((ROOT / _CONTRACT_REL).read_text(encoding="utf-8"))


def _doc() -> str:
    return (ROOT / _DOC_REL).read_text(encoding="utf-8")


def test_protocol_and_contract_files_exist() -> None:
    assert (ROOT / _DOC_REL).is_file(), f"missing protocol doc: {_DOC_REL}"
    assert (ROOT / _CONTRACT_REL).is_file(), f"missing contract: {_CONTRACT_REL}"


def test_contract_source_points_at_protocol_doc() -> None:
    assert _CONTRACT["source"] == _DOC_REL


def test_protocol_declares_every_required_section() -> None:
    doc = _doc()
    for section in _CONTRACT["required_sections"]:
        assert re.search(section["heading_regex"], doc, re.MULTILINE), (
            f"missing required section {section['id']} "
            f"(regex {section['heading_regex']!r})"
        )


def test_protocol_links_governance_authority_files() -> None:
    doc = _doc()
    for link in _CONTRACT["required_links"]:
        assert link in doc, f"missing required governance link: {link}"


def test_protocol_declares_every_required_clause() -> None:
    doc = _doc()
    for clause in _CONTRACT["required_clauses"]:
        assert clause in doc, f"missing required normative clause: {clause!r}"


def test_protocol_declares_every_perturbation_axis() -> None:
    doc = _doc()
    for axis in _CONTRACT["required_perturbation_axes"]:
        assert axis in doc, f"missing required perturbation axis: {axis!r}"


def test_protocol_declares_every_pr_disclosure_field() -> None:
    doc = _doc()
    for field_name in _CONTRACT["required_pr_disclosure_fields"]:
        assert field_name in doc, f"missing required PR-disclosure field: {field_name!r}"


def test_protocol_uses_required_verbs() -> None:
    doc = _doc()
    for verb in _CONTRACT["required_verbs"]:
        assert verb in doc, f"missing required verb: {verb!r}"


def test_protocol_forbids_direct_main_push_and_self_merge() -> None:
    doc = _doc()
    assert "MUST NOT  push directly to main" in doc
    assert "MUST NOT  merge a pull request" in doc
    assert "Merge authority is owner-only" in doc


def test_protocol_mandates_perturbation_over_green_tests() -> None:
    doc = _doc()
    assert "MUST NOT  present a result as ready on green tests alone." in doc
