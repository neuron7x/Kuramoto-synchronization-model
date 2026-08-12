# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Allow --hypothesis-show-statistics when Hypothesis is missing."""
    try:
        import hypothesis  # noqa: F401  # Hypothesis plugin already registers the option
    except Exception:
        try:
            parser.addoption(
                "--hypothesis-show-statistics",
                action="store_true",
                default=False,
                help="Compatibility flag when Hypothesis is unavailable",
            )
        except ValueError:
            # Option already registered by another plugin; ignore redefinition.
            pass
