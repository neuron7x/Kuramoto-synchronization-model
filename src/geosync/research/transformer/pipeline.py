# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic placeholder pipeline for the inference transformer control plane.

The pipeline emits a schema-compatible research envelope with ABSTAIN/HYPOTHESIS
semantics. It is intentionally inert and exists to make the control plane
executable before any evidence-bearing computation is added.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import sha256_json

SCHEMA_ID = "https://schemas.neuron7xlab.org/research/research_inference_artifact.schema.json"
ZERO_SHA64 = "0" * 64


def build_placeholder_artifact(
    *,
    git_sha: str,
    config_path: str = "configs/research/geosync_inference_transformer.v1.yaml",
    research_line: str = "ricci_microstructure_v1",
    run_id: str = "ITCP-PLACEHOLDER-001",
    seed: int = 7,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic non-evidence research envelope."""

    if len(git_sha) != 40 or any(char not in "0123456789abcdef" for char in git_sha):
        raise ValueError("git_sha must be a 40-character lowercase hex string")
    if timestamp_utc is None:
        timestamp_utc = datetime(2026, 1, 1, tzinfo=UTC).isoformat().replace("+00:00", "Z")

    config_digest = sha256_json({"config_path": config_path, "research_line": research_line})
    payload: dict[str, Any] = {
        "conforms_to": SCHEMA_ID,
        "schema_version": "1.0.0",
        "research_line": research_line,
        "run_id": run_id,
        "git_sha": git_sha,
        "git_dirty": False,
        "data_sha256": ZERO_SHA64,
        "config_sha256": config_digest,
        "seed": seed,
        "timestamp_utc": timestamp_utc,
        "input_window_sec": 1,
        "score": 0.0,
        "uncertainty": 1.0,
        "decision": "ABSTAIN",
        "claim_tier": "HYPOTHESIS",
        "falsification_status": "NOT_RUN",
        "artifact_role": "placeholder",
        "method_version": "inference-transformer-placeholder.v1",
        "score_source": "placeholder",
        "baseline": "none:placeholder",
        "replay_command": "python tools/research/run_inference_transformer_demo.py",
        "env_sha256": ZERO_SHA64,
        "agent": "human:neuron7xLab",
    }
    payload["output_sha256"] = sha256_json(payload)
    return payload


def write_placeholder_artifact(path: Path, *, git_sha: str) -> dict[str, Any]:
    """Write the deterministic placeholder envelope to disk."""

    artifact = build_placeholder_artifact(git_sha=git_sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact
