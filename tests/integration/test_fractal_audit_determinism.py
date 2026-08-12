# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Refutation harness for the fractal-audit hypothesis (formal/micro_dynamic_bug_fractal_audit.md).

Closes the §2 refutation condition for Class A / Class D edges that this PR
migrated to the injected ``Clock``:

* ``runtime.kill_switch.KillSwitchManager`` (cooldown, persist payload, audit
  event timestamp).
* ``runtime.rebus_gate.utc_now`` (delegated to ``geosync.core.compat.utc_now``).
* ``core.neuro.cryptobiosis.CryptobiosisGate`` (vitrification entry timestamp).

Each test runs two replays under a fresh ``FrozenClock`` and asserts byte-equal
state for the migrated wall-clock readings. A regression would re-introduce a
stdlib call that bypasses the Clock and produce non-identical traces.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from core.neuro.cryptobiosis import CryptobiosisConfig, CryptobiosisController
from geosync.core.compat import UTC, FrozenClock, use_clock
from runtime import rebus_gate as rebus_gate_module
from runtime.kill_switch import KillSwitchManager, KillSwitchReason


def _kill_switch_trace(persist_path: Path) -> tuple[float, ...]:
    """Drive a fresh KillSwitchManager and return the timestamps observed."""

    manager = KillSwitchManager(
        cooldown_seconds=0.0,
        max_audit_entries=8,
        persist_path=persist_path,
        _force_new=True,
    )
    manager.activate(reason=KillSwitchReason.MANUAL, source="determinism-test")
    manager.deactivate(reason="manual_deactivation", source="determinism-test")
    status_active_count = manager.get_status()["total_activations"]
    audit_timestamps = tuple(event["timestamp"] for event in manager.get_audit_log())
    assert status_active_count == 1
    return audit_timestamps


def test_kill_switch_audit_trace_is_clock_deterministic(tmp_path: Path) -> None:
    """Two replays under identical FrozenClocks must produce identical audit traces."""

    persist_a = tmp_path / "ks_a.json"
    persist_b = tmp_path / "ks_b.json"

    with use_clock(FrozenClock(instant=datetime(2026, 1, 1, tzinfo=UTC))):
        trace_a = _kill_switch_trace(persist_a)
    with use_clock(FrozenClock(instant=datetime(2026, 1, 1, tzinfo=UTC))):
        trace_b = _kill_switch_trace(persist_b)

    assert trace_a == trace_b, (
        "kill_switch audit timestamps drifted under FrozenClock — a wall-clock "
        "read bypasses default_clock(). Re-check runtime/kill_switch.py."
    )
    # And the timestamp must equal the frozen instant in epoch-seconds.
    expected = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    for ts in trace_a:
        assert ts == pytest.approx(expected, abs=1e-9)


def test_rebus_gate_utc_now_routes_through_clock() -> None:
    """``runtime.rebus_gate.utc_now`` must observe the injected FrozenClock."""

    instant = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)
    with use_clock(FrozenClock(instant=instant)):
        observed = rebus_gate_module.utc_now()
    assert (
        observed == instant
    ), "rebus_gate.utc_now() did not honor FrozenClock — Class A regression."


def test_cryptobiosis_vitrification_timestamp_is_clock_bound() -> None:
    """Vitrification snapshot timestamp must come from the injected Clock."""

    instant = datetime(2026, 3, 14, tzinfo=UTC)
    epoch_expected = instant.timestamp()

    cfg = CryptobiosisConfig(
        entry_threshold=0.5,
        exit_threshold=0.3,
        n_rehydration_stages=2,
    )
    controller = CryptobiosisController(cfg)

    with use_clock(FrozenClock(instant=instant)):
        controller.update(0.99, metadata={"src": "test"})

    snapshot = controller.snapshot
    assert snapshot is not None
    snapshot_dict = asdict(snapshot)
    assert snapshot_dict["entry_timestamp"] == pytest.approx(epoch_expected, abs=1e-9), (
        "cryptobiosis vitrification timestamp drifted from FrozenClock — "
        "Class A regression in core/neuro/cryptobiosis.py."
    )
