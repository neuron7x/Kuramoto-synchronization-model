# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed exceptions raised by the cognitive bridge.

Each error carries the originating ``InvariantId`` (when applicable) so the
audit log and host telemetry can attribute the failure to a specific
fail-closed contract.
"""

from __future__ import annotations


class BridgeError(RuntimeError):
    """Base class for all cognitive-bridge faults."""


class BridgeInvariantError(BridgeError):
    """A bridge invariant (CB-INV-*) was violated.

    The host MUST treat this as fail-closed: drop the advisory output,
    record the violation in the audit log, and continue with the
    deterministic baseline.
    """

    def __init__(self, invariant_id: str, message: str) -> None:
        super().__init__(f"[{invariant_id}] {message}")
        self.invariant_id = invariant_id


class BridgeTimeoutError(BridgeError):
    """The cognitive sidecar did not respond within the configured budget."""


class BridgeTransportError(BridgeError):
    """The transport layer failed (network, schema, codec)."""
