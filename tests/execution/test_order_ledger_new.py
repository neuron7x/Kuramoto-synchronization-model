# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.order_ledger module."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from execution.order_ledger import (
    LedgerMetadata,
    OrderLedgerConfig,
    _canonical_dumps,
    _coerce,
)


class TestCoerce:
    def test_none(self):
        assert _coerce(None) is None

    def test_primitives(self):
        assert _coerce(42) == 42
        assert _coerce(3.14) == 3.14
        assert _coerce("hello") == "hello"
        assert _coerce(True) is True

    def test_datetime_with_tz(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = _coerce(dt)
        assert "2024-01-01" in result

    def test_datetime_naive(self):
        dt = datetime(2024, 1, 1)
        result = _coerce(dt)
        assert "2024-01-01" in result

    def test_mapping(self):
        result = _coerce({"a": 1, "b": [1, 2, 3]})
        assert result == {"a": 1, "b": [1, 2, 3]}

    def test_list(self):
        result = _coerce([1, "two", 3.0])
        assert result == [1, "two", 3.0]

    def test_tuple_becomes_list(self):
        result = _coerce((1, 2, 3))
        assert result == [1, 2, 3]

    def test_set_becomes_list(self):
        result = _coerce({1, 2, 3})
        assert isinstance(result, list)
        assert set(result) == {1, 2, 3}

    def test_path(self):
        result = _coerce(Path("/tmp/file"))
        assert result == "/tmp/file"

    def test_custom_object_becomes_repr(self):
        class Custom:
            def __repr__(self):
                return "Custom()"

        assert _coerce(Custom()) == "Custom()"

    def test_nested_mapping(self):
        result = _coerce({"outer": {"inner": datetime(2024, 1, 1, tzinfo=timezone.utc)}})
        assert "2024-01-01" in result["outer"]["inner"]


class TestCanonicalDumps:
    def test_stable_ordering(self):
        d1 = {"b": 2, "a": 1}
        d2 = {"a": 1, "b": 2}
        assert _canonical_dumps(d1) == _canonical_dumps(d2)

    def test_no_spaces(self):
        result = _canonical_dumps({"a": 1, "b": 2})
        assert " " not in result

    def test_unicode(self):
        result = _canonical_dumps({"key": "hello"})
        assert "hello" in result


class TestOrderLedgerConfig:
    def test_defaults(self):
        cfg = OrderLedgerConfig()
        assert cfg.snapshot_interval == 500
        assert cfg.snapshot_retention == 8
        assert cfg.compaction_threshold_events == 10_000
        assert cfg.archive_retention == 4
        assert cfg.index_stride == 64

    def test_invalid_snapshot_interval(self):
        with pytest.raises(ValueError, match="snapshot_interval"):
            OrderLedgerConfig(snapshot_interval=0)

    def test_invalid_snapshot_retention(self):
        with pytest.raises(ValueError, match="snapshot_retention"):
            OrderLedgerConfig(snapshot_retention=0)

    def test_invalid_compaction_threshold(self):
        with pytest.raises(ValueError, match="compaction_threshold"):
            OrderLedgerConfig(compaction_threshold_events=-1)

    def test_invalid_max_journal_size(self):
        with pytest.raises(ValueError, match="max_journal_size"):
            OrderLedgerConfig(max_journal_size=100)

    def test_invalid_archive_retention(self):
        with pytest.raises(ValueError, match="archive_retention"):
            OrderLedgerConfig(archive_retention=0)

    def test_invalid_index_stride(self):
        with pytest.raises(ValueError, match="index_stride"):
            OrderLedgerConfig(index_stride=0)

    def test_frozen(self):
        cfg = OrderLedgerConfig()
        with pytest.raises(Exception):
            cfg.snapshot_interval = 1000


class TestLedgerMetadata:
    def test_new(self):
        m = LedgerMetadata.new()
        assert m.version == 1
        assert m.event_count == 0
        assert m.next_sequence == 1
        assert m.tail_digest is None
        assert m.last_snapshot_sequence is None

    def test_meta_version_constant(self):
        assert LedgerMetadata.META_VERSION == 1

    def test_custom_fields(self):
        m = LedgerMetadata(
            version=1,
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            event_count=10,
            next_sequence=11,
            tail_digest="abc123",
            last_snapshot_sequence=5,
            last_snapshot_path="/tmp/snapshot",
            last_state_hash="def456",
            compacted_through=3,
            anchor_digest="ghi789",
            last_compaction_at="2024-01-01T00:00:00+00:00",
        )
        assert m.event_count == 10
        assert m.tail_digest == "abc123"
