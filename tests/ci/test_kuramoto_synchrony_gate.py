# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The Kuramoto synchronisation certificate must stay schema-valid and locked.

Lightweight (json + pathlib only) so it collects in the minimal repo-integrity
env; the heavy engine verification lives in tests/unit/physics.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CERT = ROOT / "artifacts" / "physics" / "kuramoto_synchrony.json"
SCHEMA = ROOT / "audit" / "schema" / "kuramoto_synchrony.schema.json"


def _cert() -> dict:
    return json.loads(CERT.read_text(encoding="utf-8"))


def test_certificate_validates_against_schema() -> None:
    cert = _cert()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert cert["schema"] == schema["$id"]
    assert len(cert["checks"]) >= 5
    try:
        import jsonschema
    except ImportError:
        return
    jsonschema.validate(cert, schema)


def test_certificate_is_synchronising() -> None:
    cert = _cert()
    assert cert["gate"] == "SYNCHRONISING" and cert["verdict"] == "PASS"
    assert all(c["holds"] for c in cert["checks"])
    assert cert["r_steady_high"] - cert["r_steady_low"] >= 0.5  # transition gap
