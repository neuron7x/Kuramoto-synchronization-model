# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CI command modules packaged for GeoSync script entrypoints.

This package marker makes ``scripts.ci.*`` console-script targets importable
after a normal wheel or editable install, instead of relying on the repository
root accidentally being present on ``PYTHONPATH``.
"""

from __future__ import annotations

__all__: list[str] = []
