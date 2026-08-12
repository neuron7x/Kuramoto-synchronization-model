# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The opponency Lyapunov certificate must stay schema-valid and STABLE.

Lightweight (json + pathlib only) so it collects in the minimal repo-integrity
env. The heavy numeric verification lives in tests/unit/neuro.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CERT = ROOT / "artifacts" / "neuro" / "opponency_lyapunov.json"
SCHEMA = ROOT / "audit" / "schema" / "opponency_lyapunov.schema.json"


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


def test_certificate_is_stable_and_hurwitz() -> None:
    cert = _cert()
    assert cert["gate"] == "STABLE" and cert["verdict"] == "PASS"
    assert all(c["holds"] for c in cert["checks"])
    assert all(ev < 0.0 for ev in cert["eigenvalues_real"])  # Hurwitz
