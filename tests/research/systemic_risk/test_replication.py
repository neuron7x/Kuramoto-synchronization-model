# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the replication manifest (§ 13 of the validation protocol)."""

from __future__ import annotations

import json

from research.systemic_risk.replication import build_run_manifest


class TestBuildRunManifest:
    def test_config_hash_is_stable(self) -> None:
        a = build_run_manifest(seed=42, config={"window": 60, "alpha": 0.01})
        b = build_run_manifest(seed=42, config={"alpha": 0.01, "window": 60})
        assert a.config_hash == b.config_hash, (
            "config_hash must be invariant to dict-key order; "
            "JSON serialisation uses sort_keys=True"
        )

    def test_config_hash_changes_with_value(self) -> None:
        a = build_run_manifest(seed=42, config={"window": 60})
        b = build_run_manifest(seed=42, config={"window": 90})
        assert a.config_hash != b.config_hash

    def test_seed_recorded_verbatim(self) -> None:
        m = build_run_manifest(seed=12345, config={})
        assert m.seed == 12345

    def test_to_json_round_trip(self) -> None:
        m = build_run_manifest(
            seed=7,
            config={"k": 3, "name": "demo"},
            extra={"dataset": "synthetic"},
        )
        payload = json.loads(m.to_json())
        assert payload["seed"] == 7
        assert payload["config"] == {"k": 3, "name": "demo"}
        assert payload["extra"] == {"dataset": "synthetic"}
        assert "timestamp_utc" in payload
        assert "platform_info" in payload
        assert "package_versions" in payload

    def test_package_versions_contains_numpy(self) -> None:
        m = build_run_manifest(seed=0, config={})
        # numpy is a hard dependency of the suite — must be present.
        assert "numpy" in m.package_versions
        assert m.package_versions["numpy"] != "not-installed"

    def test_to_json_is_deterministic(self) -> None:
        # Two manifests built with identical inputs differ only in
        # timestamp; serialisation order is deterministic so the
        # bytes diff reduces to that single line.
        a = build_run_manifest(seed=1, config={"a": 1, "b": 2})
        b = build_run_manifest(seed=1, config={"a": 1, "b": 2})
        a_lines = [line for line in a.to_json().splitlines() if "timestamp" not in line]
        b_lines = [line for line in b.to_json().splitlines() if "timestamp" not in line]
        assert a_lines == b_lines
