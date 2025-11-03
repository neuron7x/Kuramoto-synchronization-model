# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for ledger corruption detection and read-only mode."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from execution.order_ledger import OrderLedger, OrderLedgerConfig


def test_corruption_detection_triggers_read_only_mode(tmp_path: Path) -> None:
    """Test that corruption detection sets ledger to read-only mode."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    # Create a ledger with some valid events
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    ledger.append("event2", state_snapshot={"orders": []})
    
    # Manually corrupt the ledger file by modifying a digest
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Corrupt the second event's digest
    if len(lines) >= 2:
        event = json.loads(lines[1])
        event["digest"] = "corrupted_digest_value"
        lines[1] = json.dumps(event) + "\n"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Reopen ledger - should detect corruption
    ledger2 = OrderLedger(ledger_path, config=config)
    
    assert ledger2.is_read_only
    assert ledger2.corruption_detected
    assert ledger2.corruption_details is not None
    assert "Digest mismatch" in ledger2.corruption_details
    
    # Attempt to append should raise error
    with pytest.raises(RuntimeError, match="read-only mode"):
        ledger2.append("event3", state_snapshot={"orders": []})


def test_corruption_action_truncate(tmp_path: Path) -> None:
    """Test that truncate action removes corrupted data."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="truncate")
    
    # Create a ledger with valid events
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    ledger.append("event2", state_snapshot={"orders": []})
    ledger.append("event3", state_snapshot={"orders": []})
    
    # Corrupt the third event
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    if len(lines) >= 3:
        event = json.loads(lines[2])
        event["digest"] = "corrupted"
        lines[2] = json.dumps(event) + "\n"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Reopen - should truncate at corruption point
    ledger2 = OrderLedger(ledger_path, config=config)
    
    # Should have detected corruption but not be read-only
    assert ledger2.corruption_detected
    assert not ledger2.is_read_only
    
    # Should only have 2 events (third was corrupted and truncated)
    events = list(ledger2.replay())
    assert len(events) == 2
    
    # Can still append new events
    ledger2.append("event4", state_snapshot={"orders": []})
    events = list(ledger2.replay())
    assert len(events) == 3


def test_corruption_action_abort(tmp_path: Path) -> None:
    """Test that abort action raises exception on corruption."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="abort")
    
    # Create a ledger with valid events
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    
    # Corrupt the event
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    event = json.loads(lines[0])
    event["digest"] = "corrupted"
    lines[0] = json.dumps(event) + "\n"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Reopen - should raise ValueError
    with pytest.raises(ValueError, match="Ledger corruption detected"):
        OrderLedger(ledger_path, config=config)


def test_broken_chain_detection(tmp_path: Path) -> None:
    """Test detection of broken digest chain."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    # Create ledger with events
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    ledger.append("event2", state_snapshot={"orders": []})
    
    # Break the chain by modifying previous_digest of second event
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    if len(lines) >= 2:
        event = json.loads(lines[1])
        event["previous_digest"] = "wrong_previous_digest"
        # Recompute digest for this corrupted event
        content = dict(event)
        del content["digest"]
        from hashlib import sha256
        digest = sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        event["digest"] = digest
        lines[1] = json.dumps(event) + "\n"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.writelines(lines)
    
    # Reopen - should detect broken chain
    ledger2 = OrderLedger(ledger_path, config=config)
    
    assert ledger2.corruption_detected
    assert "Broken digest chain" in ledger2.corruption_details


def test_json_decode_error_detection(tmp_path: Path) -> None:
    """Test detection of JSON decode errors."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    # Create valid event
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    
    # Append malformed JSON
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write("{ this is not valid json }\n")
    
    # Reopen - should detect JSON error
    ledger2 = OrderLedger(ledger_path, config=config)
    
    assert ledger2.corruption_detected
    assert "JSON decode error" in ledger2.corruption_details


def test_no_corruption_normal_operation(tmp_path: Path) -> None:
    """Test that normal ledger operations don't trigger corruption detection."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    ledger = OrderLedger(ledger_path, config=config)
    
    # Add many events
    for i in range(100):
        ledger.append(f"event{i}", state_snapshot={"orders": [i]})
    
    # Reopen
    ledger2 = OrderLedger(ledger_path, config=config)
    
    assert not ledger2.corruption_detected
    assert not ledger2.is_read_only
    assert ledger2.corruption_details is None
    
    # Verify all events are readable
    events = list(ledger2.replay())
    assert len(events) == 100


def test_read_only_properties(tmp_path: Path) -> None:
    """Test read-only property accessors."""
    ledger_path = tmp_path / "ledger.jsonl"
    config = OrderLedgerConfig(corruption_action="read_only")
    
    # Create and corrupt
    ledger = OrderLedger(ledger_path, config=config)
    ledger.append("event1", state_snapshot={"orders": []})
    
    with ledger_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    
    event = json.loads(lines[0])
    event["digest"] = "bad"
    
    with ledger_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    
    # Reopen and check properties
    ledger2 = OrderLedger(ledger_path, config=config)
    
    assert ledger2.is_read_only is True
    assert ledger2.corruption_detected is True
    assert isinstance(ledger2.corruption_details, str)
    assert len(ledger2.corruption_details) > 0
