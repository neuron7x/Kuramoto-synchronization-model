# SPDX-License-Identifier: MIT
import importlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.parametrize(
    "augend, addend, expected",
    [
        (0, 0, 0),
        (2, 3, 5),
        (-4, -6, -10),
        (-7, 5, -2),
        (10**6, 10**6, 2 * 10**6),
    ],
)
def test_add_returns_integer_sum(augend: int, addend: int, expected: int) -> None:
    module = importlib.import_module("markets.vpin.src.core.main")

    assert module.add(augend, addend) == expected
