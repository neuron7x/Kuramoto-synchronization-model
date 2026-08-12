# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Module entry point so ``python -m tools.synthetic_l2 ...`` works."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":  # pragma: no cover — exercised via subprocess in tests.
    raise SystemExit(main())
