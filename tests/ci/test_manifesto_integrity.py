# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The manifesto cannot overclaim: every path it cites must exist and hold.

``docs/COMPUTABLE_DISTRUST.md`` states the project's thesis and references real
artifacts, tools, tests and workflows. This gate keeps the manifesto honest —
every backticked repo path must exist, a required set of load-bearing artifacts
must be cited, and the final inference verdict it names must actually be PASS. The
document about the truth-machine is itself truth-gated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFESTO = ROOT / "docs" / "COMPUTABLE_DISTRUST.md"

# Backticked repo paths with a known extension.
_PATH_RE = re.compile(r"`([A-Za-z0-9_][A-Za-z0-9_./\-]*\.(?:json|py|yml|md))`")

# Load-bearing citations the manifesto must keep, or it has drifted from the code.
_REQUIRED = frozenset(
    {
        "artifacts/inference/final_inference_verdict.json",
        "artifacts/inference/no_ungrounded_act.json",
        "artifacts/neuro/opponency_lyapunov.json",
        "artifacts/physics/kuramoto_synchrony.json",
        "artifacts/provenance/inference_provenance.json",
        "tools/audit_final_inference_verdict.py",
        "tools/audit_no_ungrounded_act.py",
    }
)


def _cited_paths() -> set[str]:
    text = MANIFESTO.read_text(encoding="utf-8")
    return {m.group(1) for m in _PATH_RE.finditer(text)}


def test_manifesto_exists() -> None:
    assert MANIFESTO.is_file()


def test_every_cited_path_exists() -> None:
    missing = [p for p in _cited_paths() if not (ROOT / p).exists()]
    assert not missing, f"manifesto cites paths that do not exist: {sorted(missing)}"


def test_required_citations_are_present() -> None:
    missing = _REQUIRED - _cited_paths()
    assert not missing, f"manifesto dropped load-bearing citations: {sorted(missing)}"


def test_named_final_verdict_is_actually_pass() -> None:
    # The manifesto claims release readiness is a computed PASS verdict; verify it.
    verdict = json.loads(
        (ROOT / "artifacts" / "inference" / "final_inference_verdict.json").read_text(
            encoding="utf-8"
        )
    )
    assert verdict["verdict"] == "PASS"


def test_named_apex_is_admissible() -> None:
    apex = json.loads(
        (ROOT / "artifacts" / "inference" / "no_ungrounded_act.json").read_text(encoding="utf-8")
    )
    assert apex["gate"] == "ADMISSIBLE"


def test_boundaries_are_tier_labelled() -> None:
    # A legendary claim without stated boundaries is hype; require the tier labels.
    text = MANIFESTO.read_text(encoding="utf-8")
    for tier in ("[OBSERVED]", "[ADMISSIBLE]", "[EXTRAPOLATED]"):
        assert tier in text, f"manifesto missing epistemic tier label {tier}"
