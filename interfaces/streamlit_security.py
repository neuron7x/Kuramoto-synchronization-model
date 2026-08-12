# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime guards to keep Streamlit usage confined to development contexts."""

from __future__ import annotations

import os


def enforce_dev_only_dashboard() -> None:
    """Prevent running the Streamlit dashboard in production by default."""

    env = os.getenv("GEOSYNC_ENV", "").lower()
    if env in {"prod", "production"} and os.getenv("ALLOW_STREAMLIT_PROD") != "1":
        raise RuntimeError(
            "Streamlit dashboard is disabled in production. "
            "Set ALLOW_STREAMLIT_PROD=1 to explicitly opt-in for break-glass use."
        )
