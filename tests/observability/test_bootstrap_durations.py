# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import math
from datetime import timedelta

import pytest

from observability.bootstrap import _parse_duration, _parse_duration_to_seconds


def test_parse_duration_to_seconds_preserves_subsecond_precision() -> None:
    assert _parse_duration_to_seconds("500ms") == 0.5
    assert _parse_duration_to_seconds("1500ms") == 1.5


def test_parse_duration_accepts_fractional_seconds() -> None:
    result = _parse_duration("0.25s")
    assert isinstance(result, timedelta)
    assert math.isclose(result.total_seconds(), 0.25)


def test_parse_duration_supports_minutes_and_hours_as_floats() -> None:
    assert math.isclose(_parse_duration_to_seconds("1.5m"), 90.0)
    assert math.isclose(_parse_duration_to_seconds("0.5h"), 1800.0)


def test_parse_duration_rejects_unknown_units() -> None:
    with pytest.raises(ValueError):
        _parse_duration_to_seconds("10w")
