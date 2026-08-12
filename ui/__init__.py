# Copyright (c) 2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Namespace-package anchor for the ``ui`` tree.

The ``ui/`` directory is primarily a JS/TS dashboard tree; this file exists
only so mypy can resolve ``ui.dashboard.live_server`` as a single canonical
module, preventing the "source file found twice under different module
names" ambiguity that arises when CI's delta-scoped mypy scans a changed
Python file under both its bare name and its dotted path.
"""
