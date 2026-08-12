# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import datetime, timezone

import pytest

from core.data.timeutils import normalize_timestamp


def test_normalize_timestamp_handles_nanoseconds_epoch():
    nanosecond_epoch = 1_600_000_000_000_000_000
    ts = normalize_timestamp(nanosecond_epoch)
    assert ts == datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "value, expected",
    [
        (1_600_000_000_000_000, datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)),
        (1_270_000_000_000, datetime(2010, 3, 31, 1, 46, 40, tzinfo=timezone.utc)),
    ],
)
def test_normalize_timestamp_preserves_micro_and_milli_precision(value, expected):
    assert normalize_timestamp(value) == expected
