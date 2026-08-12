# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from ..core.params import PredictiveConfig, SensoryConfig


@pytest.mark.parametrize(
    ("config_cls", "keys"),
    [
        (SensoryConfig, ("dd", "liq")),
        (PredictiveConfig, ("reg", "vol")),
    ],
)
def test_config_keys_valid(config_cls, keys) -> None:
    config = config_cls(keys=keys)
    assert config.keys == keys


@pytest.mark.parametrize(
    ("config_cls", "keys"),
    [
        (SensoryConfig, ("dd", "unknown")),
        (PredictiveConfig, ("vol", "bad")),
    ],
)
def test_config_keys_invalid_unexpected(config_cls, keys) -> None:
    with pytest.raises(ValueError, match="Allowed keys: dd, liq, reg, vol."):
        config_cls(keys=keys)


@pytest.mark.parametrize("config_cls", [SensoryConfig, PredictiveConfig])
def test_config_keys_empty(config_cls) -> None:
    with pytest.raises(ValueError, match="keys must be non-empty"):
        config_cls(keys=())


@pytest.mark.parametrize("config_cls", [SensoryConfig, PredictiveConfig])
def test_config_keys_duplicates(config_cls) -> None:
    with pytest.raises(ValueError, match="keys must be unique"):
        config_cls(keys=("dd", "dd"))


@pytest.mark.parametrize("config_cls", [SensoryConfig, PredictiveConfig])
def test_config_keys_blank_entry(config_cls) -> None:
    with pytest.raises(ValueError, match="keys must be non-empty strings"):
        config_cls(keys=("dd", ""))
