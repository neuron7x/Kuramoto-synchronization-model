# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Entrypoint for running the cortex service via ``python -m``."""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit(
        "Deprecated entrypoint. Use: python -m application.runtime.server --config <path>"
    )
