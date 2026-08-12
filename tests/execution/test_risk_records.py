# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.risk.core — KillSwitchStateRecord and RiskStateRecord."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.risk.core import DataQualityError, KillSwitchStateRecord, RiskStateRecord


class TestKillSwitchStateRecord:
    def test_valid_engaged(self):
        rec = KillSwitchStateRecord(
            engaged=True,
            reason="max drawdown exceeded",
            updated_at=datetime.now(timezone.utc),
        )
        assert rec.engaged is True
        assert rec.reason == "max drawdown exceeded"

    def test_valid_disengaged(self):
        rec = KillSwitchStateRecord(engaged=False, reason="", updated_at=datetime.now(timezone.utc))
        assert rec.engaged is False

    def test_engaged_without_reason_raises(self):
        with pytest.raises(Exception, match="reason"):
            KillSwitchStateRecord(engaged=True, reason="", updated_at=datetime.now(timezone.utc))

    def test_from_tuple(self):
        now = datetime.now(timezone.utc)
        rec = KillSwitchStateRecord.model_validate((True, "limit breached", now))
        assert rec.engaged is True

    def test_iso_string_timestamp(self):
        rec = KillSwitchStateRecord(engaged=False, reason="", updated_at="2024-01-01T00:00:00Z")
        assert rec.updated_at.year == 2024
        assert rec.updated_at.tzinfo is not None

    def test_naive_timestamp_gets_utc(self):
        rec = KillSwitchStateRecord(engaged=False, reason="", updated_at="2024-01-01T00:00:00")
        assert rec.updated_at.tzinfo == timezone.utc

    def test_control_chars_in_reason_rejected(self):
        with pytest.raises(Exception, match="control"):
            KillSwitchStateRecord(
                engaged=True,
                reason="bad\x00reason",
                updated_at=datetime.now(timezone.utc),
            )

    def test_missing_updated_at_raises(self):
        with pytest.raises(Exception):
            KillSwitchStateRecord(engaged=False, reason="")

    def test_tuple_wrong_length_raises(self):
        with pytest.raises(Exception):
            KillSwitchStateRecord.model_validate((True, "reason"))

    def test_unsupported_type_raises(self):
        with pytest.raises(Exception):
            KillSwitchStateRecord.model_validate(42)


class TestRiskStateRecord:
    def test_defaults(self):
        rec = RiskStateRecord()
        assert rec.positions == {}
        assert rec.last_notional == {}

    def test_valid_data(self):
        rec = RiskStateRecord(
            positions={"BTCUSD": 1.5, "ETHUSD": -0.5},
            last_notional={"BTCUSD": 50000.0},
        )
        assert rec.positions["BTCUSD"] == 1.5
        assert rec.last_notional["BTCUSD"] == 50000.0

    def test_none_payload(self):
        rec = RiskStateRecord.model_validate(None)
        assert rec.positions == {}

    def test_empty_mapping(self):
        rec = RiskStateRecord.model_validate({})
        assert rec.positions == {}

    def test_empty_symbol_filtered(self):
        # Use model_validate to go through the before validator
        rec = RiskStateRecord.model_validate({"positions": {"": 1.0, "  ": 2.0, "BTC": 3.0}})
        assert "" not in rec.positions
        assert "BTC" in rec.positions

    def test_wrong_type_raises(self):
        with pytest.raises(Exception, match="mapping"):
            RiskStateRecord.model_validate(42)

    def test_positions_not_mapping_raises(self):
        with pytest.raises(Exception, match="mapping"):
            RiskStateRecord.model_validate({"positions": [1, 2, 3]})

    # DEFECT 3: non-finite persisted positions must fail CLOSED (quarantine),
    # consistent with the sibling corruption paths, instead of being kept
    # unguarded and poisoning downstream cap/drawdown computations.
    def test_nan_position_raises(self):
        with pytest.raises(DataQualityError, match="not finite"):
            RiskStateRecord.model_validate({"positions": {"BTCUSD": float("nan")}})

    def test_inf_position_raises(self):
        with pytest.raises(DataQualityError, match="not finite"):
            RiskStateRecord.model_validate({"positions": {"BTCUSD": float("inf")}})

    def test_neg_inf_notional_raises(self):
        with pytest.raises(DataQualityError, match="not finite"):
            RiskStateRecord.model_validate({"last_notional": {"ETHUSD": float("-inf")}})
