"""Alias CLI for backwards compatibility with legacy tooling.

Copyright (c) 2024 TradePulse Technologies. All rights reserved.
Licensed under the TradePulse Proprietary License Agreement (TPLA).
"""

from __future__ import annotations

from .run_validate import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
