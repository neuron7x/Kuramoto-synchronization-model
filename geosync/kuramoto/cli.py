# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical wrapper entrypoint for tp-kuramoto (ADR-0024 wrapper-first).

The Kuramoto CLI/engine is a broad scientific subsystem (35 modules, 21 importers,
INV-routing); per issue #945 it MUST NOT be bulk-moved or behavior-modified under
packaging cleanup. This wrapper re-homes only the *public console-script target*
into the canonical ``geosync.*`` namespace and lazily delegates to the stable
``core.kuramoto.cli`` (which stays packaged + ledgered as BLOCKED_IMPORT_GRAPH).
Lazy import => no import-time side effects.
"""

from __future__ import annotations


def main() -> None:
    """Delegate to the stable core.kuramoto.cli entrypoint."""
    from core.kuramoto.cli import main as _main

    _main()


def cli() -> None:
    """Delegate to the stable core.kuramoto.cli click group."""
    from core.kuramoto.cli import cli as _cli

    _cli()
