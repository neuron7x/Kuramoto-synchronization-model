# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Entry point to allow ``python -m scripts`` execution."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from .cli import main

if __name__ == "__main__":  # pragma: no cover - module execution
    raise SystemExit(main())
