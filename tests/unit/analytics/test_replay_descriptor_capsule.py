# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the public descriptor replay command surface.

Covers the replay contract properties: manifest-digest determinism for an
identical config, config_hash stability and sensitivity, fail-closed
rejection of malformed configs, presence and correctness of the
claim-boundary fields, byte-stable output digests, the CLI surface via
``main()`` and via a subprocess smoke test, and the absence of any
forecasting / trading / predictive language on the public surface.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.replay_descriptor_capsule import (
    CLAIM_BOUNDARY,
    SUPPORTED_METHODS,
    ReplayConfigError,
    main,
    replay,
)

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "replay_descriptor_capsule.py"


def _fixed_config() -> dict[str, Any]:
    """A canonical fixed-threshold replay config used across tests."""
    return {
        "method": "fixed_threshold",
        "values": [-2.0, 0.0, 0.4, float("nan")],
        "thresholds": [-0.5, 0.5],
        "labels": ["low", "neutral", "high"],
    }


def _gaussian_config() -> dict[str, Any]:
    """A canonical seeded gaussian_null replay config."""
    return {"method": "gaussian_null", "n": 16, "seed": 7}


def test_manifest_digest_is_deterministic() -> None:
    """The same config must yield a byte-identical manifest digest."""
    a = replay(_fixed_config())
    b = replay(_fixed_config())
    assert a["manifest_digest"] == b["manifest_digest"]
    assert a == b


def test_seeded_null_replay_is_deterministic() -> None:
    """A seeded null replay reproduces the identical manifest digest."""
    a = replay(_gaussian_config())
    b = replay(_gaussian_config())
    assert a["manifest_digest"] == b["manifest_digest"]
    assert a["method"] == "gaussian_null"
    assert a["input_count"] == 16


def test_config_hash_is_stable_and_sensitive() -> None:
    """config_hash is stable for the same config and changes when it changes."""
    base = replay(_fixed_config())
    same = replay(_fixed_config())
    assert base["config_hash"] == same["config_hash"]

    perturbed = _fixed_config()
    perturbed["thresholds"] = [-0.4, 0.5]
    other = replay(perturbed)
    assert other["config_hash"] != base["config_hash"]
    assert other["manifest_digest"] != base["manifest_digest"]


def test_claim_boundary_fields_present_and_correct() -> None:
    """Every manifest must carry the descriptor-only boundary fields."""
    for cfg in (_fixed_config(), _gaussian_config()):
        manifest = replay(cfg)
        assert manifest["claim_boundary"] == CLAIM_BOUNDARY == "descriptor_only_not_predictor"
        assert manifest["not_predictive_claim"] is True
        assert manifest["not_financial_advice"] is True
        assert manifest["research_only"] is True


def test_output_digest_matches_recomputed_digest() -> None:
    """output_digest must be the sha256 over the canonical descriptor output."""
    import hashlib

    manifest = replay(_fixed_config())
    canonical = json.dumps(manifest["output"], sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert manifest["output_digest"] == expected


@pytest.mark.parametrize(
    "bad_config",
    [
        {"method": "fixed_threshold", "values": [1.0]},  # missing thresholds/labels
        {"method": "gaussian_null", "n": 0, "seed": 1},  # n<=0 fails closed downstream
        {"method": "gaussian_null", "n": 4, "seed": -1},  # negative seed fails closed
        {"method": "does_not_exist", "values": []},  # unsupported method
        {"values": [1.0]},  # missing method key
        {
            "method": "fixed_threshold",
            "values": [1.0],
            "thresholds": [0.5, 0.5],
            "labels": ["a", "b"],
        },  # non-increasing thresholds rejected by quantize_states
    ],
)
def test_malformed_config_fails_closed(bad_config: dict[str, Any]) -> None:
    """A malformed config must raise ReplayConfigError, never emit a manifest."""
    with pytest.raises(ReplayConfigError):
        replay(bad_config)


def test_non_mapping_config_fails_closed() -> None:
    """A non-mapping config fails closed rather than being silently coerced."""
    not_a_mapping: Any = ["not", "a", "mapping"]
    with pytest.raises(ReplayConfigError):
        replay(not_a_mapping)


def test_main_emits_valid_manifest_json(capsys: pytest.CaptureFixture[str]) -> None:
    """main() with an inline config prints a parseable, boundary-bearing manifest."""
    rc = main(["--config-json", json.dumps(_fixed_config())])
    assert rc == 0
    out = capsys.readouterr().out
    manifest = json.loads(out)
    assert manifest["claim_boundary"] == "descriptor_only_not_predictor"
    assert "manifest_digest" in manifest


def test_main_fails_closed_on_bad_json() -> None:
    """main() returns the fail-closed exit code on undecodable config input."""
    rc = main(["--config-json", "{not valid json"])
    assert rc == 2


def test_cli_subprocess_smoke() -> None:
    """The script runs as a real subprocess and emits a reproducible digest."""
    cfg = json.dumps(_gaussian_config())
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--config-json", cfg],
        capture_output=True,
        text=True,
        check=True,
    )
    manifest = json.loads(proc.stdout)
    # Re-running the in-process replay must match the subprocess digest.
    assert manifest["manifest_digest"] == replay(_gaussian_config())["manifest_digest"]


def test_cli_help_exposes_no_predictive_language() -> None:
    """The --help surface must not promise prediction or trading outcomes."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    help_text = proc.stdout.lower()
    for banned in ("forecast", "predictor of", "buy ", "sell ", "profit", "alpha engine"):
        assert banned not in help_text


def test_module_docstring_has_no_trading_language() -> None:
    """The module docstring must stay descriptor-only, no trading promises."""
    mod = sys.modules[main.__module__]

    doc = (mod.__doc__ or "").lower()
    assert "descriptor-only" in doc or "descriptor_only_not_predictor" in doc
    for banned in ("buy signal", "sell signal", "guaranteed return", "alpha engine"):
        assert banned not in doc


def test_supported_methods_are_descriptor_only() -> None:
    """The advertised methods are descriptor/null methods, no predictor names."""
    assert set(SUPPORTED_METHODS) == {"fixed_threshold", "gaussian_null", "constant_null"}
