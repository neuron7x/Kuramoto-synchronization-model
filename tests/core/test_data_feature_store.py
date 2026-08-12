# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.feature_store module."""

from __future__ import annotations

import pandas as pd
import pytest

from core.data.feature_store import (
    FeatureStoreConfigurationError,
    FeatureStoreIntegrityError,
    RetentionPolicy,
)


class TestRetentionPolicy:
    def test_defaults(self):
        p = RetentionPolicy()
        assert p.ttl is None
        assert p.max_versions is None

    def test_valid_ttl(self):
        p = RetentionPolicy(ttl=pd.Timedelta(hours=1))
        assert p.ttl == pd.Timedelta(hours=1)

    def test_negative_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl must be positive"):
            RetentionPolicy(ttl=pd.Timedelta(hours=-1))

    def test_zero_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl must be positive"):
            RetentionPolicy(ttl=pd.Timedelta(0))

    def test_valid_max_versions(self):
        p = RetentionPolicy(max_versions=10)
        assert p.max_versions == 10

    def test_zero_max_versions_raises(self):
        with pytest.raises(ValueError, match="max_versions must be positive"):
            RetentionPolicy(max_versions=0)

    def test_negative_max_versions_raises(self):
        with pytest.raises(ValueError, match="max_versions must be positive"):
            RetentionPolicy(max_versions=-1)

    def test_both_params(self):
        p = RetentionPolicy(ttl=pd.Timedelta(days=7), max_versions=100)
        assert p.ttl == pd.Timedelta(days=7)
        assert p.max_versions == 100

    def test_frozen(self):
        p = RetentionPolicy(ttl=pd.Timedelta(hours=1))
        with pytest.raises(AttributeError):
            p.ttl = pd.Timedelta(hours=2)


class TestExceptions:
    def test_integrity_error(self):
        err = FeatureStoreIntegrityError("bad hash")
        assert isinstance(err, RuntimeError)
        assert str(err) == "bad hash"

    def test_configuration_error(self):
        err = FeatureStoreConfigurationError("missing key")
        assert isinstance(err, RuntimeError)
        assert str(err) == "missing key"
