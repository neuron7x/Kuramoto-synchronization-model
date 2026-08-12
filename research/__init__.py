# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Research namespace initialisation.

Importing research modules installs a narrow pandas datetime guard that prevents
known CPython-level crashes for ``Series[datetime.date]`` conversion while
leaving all other ``pandas.to_datetime`` behaviour delegated to pandas.
"""

from __future__ import annotations

from ._pandas_datetime_guard import install_safe_to_datetime_guard

install_safe_to_datetime_guard()
