# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Preregistration contract tests for ricci_microstructure_v1 (TASK 935).

Proves the empirical research line is formally constrained BEFORE execution:
placeholder/synthetic data cannot promote, every gate (nulls, data hash, replay,
cost model, depth) is required, and the line stays HYPOTHESIS / NOT_RUN / OBSERVE
until real, hash-pinned data exists.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from tools.research.ricci_preregistration_guard import (
    PromotionDecision,
    evaluate_promotion,
)

ROOT = Path(__file__).resolve().parents[2]
PREREG_DOC = ROOT / "docs" / "research" / "ricci_microstructure_v1_PREREGISTRATION.md"
CONFIG_SCHEMA = ROOT / "schemas" / "research" / "ricci_microstructure_v1_config.schema.json"
DATASET_SCHEMA = ROOT / "schemas" / "research" / "ricci_microstructure_v1_dataset.schema.json"
PREREG_DIR = ROOT / "research_lines" / "ricci_microstructure_v1" / "preregistration"
CONFIG_EXAMPLE = PREREG_DIR / "config.example.json"
DATASET_EXAMPLE = PREREG_DIR / "dataset.example.json"
CONTRACT = ROOT / "research_lines" / "ricci_microstructure_v1" / "contract.yaml"

REQUIRED_SECTIONS = (
    "Hypothesis",
    "Forbidden Claims",
    "Dataset Contract",
    "Minimum Data Depth",
    "Observation Window",
    "Null Baselines",
    "Primary Metric",
    "Failure Threshold",
    "Cost Model",
    "Replay Command",
    "Artifact Schema",
    "Promotion Criteria",
    "Rejection Criteria",
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return _load(CONFIG_EXAMPLE)


@pytest.fixture(scope="module")
def dataset() -> dict[str, Any]:
    return _load(DATASET_EXAMPLE)


# --------------------------------------------------------------------------- #
# Preregistration document + schema shape
# --------------------------------------------------------------------------- #
def test_preregistration_doc_has_all_13_sections() -> None:
    text = PREREG_DOC.read_text(encoding="utf-8")
    for i, section in enumerate(REQUIRED_SECTIONS, start=1):
        assert f"## {i}. {section}" in text, f"missing section {i}. {section}"


def test_example_config_and_dataset_are_schema_valid(
    config: dict[str, Any], dataset: dict[str, Any]
) -> None:
    jsonschema.validate(config, _load(CONFIG_SCHEMA))
    jsonschema.validate(dataset, _load(DATASET_SCHEMA))


def test_config_schema_rejects_missing_null_baseline(config: dict[str, Any]) -> None:
    bad = copy.deepcopy(config)
    bad["null_baselines"] = ["permutation_null", "lag_sweep_no_future_data"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, _load(CONFIG_SCHEMA))


def test_config_schema_rejects_missing_cost_model(config: dict[str, Any]) -> None:
    bad = copy.deepcopy(config)
    del bad["cost_model"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, _load(CONFIG_SCHEMA))


def test_config_schema_rejects_missing_replay_command(config: dict[str, Any]) -> None:
    bad = copy.deepcopy(config)
    del bad["replay_command"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, _load(CONFIG_SCHEMA))


def test_dataset_schema_rejects_missing_data_hash(dataset: dict[str, Any]) -> None:
    bad = copy.deepcopy(dataset)
    del bad["data_sha256"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, _load(DATASET_SCHEMA))


# --------------------------------------------------------------------------- #
# Promotion guard — the executable preregistration invariants
# --------------------------------------------------------------------------- #
def test_placeholder_cannot_pass_as_empirical_evidence(
    dataset: dict[str, Any], config: dict[str, Any]
) -> None:
    decision = evaluate_promotion(dataset, config)
    assert isinstance(decision, PromotionDecision)
    assert decision.allowed is False
    assert decision.claim_tier == "HYPOTHESIS"
    assert decision.falsification_status == "NOT_RUN"
    assert decision.decision == "OBSERVE"
    assert any("no real data hash" in r for r in decision.reasons)


def test_synthetic_data_cannot_promote_claim_tier(config: dict[str, Any]) -> None:
    # Real-looking hash but flagged synthetic → still cannot promote.
    synthetic = {"data_sha256": "a" * 64, "is_synthetic": True, "min_data_depth_sec": 7200}
    decision = evaluate_promotion(synthetic, config)
    assert decision.allowed is False
    assert decision.claim_tier == "HYPOTHESIS"
    assert any("synthetic" in r for r in decision.reasons)


def test_missing_null_baseline_blocks_promotion(config: dict[str, Any]) -> None:
    real = {"data_sha256": "b" * 64, "is_synthetic": False, "min_data_depth_sec": 7200}
    bad_config = copy.deepcopy(config)
    bad_config["null_baselines"] = ["permutation_null"]
    decision = evaluate_promotion(real, bad_config)
    assert decision.allowed is False
    assert any("missing null baselines" in r for r in decision.reasons)


def test_missing_replay_command_blocks_promotion(config: dict[str, Any]) -> None:
    real = {"data_sha256": "b" * 64, "is_synthetic": False, "min_data_depth_sec": 7200}
    bad_config = copy.deepcopy(config)
    bad_config["replay_command"] = "  "
    decision = evaluate_promotion(real, bad_config)
    assert decision.allowed is False
    assert any("replay_command" in r for r in decision.reasons)


def test_missing_data_hash_blocks_promotion(config: dict[str, Any]) -> None:
    no_hash = {"is_synthetic": False, "min_data_depth_sec": 7200}
    decision = evaluate_promotion(no_hash, config)
    assert decision.allowed is False
    assert any("no real data hash" in r for r in decision.reasons)


def test_cost_model_failure_blocks_promotion(config: dict[str, Any]) -> None:
    real = {"data_sha256": "b" * 64, "is_synthetic": False, "min_data_depth_sec": 7200}
    result = {"net_pnl_after_costs": -12.5, "oos_ic": 0.04}
    decision = evaluate_promotion(real, config, result)
    assert decision.allowed is False
    assert decision.decision == "REJECT"
    assert decision.falsification_status == "REJECT"
    assert any("negative net-of-cost" in r for r in decision.reasons)


def test_fully_satisfied_real_multi_run_may_promote(config: dict[str, Any]) -> None:
    # Positive control: only an all-real, all-gate-passing run promotes.
    real_config = copy.deepcopy(config)
    real_config["data_source"] = "real_multi"
    real = {"data_sha256": "c" * 64, "is_synthetic": False, "min_data_depth_sec": 7200}
    result = {"net_pnl_after_costs": 42.0, "oos_ic": 0.11}
    decision = evaluate_promotion(real, real_config, result)
    assert decision.allowed is True
    assert decision.claim_tier == "MEASURED"
    assert decision.falsification_status == "PASS"


def test_single_real_session_caps_below_measured(config: dict[str, Any]) -> None:
    # Negative control / promotion blocker for `real_multi_required_for: MEASURED`.
    # A real, all-gate-passing session that is NOT multi-session must clear every
    # falsifier (allowed + PASS) yet stop at TESTED_REAL_SINGLE — MEASURED is
    # reserved for real_multi. Pins the contract's multi-session requirement so a
    # single session can never be silently promoted to MEASURED.
    single_config = copy.deepcopy(config)
    single_config["data_source"] = "real_single"
    real = {"data_sha256": "d" * 64, "is_synthetic": False, "min_data_depth_sec": 7200}
    result = {"net_pnl_after_costs": 42.0, "oos_ic": 0.11}
    decision = evaluate_promotion(real, single_config, result)
    assert decision.allowed is True
    assert decision.falsification_status == "PASS"
    assert decision.claim_tier == "TESTED_REAL_SINGLE"
    assert decision.claim_tier != "MEASURED"


# --------------------------------------------------------------------------- #
# The line itself stays unpromoted until real data exists
# --------------------------------------------------------------------------- #
def test_line_contract_remains_hypothesis_not_run_observe() -> None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert contract["claim"]["tier"] == "HYPOTHESIS"
    assert contract["state"] == "INSTRUMENTED"
    allowed = contract["inference_contract"]["allowed_decisions"]
    assert "OBSERVE" in allowed and "TRADE" not in allowed


def test_committed_dataset_fixture_is_placeholder(dataset: dict[str, Any]) -> None:
    assert dataset["data_sha256"] == "0" * 64
    assert dataset["is_synthetic"] is True
