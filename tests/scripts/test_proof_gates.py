# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioural proofs for the executable proof gates (E/G/H/K/M/Q + firewall).

These tests are the self-falsification of the proof-gate machinery itself:
each gate must (1) survive its own controls, (2) fail closed on corruption,
(3) stay deterministic, and (4) keep the claim firewall sharp — it must still
*fire* on a real claim, not just pass on shipped prose. The clean-clone wheel
build is exercised separately (it is heavy); here we assert its fast-lane
contract and the artifact-aware interpretation in release_gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import (
    benchmark_spine,
    execution_contract,
    falsification_ledger,
    real_data_probe,
    replication_packet,
)

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# H. falsification ledger
# --------------------------------------------------------------------------
def test_falsification_all_controls_survive() -> None:
    payload = falsification_ledger.run()
    assert payload["promotion_allowed"] is True
    assert len(payload["controls"]) == 8
    for c in payload["controls"]:
        assert c["verdict"] == "SURVIVED", f"{c['name']}: {c['failure_mode']}"


def test_falsification_every_control_is_hash_addressable() -> None:
    payload = falsification_ledger.run()
    for c in payload["controls"]:
        assert c["command"].startswith("python -m scripts.ci.falsification_ledger")
        assert len(c["input_sha256"]) == 64
        assert len(c["output_sha256"]) == 64
        assert c["verdict"] in {"SURVIVED", "REFUTED", "BLOCKED"}


def test_falsification_is_deterministic() -> None:
    a = falsification_ledger.run()
    b = falsification_ledger.run()
    ha = {c["name"]: c["output_sha256"] for c in a["controls"]}
    hb = {c["name"]: c["output_sha256"] for c in b["controls"]}
    assert ha == hb


# --------------------------------------------------------------------------
# G. real-data manifest schema — fail closed
# --------------------------------------------------------------------------
def _valid_manifest() -> dict[str, Any]:
    return {
        "artifact_id": "demo",
        "venue": "DEMO",
        "symbol": "X",
        "time_start_utc": "2026-01-01T00:00:00Z",
        "time_end_utc": "2026-01-02T00:00:00Z",
        "git_sha": "0" * 40,
        "git_dirty": False,
        "config_sha256": "a" * 64,
        "data_sha256": "b" * 64,
        "data_bytes": 1024,
        "schema_version": "1.0",
        "license_provenance": "public-domain",
        "replay_command": "python -m geosync.replay demo",
        "status": "MEASURED_SINGLE",
    }


def test_real_data_valid_manifest_accepted() -> None:
    assert real_data_probe.validate_manifest(_valid_manifest()) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.update(data_bytes=0),
        lambda m: m.update(data_sha256=""),
        lambda m: m.update(replay_command=""),
        lambda m: m.update(license_provenance=""),
        lambda m: m.update(git_dirty=True),  # dirty cannot support signoff tier
        lambda m: m.pop("data_sha256"),
        lambda m: m.update(status="MEASURED_MULTI"),  # needs ≥2 independent sessions
    ],
)
def test_real_data_corruption_rejected(mutate: Any) -> None:
    m = _valid_manifest()
    mutate(m)
    assert real_data_probe.validate_manifest(m), "corruption must be rejected"


def test_real_data_probe_is_blocked_without_real_data() -> None:
    # The repository ships only synthetic single-session fixtures.
    payload = real_data_probe.run()
    assert payload["status"] == "BLOCKED"
    assert payload["blocker"]


# --------------------------------------------------------------------------
# K. execution out-of-scope contract
# --------------------------------------------------------------------------
def test_execution_contract_out_of_scope_and_enforced() -> None:
    payload = execution_contract.run()
    assert payload["scope"] == "OUT_OF_SCOPE"
    assert payload["status"] == "PASS"
    assert payload["claim_boundary_enforced"] is True
    assert set(execution_contract.EXCLUDED_DIMENSIONS) >= {"slippage", "fees", "latency"}


# --------------------------------------------------------------------------
# M. benchmark determinism
# --------------------------------------------------------------------------
def test_benchmark_kernel_is_deterministic() -> None:
    _, _, h1 = benchmark_spine._bench_kuramoto_order()
    _, _, h2 = benchmark_spine._bench_kuramoto_order()
    assert h1 == h2
    payload = benchmark_spine._measure()
    case = payload["cases"]["kuramoto_order_N2048"]
    assert case["deterministic"] is True
    assert payload["hardware_id"]


# --------------------------------------------------------------------------
# Q. replication projections are deterministic and hash-locked
# --------------------------------------------------------------------------
def test_replication_projection_is_deterministic() -> None:
    fp1, _ = replication_packet._fingerprints()
    fp2, _ = replication_packet._fingerprints()
    assert fp1 == fp2
    # every projected gate produces a 64-char fingerprint when its artifact exists
    for _gate, fp in fp1.items():
        assert len(fp) == 64


# --------------------------------------------------------------------------
# VII. claim firewall must still FIRE (not neutered by the hardening)
# --------------------------------------------------------------------------
def _load_claim_boundary() -> Any:
    path = ROOT / "scripts" / "ci" / "check_claim_boundary.py"
    spec = importlib.util.spec_from_file_location("check_claim_boundary_pg", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_claim_boundary_pg"] = module
    spec.loader.exec_module(module)
    return module


def test_firewall_fires_on_real_strong_claim() -> None:
    mod = _load_claim_boundary()
    # An assertive, non-disclaimed product claim must match a strong pattern.
    line = mod._normalise("Our model is a proven alpha with guaranteed profit.")
    assert not mod._DISCLAIMER_MARKERS.search(line)
    assert any(p.search(line) for p, _ in mod._STRONG_COMPILED)


def test_firewall_escapes_disclaimer_and_edge_case() -> None:
    mod = _load_claim_boundary()
    for text in (
        "GeoSync does not claim a profitable strategy.",
        "Tested and validated edge cases:",
        "production trading is outside this stack",
    ):
        line = mod._normalise(text)
        assert mod._DISCLAIMER_MARKERS.search(line), text


def test_claim_status_enum_rejects_unknown_token() -> None:
    mod = _load_claim_boundary()
    m = mod._CLAIM_STATUS_RE.search("claim_status: MEASURED_SINGLE")
    assert m and m.group(1).upper() in mod.CLAIM_STATUS_ENUM
    bad = mod._CLAIM_STATUS_RE.search("claim_status: TOTALLY_PROVEN")
    assert bad and bad.group(1).upper() not in mod.CLAIM_STATUS_ENUM
    # a domain analysis field must NOT be governed by the tier enum
    assert mod._CLAIM_STATUS_RE.search("ba_claim_status = NOT_DISTINGUISHED") is None


# --------------------------------------------------------------------------
# release_gate artifact-aware probes — fast lane is MANUAL (cannot cheat)
# --------------------------------------------------------------------------
def _load_release_gate() -> Any:
    path = ROOT / "scripts" / "ci" / "release_gate.py"
    spec = importlib.util.spec_from_file_location("release_gate_pg", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_gate_pg"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "probe_name",
    [
        "probe_e_clean_clone",
        "probe_g_real_data",
        "probe_h_falsification",
        "probe_k_execution",
        "probe_m_benchmarks",
        "probe_q_replication",
    ],
)
def test_proof_probes_fast_lane_is_manual(probe_name: str) -> None:
    mod = _load_release_gate()
    status, evidence = getattr(mod, probe_name)(False)
    assert status == mod.MANUAL
    assert "requires --deep" in evidence


def test_proof_probes_g_is_red_in_deep() -> None:
    # G must be RED (BLOCKED) under --deep until real data is staged — this is
    # the honest fail-closed contract, and the gate must not silently pass it.
    mod = _load_release_gate()
    status, _ = mod.probe_g_real_data(True)
    assert status == mod.RED
