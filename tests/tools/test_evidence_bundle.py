# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the WP-09 evidence-bundle assembler.

The keystone is ``test_unearned_tier_is_refused``: a manifest claiming a tier
its evidence tokens do not earn cannot be assembled into a bundle. The bundle is
also content-hashed, so tampering is detected, and the null results come from
the real ``null_baseline`` generator, not a placeholder.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "schemas" / "inference" / "examples" / "context_manifest.example.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "assemble_evidence_bundle", _ROOT / "tools" / "inference" / "assemble_evidence_bundle.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_aeb = _load()


def test_assemble_from_example_is_valid() -> None:
    bundle = _aeb.assemble(_MANIFEST, seed=7, n=512)
    assert _aeb.validate_bundle(bundle) == []
    assert bundle["claim_card"]["tier"] == "MEASURED_SYNTHETIC"
    # null results are real, not a placeholder
    assert bundle["null_results"]["generator"] == "make_gaussian_null"
    assert bundle["null_results"]["n"] == 512


def test_assemble_is_deterministic() -> None:
    a = _aeb.assemble(_MANIFEST, seed=7, n=512)
    b = _aeb.assemble(_MANIFEST, seed=7, n=512)
    assert a["bundle_sha256"] == b["bundle_sha256"]


def test_unearned_tier_is_refused(tmp_path: Path) -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    manifest["claim_tier"] = "REAL_DATA_SINGLE_SESSION"
    p = tmp_path / "hi.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _aeb.assemble(p, seed=7, n=512)
    assert "not earned" in str(exc.value)


def test_tamper_breaks_hash() -> None:
    bundle = _aeb.assemble(_MANIFEST, seed=7, n=512)
    bundle["null_results"]["mean"] = 999.0
    errors = _aeb.validate_bundle(bundle)
    assert any("bundle_sha256 does not match" in e for e in errors)


def test_missing_section_fails() -> None:
    bundle = _aeb.assemble(_MANIFEST, seed=7, n=512)
    del bundle["null_results"]
    errors = _aeb.validate_bundle(bundle)
    assert any("missing required section: null_results" in e for e in errors)


def test_roundtrip_assemble_then_validate() -> None:
    """A freshly assembled bundle re-validates clean (the bundle is generated,
    not committed, to avoid pinning a high-entropy content hash in the tree)."""
    bundle = _aeb.assemble(_MANIFEST, seed=11, n=256)
    assert _aeb.validate_bundle(bundle) == []
    assert bundle["bundle_sha256"]
