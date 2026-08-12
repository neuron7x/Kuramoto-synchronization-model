# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compatibility shim -> application.risk.risk_manager.

Retained so the not-yet-relocated ``src.admin.remote_control`` (which imports
``KillSwitchState``/``RiskManagerFacade``) keeps resolving during the staged src/ migration
(docs/audit/INTEGRATION_DEBT_2026-07-23.md). Removed once remote_control moves (stage 4).
"""

from application.risk.risk_manager import *  # noqa: F401,F403
from application.risk.risk_manager import __all__  # noqa: F401
