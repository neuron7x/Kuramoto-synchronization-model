# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest

from geosync.mfn.contract import MFNContract


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": ""},
        {"seed": True},
        {"seed": "1337"},
        {"input_window_sec": False},
        {"input_window_sec": 0},
        {"claim_tier": ""},
    ],
)
def test_mfn_contract_rejects_invalid_fields(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MFNContract(**kwargs)


def test_mfn_contract_accepts_default_contract() -> None:
    contract = MFNContract()

    assert contract.schema_version == "mfn.integration.v1"
    assert contract.seed == 1337
    assert contract.input_window_sec == 30
    assert contract.claim_tier == "INSTRUMENTED"
