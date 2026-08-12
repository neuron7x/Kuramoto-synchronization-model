# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from execution.risk import KillSwitchStateRecord


def test_tuple_payload_is_normalised_to_utc_and_stripped_reason() -> None:
    naive_timestamp = datetime(2025, 1, 1, 12, 30, 0)
    record = KillSwitchStateRecord.model_validate((True, " maintenance  ", naive_timestamp))

    assert record.engaged is True
    assert record.reason == "maintenance"
    assert record.updated_at.tzinfo == timezone.utc
    assert record.updated_at == naive_timestamp.replace(tzinfo=timezone.utc)


def test_string_timestamp_allows_space_separator_and_converts_timezone() -> None:
    aware_timestamp = datetime(2025, 5, 1, 8, 15, 0, tzinfo=timezone(timedelta(hours=-4)))
    payload = {
        "engaged": False,
        "reason": None,
        "updated_at": aware_timestamp.isoformat().replace("T", " "),
    }

    record = KillSwitchStateRecord.model_validate(payload)

    assert record.engaged is False
    assert record.reason == ""
    assert record.updated_at.tzinfo == timezone.utc
    assert record.updated_at == aware_timestamp.astimezone(timezone.utc)


def test_timestamp_with_utc_z_suffix_is_accepted() -> None:
    payload = {
        "engaged": True,
        "reason": "maintenance",
        "updated_at": "2025-01-15T10:00:00Z",
    }

    record = KillSwitchStateRecord.model_validate(payload)

    assert record.updated_at == datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    assert record.reason == "maintenance"
    assert record.engaged is True


@pytest.mark.parametrize("bad_reason", ["", "\x00control"])
def test_reason_validation_enforced_when_engaged(bad_reason: str) -> None:
    with pytest.raises(ValueError):
        KillSwitchStateRecord.model_validate(
            {
                "engaged": True,
                "reason": bad_reason,
                "updated_at": datetime.now(timezone.utc),
            }
        )


def test_unsupported_payload_shape_raises_type_error() -> None:
    with pytest.raises(TypeError):
        KillSwitchStateRecord.model_validate(123)


def test_missing_timestamp_raises_value_error() -> None:
    with pytest.raises(ValueError):
        KillSwitchStateRecord.model_validate({"engaged": False, "reason": "ok"})
