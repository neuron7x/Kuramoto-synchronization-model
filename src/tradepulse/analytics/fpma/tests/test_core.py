# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import importlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_add():
    module = importlib.import_module("analytics.fpma.src.core.main")
    assert module.add(2, 3) == 5
