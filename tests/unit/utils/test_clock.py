# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import datetime as dt
import time

from core.utils.clock import freeze_time


def test_freeze_time_freezes_multiple_sources() -> None:
    target = dt.datetime(2024, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

    with freeze_time(target) as frozen:
        assert frozen == target
        assert dt.datetime.now() == target.replace(tzinfo=None)
        assert dt.datetime.utcnow() == target.replace(tzinfo=None)
        assert dt.datetime.now(dt.timezone.utc) == target
        assert dt.date.today() == target.date()
        assert time.time() == target.timestamp()
        assert time.time_ns() == int(target.timestamp() * 1_000_000_000)
        assert time.monotonic() == 1.0
        assert time.perf_counter() == 1.0

    # After exiting the context the monotonic clock should resume increasing.
    assert time.monotonic() != 1.0


def test_freeze_time_accepts_epoch_seconds() -> None:
    target_epoch = 1_700_000_000

    with freeze_time(target_epoch) as frozen:
        assert frozen == dt.datetime.fromtimestamp(target_epoch, tz=dt.timezone.utc)
        assert dt.datetime.utcnow() == dt.datetime.fromtimestamp(
            target_epoch, tz=dt.timezone.utc
        ).replace(tzinfo=None)
