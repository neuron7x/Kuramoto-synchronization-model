# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for execution.live_loop LiveLoopConfig."""

from __future__ import annotations

import pytest

from execution.live_loop import LiveLoopConfig


class TestLiveLoopConfig:
    def test_defaults(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "state")
        assert cfg.submission_interval == 0.25
        assert cfg.fill_poll_interval == 1.0
        assert cfg.heartbeat_interval == 10.0
        assert cfg.max_backoff == 60.0
        assert cfg.snapshot_interval == 30.0
        assert cfg.pre_action_timeout == 0.2

    def test_string_state_dir(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=str(tmp_path / "s"))
        from pathlib import Path

        assert isinstance(cfg.state_dir, Path)

    def test_creates_state_dir(self, tmp_path):
        d = tmp_path / "new_dir"
        assert not d.exists()
        LiveLoopConfig(state_dir=d)
        assert d.exists()

    def test_min_submission_interval(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", submission_interval=0.001)
        assert cfg.submission_interval == 0.01

    def test_min_fill_poll_interval(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", fill_poll_interval=0.01)
        assert cfg.fill_poll_interval == 0.1

    def test_min_heartbeat_interval(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", heartbeat_interval=0.1)
        assert cfg.heartbeat_interval == 0.5

    def test_max_backoff_at_least_heartbeat(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", heartbeat_interval=20.0, max_backoff=5.0)
        assert cfg.max_backoff >= cfg.heartbeat_interval

    def test_min_snapshot_interval(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", snapshot_interval=0.1)
        assert cfg.snapshot_interval == 1.0

    def test_pre_action_timeout_zero_becomes_none(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", pre_action_timeout=0)
        assert cfg.pre_action_timeout is None

    def test_pre_action_timeout_negative_becomes_none(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", pre_action_timeout=-1.0)
        assert cfg.pre_action_timeout is None

    def test_ledger_dir_default(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s")
        assert cfg.ledger_dir == cfg.state_dir

    def test_ledger_dir_custom(self, tmp_path):
        ld = tmp_path / "ledger"
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", ledger_dir=ld)
        assert cfg.ledger_dir == ld
        assert ld.exists()

    def test_ledger_dir_string(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", ledger_dir=str(tmp_path / "led"))
        from pathlib import Path

        assert isinstance(cfg.ledger_dir, Path)

    def test_credentials_default_none(self, tmp_path):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s")
        assert cfg.credentials is None

    @pytest.mark.parametrize("interval", [0.25, 0.5, 1.0, 5.0])
    def test_various_submission_intervals(self, tmp_path, interval):
        cfg = LiveLoopConfig(state_dir=tmp_path / "s", submission_interval=interval)
        assert cfg.submission_interval >= 0.01
