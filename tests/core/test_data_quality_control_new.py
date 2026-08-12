# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.quality_control — RangeCheck and TemporalContract."""

from __future__ import annotations

import pandas as pd
import pytest

from core.data.quality_control import QualityGateError, RangeCheck, TemporalContract


class TestRangeCheck:
    def test_valid_min_only(self):
        rc = RangeCheck(column="price", min_value=0.0)
        assert rc.column == "price"
        assert rc.min_value == 0.0
        assert rc.max_value is None

    def test_valid_max_only(self):
        rc = RangeCheck(column="volume", max_value=1e9)
        assert rc.max_value == 1e9

    def test_valid_both_bounds(self):
        rc = RangeCheck(column="ratio", min_value=0.0, max_value=1.0)
        assert rc.min_value == 0.0
        assert rc.max_value == 1.0

    def test_no_bounds_raises(self):
        with pytest.raises(Exception, match="at least"):
            RangeCheck(column="x")

    def test_min_exceeds_max_raises(self):
        with pytest.raises(Exception, match="exceeds"):
            RangeCheck(column="x", min_value=10.0, max_value=5.0)

    def test_inclusive_defaults(self):
        rc = RangeCheck(column="p", min_value=0.0)
        assert rc.inclusive_min is True
        assert rc.inclusive_max is True

    def test_exclusive_bounds(self):
        rc = RangeCheck(
            column="p",
            min_value=0.0,
            max_value=100.0,
            inclusive_min=False,
            inclusive_max=False,
        )
        assert rc.inclusive_min is False
        assert rc.inclusive_max is False

    def test_frozen(self):
        rc = RangeCheck(column="p", min_value=0.0)
        with pytest.raises(Exception):
            rc.column = "q"

    @pytest.mark.parametrize("min_v,max_v", [(0, 100), (-10.0, 10.0), (0.0, 0.0)])
    def test_equal_bounds_allowed(self, min_v, max_v):
        rc = RangeCheck(column="x", min_value=min_v, max_value=max_v)
        assert rc.min_value is not None


class TestTemporalContract:
    def test_creation(self):
        tc = TemporalContract(
            earliest=pd.Timestamp("2024-01-01", tz="UTC"),
            latest=pd.Timestamp("2024-12-31", tz="UTC"),
        )
        assert tc.earliest.year == 2024

    def test_no_bounds(self):
        tc = TemporalContract()
        assert tc.earliest is None
        assert tc.latest is None

    def test_frozen(self):
        tc = TemporalContract()
        with pytest.raises(Exception):
            tc.earliest = pd.Timestamp("2024-01-01")


class TestQualityGateError:
    def test_is_exception(self):
        err = QualityGateError("bad data")
        assert isinstance(err, Exception)
        assert str(err) == "bad data"
