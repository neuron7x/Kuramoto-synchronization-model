# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression: unquoted `runtime_path: YES` must not defeat the
DECORATIVE-on-runtime quarantine gate.

YAML coerces an unquoted ``YES`` to Python ``True`` (``NO`` -> ``False``). Before
the fix, ``integrity_errors`` compared ``runtime == "YES"`` which is ``False``
for the boolean ``True``, so a DECORATIVE entry on a runtime path escaped the
quarantine requirement. The fix normalizes the boolean back to the canonical
string before the comparison.
"""

from __future__ import annotations

import yaml

from scripts.ci.check_evidence_integrity import integrity_errors

KNOWN = {"INV-K1"}


def test_unquoted_yes_coerces_to_bool_true() -> None:
    # Guards the premise: unquoted YES really becomes Python True in YAML.
    parsed = yaml.safe_load("runtime_path: YES\n")
    assert parsed["runtime_path"] is True


def test_decorative_runtime_bool_true_without_quarantine_is_rejected() -> None:
    entry: dict[str, object] = {
        "id": "deco-bool",
        "classification": "DECORATIVE",
        "inv_refs": [],
        "existing_tests": [],
        "falsifier": "non-claim: pure label.",
        "runtime_path": True,  # what unquoted `YES` deserializes to
        "remediation_action": "KEEP",  # NOT a quarantine action
        "reason": "z",
    }
    errs = integrity_errors({"entries": [entry]}, KNOWN)
    assert any("must be quarantined" in e for e in errs), errs


def test_decorative_runtime_bool_false_is_ignored() -> None:
    # `runtime_path: NO` (-> False) is off the runtime path: gate must not fire.
    entry: dict[str, object] = {
        "id": "deco-nonrt",
        "classification": "DECORATIVE",
        "inv_refs": [],
        "existing_tests": [],
        "falsifier": "label",
        "runtime_path": False,
        "remediation_action": "KEEP",
        "reason": "z",
    }
    assert integrity_errors({"entries": [entry]}, KNOWN) == []
