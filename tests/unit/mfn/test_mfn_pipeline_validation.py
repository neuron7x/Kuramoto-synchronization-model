# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

import pytest

from geosync.mfn.contract import MFNContract
from geosync.mfn.pipeline import extract, write_json


def test_extract_rejects_observations_without_two_prices(tmp_path: Path) -> None:
    write_json(
        tmp_path / "simulate.json",
        {
            "observations": [
                {"price": 100.0},
                "not-a-record",
            ]
        },
    )

    with pytest.raises(ValueError, match="at least two price observations"):
        extract(tmp_path, contract=MFNContract())
