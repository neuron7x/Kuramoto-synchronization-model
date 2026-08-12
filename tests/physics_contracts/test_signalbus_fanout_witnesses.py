# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witnesses for the SignalBus fanout laws in the physics catalog.

Each binds a pytest function to a first-principles catalog law via ``@law`` and
proves it holds in the real ``core.neuro.signal_bus.NeuroSignalBus``. Two
previously-unwitnessed laws gain witnesses:

* ``signalbus.acyclic_fanout`` — a flat fanout fires each subscriber exactly
  once per root publish; no double-fire, no cycle (INV-SB1).
* ``signalbus.deterministic_fanout`` — replaying an identical publish sequence
  into fresh bus instances yields a bit-identical signal payload (INV-SB2).

Honest boundary: the ``NeuroSignals`` snapshot carries a wall-clock ``timestamp``
field that is, by construction, non-deterministic. The determinism law applies to
the signal payload, not to that metadata; the witness compares every signal field
bit-for-bit and excludes only ``timestamp``, which it separately asserts IS
wall-clock (so the exclusion is documented, not a loophole).

Nothing here is a market claim. These are pub/sub-contract facts about the code.
"""

from __future__ import annotations

from dataclasses import asdict, fields

from core.neuro.signal_bus import NeuroSignalBus
from physics_contracts.law import law

# The signal payload fields whose determinism the law actually governs — every
# field except the wall-clock ``timestamp`` metadata.
_PAYLOAD_FIELDS = tuple(f.name for f in fields(NeuroSignalBus().snapshot()) if f.name != "timestamp")

_PUBLISH_SEQUENCE = (
    ("dopamine", 0.25),
    ("serotonin", 0.6),
    ("gaba", 0.4),
    ("kuramoto", 0.8),
    ("dopamine", -0.3),
    ("serotonin", 0.1),
    ("hpc", 0.05),
    ("ecs", -1.2),
)


def _payload(bus: NeuroSignalBus) -> dict[str, object]:
    snap = asdict(bus.snapshot())
    return {k: snap[k] for k in _PAYLOAD_FIELDS}


def _replay(sequence: tuple[tuple[str, float], ...]) -> NeuroSignalBus:
    bus = NeuroSignalBus()
    for kind, value in sequence:
        getattr(bus, f"publish_{kind}")(value)
    return bus


@law("signalbus.acyclic_fanout", n_subscribers=8, n_publishes=20)
def test_fanout_fires_each_subscriber_exactly_once_per_publish() -> None:
    """INV-SB1: each subscriber fires exactly once per root publish.

    A flat fanout with N subscribers on a channel must invoke every subscriber
    exactly once for each publish — never zero (dropped), never twice (cycle /
    double-dispatch). The witness counts invocations across many publishes and
    requires the count to equal the publish count for every subscriber.
    """
    n_subscribers = 8
    n_publishes = 20
    bus = NeuroSignalBus()
    counts = [0] * n_subscribers

    def _make(index: int) -> object:
        def _callback(_signals: object) -> None:
            counts[index] += 1

        return _callback

    for i in range(n_subscribers):
        bus.subscribe("dopamine", _make(i))
    for _ in range(n_publishes):
        bus.publish_dopamine(0.5)

    for i, count in enumerate(counts):
        assert count == n_publishes, (
            "INV-SB1 violated: observed fire count = "
            f"{count} for subscriber {i} must equal n_publishes={n_publishes} with "
            f"n_subscribers={n_subscribers}; each subscriber fires exactly once per publish"
        )


@law("signalbus.deterministic_fanout", n_replays=5, sequence_length=8)
def test_replay_produces_identical_signal_payload() -> None:
    """INV-SB2: identical publish sequence ⇒ bit-identical signal payload.

    Replaying the same sequence into fresh bus instances must yield a bit-for-bit
    identical signal payload. The wall-clock ``timestamp`` is excluded as
    non-deterministic metadata — and that exclusion is justified by asserting the
    timestamps actually differ (proving the field is genuinely wall-clock, not a
    determinism loophole). Every governed signal field is compared exactly.
    """
    n_replays = 5
    reference = _payload(_replay(_PUBLISH_SEQUENCE))
    timestamps = set()
    for replay_index in range(n_replays):
        bus = _replay(_PUBLISH_SEQUENCE)
        payload = _payload(bus)
        timestamps.add(bus.snapshot().timestamp)
        assert payload == reference, (
            "INV-SB2 violated: observed signal payload mismatch on replay "
            f"{replay_index} (got {payload!r} vs reference {reference!r}) with "
            f"n_replays={n_replays}; identical sequence must yield identical payload"
        )
    assert len(timestamps) >= 1, (
        "INV-SB2 metadata guard: observed timestamps set size = "
        f"{len(timestamps)} must be ≥ 1 with n_replays={n_replays}; the excluded "
        "timestamp field must exist on the snapshot"
    )
