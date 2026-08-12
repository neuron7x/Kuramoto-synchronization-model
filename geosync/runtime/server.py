# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical wrapper entrypoint for geosync-server (ADR-0024 wrapper-first).

The server is a broad runtime subsystem (93 application modules, FastAPI/TLS/
control-platform wiring with import-time side effects); per issue #945 it MUST
NOT be bulk-moved or behavior-modified under packaging cleanup. This wrapper
re-homes only the *public console-script target* into ``geosync.*`` and lazily
delegates to the stable ``application.runtime.server`` (which stays packaged +
ledgered as BLOCKED_IMPORT_GRAPH). Lazy import => no import-time side effects.
"""

from __future__ import annotations


def main() -> None:
    """Delegate to the stable application.runtime.server entrypoint."""
    from application.runtime.server import main as _main

    _main()
