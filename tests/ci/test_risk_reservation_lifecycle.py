# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The risk reservation-lifecycle artifact must stay bound to real code + tests.

``artifacts/risk/reservation_lifecycle.json`` declares the pending-exposure state
machine RiskManager enforces. This gate keeps the artifact honest: it must be
schema-valid, its component/config-flag/leak-detector must exist in source, and
every invariant must reference a test node that actually exists — so the artifact
cannot claim a closed cap-bypass that the code no longer backs.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "artifacts" / "risk" / "reservation_lifecycle.json"
SCHEMA = ROOT / "audit" / "schema" / "risk_reservation_lifecycle.schema.json"
CORE = ROOT / "execution" / "risk" / "core.py"
OMS = ROOT / "execution" / "oms.py"


def _artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_artifact_validates_against_schema() -> None:
    artifact = _artifact()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert artifact["schema"] == schema["$id"]
    assert artifact["verdict"] == "BOUND"
    assert isinstance(artifact["transitions"], list) and artifact["transitions"]
    assert isinstance(artifact["invariants"], list) and artifact["invariants"]
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(artifact, schema)


def test_transition_states_are_declared() -> None:
    artifact = _artifact()
    states = set(artifact["states"])
    for transition in artifact["transitions"]:
        assert transition["from"] in states, transition
        assert transition["to"] in states, transition


def test_component_flag_and_detector_exist_in_source() -> None:
    artifact = _artifact()
    core_text = CORE.read_text(encoding="utf-8")
    oms_text = OMS.read_text(encoding="utf-8")

    # component: dotted path ending in the RiskManager class name.
    assert "class RiskManager" in core_text
    # leak detector method.
    detector = artifact["leak_detector"].split(".")[-1]
    assert f"def {detector}" in core_text, detector
    # config flag lives on OMSConfig.
    flag = artifact["config_flag"].split(".")[-1]
    assert f"{flag}:" in oms_text, flag
    # default_enabled must match the source default.
    assert artifact["default_enabled"] is False
    assert f"{flag}: bool = False" in oms_text


def test_every_invariant_and_test_node_exists() -> None:
    artifact = _artifact()
    nodes = [inv["test"] for inv in artifact["invariants"]]
    for file_ref in artifact["tests"]:
        assert (ROOT / file_ref).is_file(), f"missing test file: {file_ref}"
    for node in nodes:
        file_part, _, func = node.partition("::")
        func_name = func.split("::")[-1]
        path = ROOT / file_part
        assert path.is_file(), f"invariant references missing test file: {file_part}"
        text = path.read_text(encoding="utf-8")
        assert f"def {func_name}" in text, (
            f"invariant references missing test {func_name!r} in {file_part}"
        )


def test_bypass_and_leak_invariants_are_present() -> None:
    ids = {inv["id"] for inv in _artifact()["invariants"]}
    # The two load-bearing claims: cap check includes pending, and no OMS leak.
    assert {"RESV-1", "RESV-9", "RESV-10"} <= ids
