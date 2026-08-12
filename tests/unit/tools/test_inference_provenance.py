# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reproducibility: every tool-generated inference artifact rebuilds byte-identical.

Heavy (imports the generator tools). A verdict you cannot reproduce from source is
not a verdict. Negative control: mutating a pinned artifact changes the
provenance_root — tampering is detectable.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "tools" / "audit_inference_provenance.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("prov", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


prov = _load_tool()


def test_provenance_is_pass_and_all_generated_artifacts_reproducible() -> None:
    report = prov.build_provenance(ROOT)
    assert report["verdict"] == "PASS"
    generated = [r for r in report["artifacts"] if r["reproducible"] is not None]
    assert generated and all(r["reproducible"] for r in generated)


def test_committed_manifest_root_is_reproducible() -> None:
    committed = json.loads(
        (ROOT / "artifacts" / "provenance" / "inference_provenance.json").read_text()
    )
    recomputed = prov.build_provenance(ROOT)
    assert recomputed["provenance_root"] == committed["provenance_root"]


def test_tampering_changes_the_root(tmp_path) -> None:
    # Build once, mutate a pinned artifact's bytes, rebuild -> root must differ.
    import shutil

    shutil.copytree(ROOT / "artifacts", tmp_path / "artifacts")
    shutil.copytree(ROOT / "tools", tmp_path / "tools")
    baseline = prov.build_provenance(tmp_path)["provenance_root"]
    victim = tmp_path / "artifacts" / "state" / "mutable_state_registry.json"
    data = json.loads(victim.read_text())
    data["verdict"] = "UNBOUND"  # tamper
    victim.write_text(json.dumps(data))
    tampered = prov.build_provenance(tmp_path)["provenance_root"]
    assert tampered != baseline
