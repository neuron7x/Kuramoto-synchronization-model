# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.live_loop module."""

from __future__ import annotations

import pytest

from execution.live_loop import Signal, _full_jitter_backoff, _snapshot_timestamp


class TestFullJitterBackoff:
    def test_zero_attempt(self):
        result = _full_jitter_backoff(1.0, 0, 10.0)
        assert 0.0 <= result <= 1.0

    def test_increasing_cap(self):
        results = [_full_jitter_backoff(1.0, i, 100.0) for i in range(5)]
        # All should be within [0, cap]
        for r in results:
            assert 0.0 <= r <= 100.0

    def test_cap_enforced(self):
        result = _full_jitter_backoff(1.0, 100, 5.0)
        assert result <= 5.0

    def test_negative_attempt_handled(self):
        result = _full_jitter_backoff(1.0, -1, 10.0)
        assert 0.0 <= result <= 10.0

    @pytest.mark.parametrize("base", [0.1, 0.5, 1.0, 2.0])
    def test_various_bases(self, base):
        result = _full_jitter_backoff(base, 3, 100.0)
        assert 0.0 <= result <= min(100.0, base * (2**3))


class TestSnapshotTimestamp:
    def test_valid_filename(self, tmp_path):
        p = tmp_path / "oms_snapshot_1234567890.json"
        p.write_text("{}")
        assert _snapshot_timestamp(p) == 1234567890.0

    def test_float_timestamp(self, tmp_path):
        p = tmp_path / "oms_snapshot_1234567890.123.json"
        p.write_text("{}")
        assert _snapshot_timestamp(p) == 1234567890.123

    def test_invalid_filename_falls_back(self, tmp_path):
        p = tmp_path / "snapshot.json"
        p.write_text("{}")
        ts = _snapshot_timestamp(p)
        assert ts > 0  # Falls back to mtime

    def test_non_numeric_suffix_falls_back(self, tmp_path):
        p = tmp_path / "oms_snapshot_abc.json"
        p.write_text("{}")
        ts = _snapshot_timestamp(p)
        assert ts > 0


class TestSignal:
    def test_connect_and_emit(self):
        sig = Signal()
        results = []
        sig.connect(lambda x: results.append(x))
        sig.emit(42)
        assert results == [42]

    def test_multiple_subscribers(self):
        sig = Signal()
        r1, r2 = [], []
        sig.connect(lambda x: r1.append(x))
        sig.connect(lambda x: r2.append(x))
        sig.emit("hello")
        assert r1 == ["hello"]
        assert r2 == ["hello"]

    def test_emit_with_kwargs(self):
        sig = Signal()
        results = []
        sig.connect(lambda **kw: results.append(kw))
        sig.emit(key="val")
        assert results == [{"key": "val"}]

    def test_no_subscribers(self):
        sig = Signal()
        sig.emit("nothing")  # Should not raise

    def test_emit_multiple_args(self):
        sig = Signal()
        results = []
        sig.connect(lambda a, b: results.append((a, b)))
        sig.emit(1, 2)
        assert results == [(1, 2)]
