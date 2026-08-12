# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""N6 — Kuramoto synchronisation certificate (second-domain transfer, real engine).

Defect-sensitive: strong coupling locks, weak coupling stays incoherent, and a
phase-transition gap separates them. Negative control: at weak coupling the steady
order parameter is strictly below the locked one — if the engine stopped
synchronising, the gap collapses and the certificate flips to INCOHERENT.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_kuramoto_synchrony.py"
ARTIFACT = ROOT / "artifacts" / "physics" / "kuramoto_synchrony.json"
SCHEMA = ROOT / "audit" / "schema" / "kuramoto_synchrony.schema.json"


def _load_tool():
    spec = importlib.util.spec_from_file_location("kura", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ks = _load_tool()


def test_certificate_is_synchronising() -> None:
    report = ks.build_certificate()
    assert report["gate"] == "SYNCHRONISING"
    assert report["verdict"] == "PASS"
    assert all(c["holds"] for c in report["checks"])


def test_strong_coupling_locks_weak_stays_incoherent() -> None:
    assert ks.r_steady(5.0) >= ks._R_LOCK
    assert ks.r_steady(0.05) < ks._R_INCOHERENT


def test_phase_transition_gap_exists() -> None:
    gap = ks.r_steady(5.0) - ks.r_steady(0.05)
    assert gap >= ks._TRANSITION_GAP  # a real transition, not a flat plateau


def test_order_parameter_is_bounded() -> None:
    assert ks.order_parameter_bounded(5.0) is True


def test_engine_is_deterministic_under_seed() -> None:
    assert ks.r_steady(1.0) == ks.r_steady(1.0)


def test_exit_code_enforces_incoherent() -> None:
    assert ks.exit_code({"verdict": "PASS"}, report_only=False) == 0
    assert ks.exit_code({"verdict": "FAIL"}, report_only=False) == 1
    assert ks.exit_code({"verdict": "FAIL"}, report_only=True) == 0


def test_committed_certificate_is_schema_valid() -> None:
    report = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert report["schema"] == ks.SCHEMA_ID
    assert report["gate"] == "SYNCHRONISING"
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(report, json.loads(SCHEMA.read_text(encoding="utf-8")))
