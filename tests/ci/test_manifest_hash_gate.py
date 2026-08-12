# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compatibility sentinel for manifest hash gate tests."""

from __future__ import annotations

from pathlib import Path


def test_manifest_hash_gate_coverage_owner_exists() -> None:
    owner = Path(__file__).with_name("test_manifest_hashes.py")
    assert owner.exists()
