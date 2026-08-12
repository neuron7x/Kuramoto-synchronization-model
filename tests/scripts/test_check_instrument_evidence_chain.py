# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Instrument evidence-chain gate — behavioural / self-falsification proof.

``scripts/ci/check_instrument_evidence_chain.py`` must (1) PASS on the real
``governance/INSTRUMENTS.yaml`` as shipped, and FAIL CLOSED when ANY single
link in an instrument's evidence chain dangles: a moved module, a drifted
source hash, a non-existent merge commit, a commit that did not touch the
module, a missing test file, an acceptor that does not bind the module, a
missing claim boundary, a falsifier node pytest cannot collect, or missing
provenance evidence. A gate that only string-matches would pass several of
these; the live ``pytest --collect-only`` link is what gives it teeth.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "ci" / "check_instrument_evidence_chain.py"
REGISTRY_PATH = ROOT / "governance" / "INSTRUMENTS.yaml"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_instrument_evidence_chain", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_instrument_evidence_chain"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    return _load_module()


@pytest.fixture(scope="module")
def live_registry() -> dict[str, Any]:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _valid_instrument(live_registry: dict[str, Any], iid: str = "null-baseline") -> dict[str, Any]:
    for inst in live_registry["instruments"]:
        if inst["id"] == iid:
            # deep-ish copy so per-test mutation does not bleed across tests
            return {**inst, "falsifiers": list(inst["falsifiers"])}
    raise AssertionError(f"{iid} not in live registry")


def _write_registry(
    tmp_path: Path,
    instruments: list[dict[str, Any]],
    *,
    boundary: str = "descriptor_only_not_predictor",
) -> Path:
    reg = {"schema_version": 1, "claim_boundary_required": boundary, "instruments": instruments}
    p = tmp_path / "INSTRUMENTS.yaml"
    p.write_text(yaml.safe_dump(reg, sort_keys=False), encoding="utf-8")
    return p


def _run(gate: Any, registry_path: Path, *, skip_collect: bool = True) -> int:
    argv = ["--registry", str(registry_path)]
    if skip_collect:
        argv.append("--skip-collect")
    return gate.main(argv)


# --------------------------------------------------------------------------
# Positive: the shipped registry resolves.
# --------------------------------------------------------------------------


def test_live_registry_passes_static_links(gate: Any) -> None:
    # Links 1-6, 8 against the real registry (fast, no pytest collection).
    assert _run(gate, REGISTRY_PATH, skip_collect=True) == 0


def test_live_registry_passes_with_live_collection(
    gate: Any, live_registry: dict[str, Any], tmp_path: Path
) -> None:
    # The full chain INCLUDING live pytest --collect-only for one instrument.
    reg = _write_registry(tmp_path, [_valid_instrument(live_registry, "null-baseline")])
    assert _run(gate, reg, skip_collect=False) == 0


def test_collect_output_accepts_parametrized_instances(gate: Any) -> None:
    node = "tests/unit/analytics/test_descriptor_capsule.py::test_fail_closed_on_bad_config"
    output = f"{node}[bad0]\n{node}[bad1]\n"
    assert gate._collect_output_has_node(node, output) is True


def test_collect_nonzero_after_exact_node_resolution_is_not_dangling(
    gate: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = "tests/unit/analytics/test_null_baseline.py::test_gaussian_deterministic_for_same_seed"

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pytest"],
            returncode=139,
            stdout=f"{node}\n",
            stderr="Fatal Python error: Segmentation fault\nExtension modules: numpy._core\n",
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate._node_is_collectable(node) == (True, "collectable")


def test_native_collect_crash_uses_source_backed_fallback(
    gate: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = "tests/unit/analytics/test_null_baseline.py::test_gaussian_deterministic_for_same_seed"

    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pytest"],
            returncode=-11,
            stdout="",
            stderr="Fatal Python error: Segmentation fault\nExtension modules: numpy._core\n",
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate._node_is_collectable(node) == (
        True,
        "collectable via source-backed fallback after native collect crash",
    )


# --------------------------------------------------------------------------
# Negative: every single dangling link must flip the verdict to FAIL.
# --------------------------------------------------------------------------


def test_source_drift_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["source_sha256"] = "0" * 64
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_missing_module_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["module"] = "analytics/signals/does_not_exist.py"
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_unknown_merge_commit_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["merge_commit"] = "0123456789abcdef0123456789abcdef01234567"  # pragma: allowlist secret
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_commit_not_touching_module_fails(
    gate: Any, live_registry: dict[str, Any], tmp_path: Path
) -> None:
    # A real, existing commit that did NOT touch null_baseline.py:
    # borrow another instrument's merge commit.
    inst = _valid_instrument(live_registry, "null-baseline")
    other = _valid_instrument(live_registry, "descriptor-metadata")
    inst["merge_commit"] = other["merge_commit"]
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_missing_test_file_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["test_file"] = "tests/unit/analytics/test_nope.py"
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_acceptor_not_binding_module_fails(
    gate: Any, live_registry: dict[str, Any], tmp_path: Path
) -> None:
    inst = _valid_instrument(live_registry, "null-baseline")
    other = _valid_instrument(live_registry, "descriptor-metadata")
    inst["acceptor"] = other["acceptor"]  # exists but binds a different module
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_wrong_claim_boundary_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["claim_boundary"] = "predictive_alpha_signal"
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_uncollectable_falsifier_node_fails(
    gate: Any, live_registry: dict[str, Any], tmp_path: Path
) -> None:
    # THE teeth: real file, nonexistent test function. A string-only gate
    # would pass this. Live pytest --collect-only must reject it.
    inst = _valid_instrument(live_registry)
    inst["falsifiers"] = ["tests/unit/analytics/test_null_baseline.py::test_this_node_does_not_exist"]
    assert _run(gate, _write_registry(tmp_path, [inst]), skip_collect=False) == 1


def test_falsifier_file_missing_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["falsifiers"] = ["tests/unit/analytics/test_absent.py::test_x"]
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_malformed_node_fails(gate: Any, live_registry: dict[str, Any], tmp_path: Path) -> None:
    inst = _valid_instrument(live_registry)
    inst["falsifiers"] = ["not_a_valid_node_id"]
    assert _run(gate, _write_registry(tmp_path, [inst])) == 1


def test_missing_registry_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, tmp_path / "absent.yaml") == 2


def test_empty_instruments_returns_2(gate: Any, tmp_path: Path) -> None:
    assert _run(gate, _write_registry(tmp_path, [])) == 2
