# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the integrated descriptor replay capsule (Task 5).

Asserts the one-command pipeline is deterministic (byte-identical manifest +
manifest_digest for equal config), carries every stage (null baseline,
quantization, null comparison, information quality, metadata) plus the
observed-vs-null rank and the claim-safe disclaimers, and fails closed on a
malformed config.
"""

from __future__ import annotations

import json
import subprocess
import os
import sys
from pathlib import Path

import pytest

from analytics.signals.descriptor_capsule import build_capsule

BASE_CONFIG = {
    "observed": [0.1, -0.2, 0.4, 0.9, -1.3, 0.05, 0.6, -0.7],
    "thresholds": [-0.5, 0.5],
    "labels": ["low", "mid", "high"],
    "null_seed": 42,
    "null_n": 2000,
}


def test_manifest_is_deterministic() -> None:
    a = build_capsule(BASE_CONFIG)
    b = build_capsule(dict(BASE_CONFIG))
    assert a == b
    assert a["manifest_digest"] == b["manifest_digest"]


def test_manifest_digest_changes_with_seed() -> None:
    a = build_capsule(BASE_CONFIG)
    b = build_capsule({**BASE_CONFIG, "null_seed": 43})
    assert a["manifest_digest"] != b["manifest_digest"]


def test_manifest_carries_all_stages() -> None:
    m = build_capsule(BASE_CONFIG)
    stages = m["stages"]
    assert set(stages) == {
        "null_baseline",
        "quantization",
        "null_comparison",
        "information_quality",
    }
    assert "observed_digest" in stages["quantization"]
    assert 0 <= stages["null_comparison"]["rank"]
    assert 0.0 <= stages["null_comparison"]["percentile"] <= 100.0
    assert 0.0 <= stages["information_quality"]["normalized_entropy"] <= 1.0
    assert 0.0 <= stages["information_quality"]["js_divergence_bits"] <= 1.0 + 1e-9


def test_manifest_is_claim_safe() -> None:
    m = build_capsule(BASE_CONFIG)
    assert m["claim_boundary"] == "descriptor_only_not_predictor"
    assert m["not_predictive_claim"] and m["not_financial_advice"] and m["research_only"]
    assert m["metadata"]["claim_boundary"] == "descriptor_only_not_predictor"
    assert m["stages"]["information_quality"]["claim_boundary"] == "descriptor_only_not_predictor"


def test_config_hash_is_stable_and_distinct() -> None:
    a = build_capsule(BASE_CONFIG)
    b = build_capsule({**BASE_CONFIG, "observed": [*BASE_CONFIG["observed"], 0.33]})
    assert a["config_hash"] != b["config_hash"]
    assert a["config_hash"] == build_capsule(dict(BASE_CONFIG))["config_hash"]


@pytest.mark.parametrize(
    "bad",
    [
        {"thresholds": [-0.5, 0.5], "labels": ["low", "mid", "high"], "null_seed": 1},  # no observed
        {**BASE_CONFIG, "observed": []},  # empty observed
        {**BASE_CONFIG, "null_n": 0},  # degenerate null length
        {**BASE_CONFIG, "labels": ["only_one"]},  # labels/thresholds mismatch (quantize fail-closed)
    ],
)
def test_fail_closed_on_bad_config(bad: dict) -> None:
    with pytest.raises(ValueError):
        build_capsule(bad)


def test_cli_smoke(tmp_path: Path) -> None:
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps(BASE_CONFIG), encoding="utf-8")
    # The repo is not editable-installed in CI; pytest's rootdir puts the repo on
    # this process's sys.path but that does NOT propagate to a child process. Pass
    # the repo root via PYTHONPATH so the subprocess can import `analytics`
    # regardless of install mode (this is what made #1171 a CI-only failure).
    repo_root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(repo_root) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    proc = subprocess.run(
        [sys.executable, "scripts/run_descriptor_capsule.py", "--config-file", str(cfg)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["manifest_digest"] == build_capsule(BASE_CONFIG)["manifest_digest"]
