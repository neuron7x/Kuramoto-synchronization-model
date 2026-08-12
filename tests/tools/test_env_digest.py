# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the deterministic environment digest (evidence-grade provenance)."""

from __future__ import annotations

import re

from tools.provenance import env_digest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_env_sha256_is_64_hex() -> None:
    assert _HEX64.fullmatch(env_digest.env_sha256())


def test_env_sha256_is_deterministic_for_fixed_manifest() -> None:
    manifest = {"interpreter": "cpython-3.12.0", "dependencies": ["numpy==2.0.0"], "blas": "blas:openblas"}
    assert env_digest.env_sha256(manifest) == env_digest.env_sha256(manifest)


def test_env_sha256_is_order_independent() -> None:
    a = {"interpreter": "x", "dependencies": ["a==1", "b==2"], "blas": "y"}
    b = {"blas": "y", "dependencies": ["a==1", "b==2"], "interpreter": "x"}
    assert env_digest.env_sha256(a) == env_digest.env_sha256(b)


def test_env_sha256_changes_with_dependencies() -> None:
    base = {"interpreter": "x", "dependencies": ["numpy==2.0.0"], "blas": "y"}
    bumped = {"interpreter": "x", "dependencies": ["numpy==2.1.0"], "blas": "y"}
    assert env_digest.env_sha256(base) != env_digest.env_sha256(bumped)


def test_environment_manifest_has_required_keys() -> None:
    m = env_digest.environment_manifest()
    assert set(m) == {"interpreter", "dependencies", "blas"}
    assert isinstance(m["dependencies"], list)
    assert m["dependencies"] == sorted(m["dependencies"])  # canonical order
