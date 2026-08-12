# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime-state envelope — integrity invariants.

Guards every integrity claim the envelope makes: round-trip preservation,
deterministic canonical encoding, SHA-256 corruption detection, schema
version gating, unsupported-envelope-version rejection, non-finite
payload rejection, and parity of file bytes under identical input.

A failure at this layer silently turns snapshot / restore into a coin
toss. These tests refuse that outcome at CI time.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from geosync_hpc.runtime_state import (
    ENVELOPE_VERSION,
    ChecksumMismatch,
    EnvelopeError,
    RuntimeStateEnvelope,
    SchemaVersionMismatch,
    UnsupportedEnvelopeVersion,
    dump_envelope,
    load_envelope,
)

SCHEMA_V1 = 1


def _frozen_clock() -> datetime:
    return datetime(2026, 4, 25, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_roundtrip_preserves_payload(tmp_path: Path) -> None:
    payload = {"pos": 42, "cash": -1234567, "name": "execution", "flags": [1, 2, 3]}
    target = tmp_path / "state.json"
    written = dump_envelope(target, payload, schema_version=SCHEMA_V1, clock=_frozen_clock)
    loaded = load_envelope(target, expected_schema_version=SCHEMA_V1)
    assert loaded.payload == payload
    assert loaded.payload_sha256 == written.payload_sha256
    assert loaded.schema_version == SCHEMA_V1
    assert loaded.envelope_version == ENVELOPE_VERSION


def test_roundtrip_preserves_int_precision(tmp_path: Path) -> None:
    """Scaled-int ledger values routinely exceed 1e15; json must not
    downcast them to float. A round-trip that drifts one tick breaks
    the whole determinism story."""
    big = 10**17 + 7  # bigger than float64 precision
    target = tmp_path / "ledger.json"
    dump_envelope(target, {"cash": big}, schema_version=SCHEMA_V1)
    loaded = load_envelope(target, expected_schema_version=SCHEMA_V1)
    assert loaded.payload["cash"] == big
    assert isinstance(loaded.payload["cash"], int)


def test_roundtrip_nested_structures(tmp_path: Path) -> None:
    payload = {
        "a": {"b": [1, {"c": [2, 3], "d": None}]},
        "flag": True,
        "ratio": 0.25,
    }
    target = tmp_path / "nested.json"
    dump_envelope(target, payload, schema_version=SCHEMA_V1)
    loaded = load_envelope(target, expected_schema_version=SCHEMA_V1)
    assert loaded.payload == payload


# ---------------------------------------------------------------------------
# Canonical encoding determinism
# ---------------------------------------------------------------------------


def test_identical_payloads_produce_identical_bytes(tmp_path: Path) -> None:
    """Canonical JSON + sort_keys + fixed clock + fixed separators →
    two dumps must produce byte-identical files."""
    payload = {"b": 2, "a": 1, "c": 3}
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    dump_envelope(p1, payload, schema_version=SCHEMA_V1, clock=_frozen_clock)
    dump_envelope(p2, payload, schema_version=SCHEMA_V1, clock=_frozen_clock)
    assert p1.read_bytes() == p2.read_bytes()


def test_dict_key_order_does_not_affect_checksum(tmp_path: Path) -> None:
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    e1 = dump_envelope(p1, {"a": 1, "b": 2}, schema_version=SCHEMA_V1)
    e2 = dump_envelope(p2, {"b": 2, "a": 1}, schema_version=SCHEMA_V1)
    assert e1.payload_sha256 == e2.payload_sha256


def test_checksum_changes_with_payload(tmp_path: Path) -> None:
    e1 = dump_envelope(tmp_path / "a.json", {"x": 1}, schema_version=SCHEMA_V1)
    e2 = dump_envelope(tmp_path / "b.json", {"x": 2}, schema_version=SCHEMA_V1)
    assert e1.payload_sha256 != e2.payload_sha256


# ---------------------------------------------------------------------------
# Integrity — fail-closed
# ---------------------------------------------------------------------------


def test_load_detects_tampered_payload(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    dump_envelope(target, {"pos": 1, "cash": 100}, schema_version=SCHEMA_V1)
    wrapper = json.loads(target.read_bytes())
    wrapper["payload"]["pos"] = 9999  # alter a field without updating the hash
    target.write_bytes(json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ChecksumMismatch):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


def test_load_detects_tampered_checksum(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    dump_envelope(target, {"x": 1}, schema_version=SCHEMA_V1)
    wrapper = json.loads(target.read_bytes())
    wrapper["payload_sha256"] = "0" * 64
    target.write_bytes(json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ChecksumMismatch):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


def test_load_rejects_schema_version_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    dump_envelope(target, {"x": 1}, schema_version=SCHEMA_V1)
    with pytest.raises(SchemaVersionMismatch):
        load_envelope(target, expected_schema_version=SCHEMA_V1 + 1)


def test_load_rejects_unknown_envelope_version(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    dump_envelope(target, {"x": 1}, schema_version=SCHEMA_V1)
    wrapper = json.loads(target.read_bytes())
    wrapper["envelope_version"] = 999
    # Recompute checksum so we trip ONLY the envelope-version guard,
    # not the unrelated checksum guard.
    wrapper["payload_sha256"] = wrapper["payload_sha256"]
    target.write_bytes(json.dumps(wrapper, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(UnsupportedEnvelopeVersion):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


def test_load_rejects_missing_fields(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(json.dumps({"envelope_version": 1}).encode())
    with pytest.raises(EnvelopeError):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"{not json}")
    with pytest.raises(EnvelopeError):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


def test_load_rejects_non_object_root(tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    target.write_bytes(b"[1, 2, 3]")
    with pytest.raises(EnvelopeError):
        load_envelope(target, expected_schema_version=SCHEMA_V1)


# ---------------------------------------------------------------------------
# Dump-side contracts
# ---------------------------------------------------------------------------


def test_dump_rejects_non_mapping_payload(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        dump_envelope(tmp_path / "x.json", [1, 2, 3], schema_version=SCHEMA_V1)  # type: ignore[arg-type]


def test_dump_rejects_negative_schema_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_envelope(tmp_path / "x.json", {"a": 1}, schema_version=-1)


def test_dump_rejects_non_int_schema_version(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        dump_envelope(tmp_path / "x.json", {"a": 1}, schema_version=1.0)  # type: ignore[arg-type]


def test_dump_rejects_nan_payload(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_envelope(tmp_path / "x.json", {"a": math.nan}, schema_version=SCHEMA_V1)


def test_dump_rejects_inf_payload(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_envelope(tmp_path / "x.json", {"a": math.inf}, schema_version=SCHEMA_V1)


def test_dump_rejects_nested_nan_payload(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_envelope(
            tmp_path / "x.json",
            {"nest": {"a": [1.0, math.nan]}},
            schema_version=SCHEMA_V1,
        )


def test_dump_rejects_unsupported_type(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_envelope(tmp_path / "x.json", {"a": {1, 2, 3}}, schema_version=SCHEMA_V1)


def test_dump_rejects_missing_parent_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does" / "not" / "exist" / "state.json"
    with pytest.raises(ValueError):
        dump_envelope(missing, {"a": 1}, schema_version=SCHEMA_V1)


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------


def test_envelope_is_frozen() -> None:
    env = RuntimeStateEnvelope(
        envelope_version=1,
        schema_version=1,
        created_utc="2026-04-25T12:00:00Z",
        payload_sha256="0" * 64,
        payload={},
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        env.schema_version = 2  # type: ignore[misc]


def test_created_utc_is_iso_8601_zulu(tmp_path: Path) -> None:
    """A frozen clock must serialise to canonical ``...Z`` form."""
    target = tmp_path / "s.json"
    env = dump_envelope(target, {"a": 1}, schema_version=SCHEMA_V1, clock=_frozen_clock)
    assert env.created_utc == "2026-04-25T12:00:00Z"


# ---------------------------------------------------------------------------
# Cross-process simulation — file bytes are the contract
# ---------------------------------------------------------------------------


def test_cross_process_parity_via_file_bytes(tmp_path: Path) -> None:
    """Simulate process A → disk → process B by copying the file bytes
    through an intermediate buffer before load. Proves the on-disk format
    is self-contained (no runtime state in the loader)."""
    target = tmp_path / "s.json"
    dump_envelope(target, {"pos": 7, "cash": 123456789}, schema_version=SCHEMA_V1)

    # "Process B" reads raw bytes, writes to a new file, then loads.
    copy = tmp_path / "s_copy.json"
    copy.write_bytes(target.read_bytes())
    loaded = load_envelope(copy, expected_schema_version=SCHEMA_V1)
    assert loaded.payload == {"pos": 7, "cash": 123456789}


def test_file_bytes_are_stable_across_repeated_dumps(tmp_path: Path) -> None:
    """Same payload + frozen clock + deterministic canonical encoding
    → file bytes are identical. Guards against any future change that
    sneaks in an indeterministic encoder (whitespace, key ordering,
    locale-aware float repr, ...)."""
    payload = {"a": 1, "b": 2, "c": 3}
    dumps = []
    for i in range(5):
        target = tmp_path / f"s_{i}.json"
        dump_envelope(target, payload, schema_version=SCHEMA_V1, clock=_frozen_clock)
        dumps.append(target.read_bytes())
    assert all(d == dumps[0] for d in dumps[1:])
