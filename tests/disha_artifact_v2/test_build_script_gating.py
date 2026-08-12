# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G15, G16 — build script still passes existing tests AND consumes the
gating layer (it imports + calls emit_verdict before producing artefacts)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "build_disha_ba_correlation_figures.py"


def test_build_script_imports_emit_verdict() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "from instrument_validation.verdict import" in text
    assert "emit_verdict" in text
    assert "country_aggregate_default_scope" in text


def test_build_script_calls_emit_verdict_before_artefact_writes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    emit_idx = text.find("emit_verdict(")
    write_idx = text.find(".to_csv(")
    assert emit_idx > 0
    assert write_idx > emit_idx, "emit_verdict must be invoked before any artefact CSV is written"


def test_build_script_does_not_import_x9r() -> None:
    """Spec: do not touch X-9R."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "from research.systemic_risk.protocol_x9r" not in text
    assert "import research.systemic_risk.protocol_x9r" not in text
