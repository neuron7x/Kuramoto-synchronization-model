# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Compatibility shim: security primitives now live at ``application.security.access_control``.

Retained so ``import src.security`` (tests/packaging/test_namespace.py) and any lingering
``src.security.*`` importer keeps resolving during the staged src/ migration
(docs/audit/INTEGRATION_DEBT_2026-07-23.md). New code imports from application.security.access_control.
"""

from application.security.access_control import (
    AccessController,
    AccessDeniedError,
    AccessPolicy,
)

__all__ = ["AccessController", "AccessDeniedError", "AccessPolicy"]
