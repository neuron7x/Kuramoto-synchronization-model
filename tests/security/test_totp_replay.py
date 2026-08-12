# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Replay protection for admin TOTP second factor.

Regression for the HIGH finding: ``verify_totp_code`` is a pure RFC-6238 check
with no used-code tracking, so a captured code is replayable for the full
``period * (2*drift + 1)`` validity window. ``require_two_factor`` now records
each accepted ``(subject, counter)`` via ``TotpReplayGuard`` and rejects reuse.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from application.api.security import require_two_factor
from application.security.two_factor import (
    TotpReplayGuard,
    find_totp_counter,
    generate_totp_code,
    verify_totp_code,
)
from src.admin.remote_control import AdminIdentity

_SECRET = "JBSWY3DPEHPK3PXP"  # pragma: allowlist secret  # public pyotp example seed
_HEADER = "X-Admin-OTP"


# --- TotpReplayGuard unit behaviour --------------------------------------------


def test_guard_accepts_then_rejects_same_pair() -> None:
    now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    counter = int(now.timestamp()) // 30
    guard = TotpReplayGuard(period_seconds=30, drift_windows=1)
    assert guard.register("admin", counter, now=now) is True
    assert guard.register("admin", counter, now=now) is False  # replay


def test_guard_is_per_subject() -> None:
    now = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    guard = TotpReplayGuard(period_seconds=30, drift_windows=1)
    assert guard.register("admin-a", 100, now=now) is True
    # Different subject, same counter — independent, must be accepted.
    assert guard.register("admin-b", 100, now=now) is True


def test_guard_prunes_after_validity_window() -> None:
    guard = TotpReplayGuard(period_seconds=30, drift_windows=1)
    base = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert guard.register("admin", 100, now=base) is True
    # Within the validity window (period*(2*drift+1) = 90s) it is still a replay.
    assert guard.register("admin", 100, now=base + timedelta(seconds=89)) is False
    # Past the window the slot is pruned and the pair may be registered again.
    assert guard.register("admin", 100, now=base + timedelta(seconds=91)) is True


def test_guard_rejects_empty_subject() -> None:
    guard = TotpReplayGuard()
    with pytest.raises(ValueError, match="subject"):
        guard.register("", 1)


# --- find_totp_counter / verify_totp_code parity -------------------------------


def test_find_counter_matches_verify() -> None:
    now = datetime.now(timezone.utc)
    code = generate_totp_code(_SECRET, timestamp=now)
    assert verify_totp_code(_SECRET, code, timestamp=now) is True
    counter = find_totp_counter(_SECRET, code, timestamp=now)
    assert counter == int(now.timestamp()) // 30
    assert find_totp_counter(_SECRET, "000000", timestamp=now) is None or isinstance(
        find_totp_counter(_SECRET, "000000", timestamp=now), int
    )


# --- require_two_factor end-to-end replay rejection ----------------------------


def _make_request(headers: dict[str, str], method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/admin/kill-switch",
        "headers": [
            (key.lower().encode("ascii"), value.encode("utf-8"))
            for key, value in headers.items()
        ],
    }

    async def receive() -> dict[str, object]:  # pragma: no cover - not awaited
        return {"type": "http.request"}

    return Request(scope, receive)


async def _identity() -> AdminIdentity:
    return AdminIdentity(subject="admin-1", roles=("admin",))


@pytest.mark.asyncio
async def test_dependency_accepts_once_then_rejects_replay() -> None:
    moment = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    code = generate_totp_code(_SECRET, timestamp=moment)
    dependency = require_two_factor(
        secret_provider=lambda: _SECRET,
        header_name=_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        identity_dependency=_identity,
        clock=lambda: moment,
    )
    request = _make_request({_HEADER: code})

    identity = await dependency(request, identity=await _identity())
    assert identity.subject == "admin-1"

    # Same code, same window, same subject → replay must be rejected with 401.
    with pytest.raises(HTTPException) as exc:
        await dependency(request, identity=await _identity())
    assert exc.value.status_code == 401
    assert "already been used" in exc.value.detail


@pytest.mark.asyncio
async def test_safe_method_read_does_not_burn_code_then_write_succeeds() -> None:
    # A TOTP code is constant within its window. A read (GET) must verify but not
    # consume it, so the holder can still perform a write (POST) in the same
    # window with the same code; a SECOND write then replays and is rejected.
    moment = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    code = generate_totp_code(_SECRET, timestamp=moment)
    dependency = require_two_factor(
        secret_provider=lambda: _SECRET,
        header_name=_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        identity_dependency=_identity,
        clock=lambda: moment,
    )

    # GET: verified, not consumed (repeatable).
    await dependency(_make_request({_HEADER: code}, method="GET"), identity=await _identity())
    await dependency(_make_request({_HEADER: code}, method="GET"), identity=await _identity())

    # POST: first write with the same in-window code succeeds.
    identity = await dependency(
        _make_request({_HEADER: code}, method="POST"), identity=await _identity()
    )
    assert identity.subject == "admin-1"

    # Second write replays the now-consumed code → rejected.
    with pytest.raises(HTTPException) as exc:
        await dependency(_make_request({_HEADER: code}, method="POST"), identity=await _identity())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_dependency_allows_distinct_codes_in_new_windows() -> None:
    first = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)
    second = first + timedelta(seconds=90)
    guard = TotpReplayGuard(period_seconds=30, drift_windows=1)
    state = {"now": first}

    dependency = require_two_factor(
        secret_provider=lambda: _SECRET,
        header_name=_HEADER,
        digits=6,
        period_seconds=30,
        drift_windows=1,
        algorithm="SHA1",
        identity_dependency=_identity,
        clock=lambda: state["now"],
        replay_guard=guard,
    )

    code1 = generate_totp_code(_SECRET, timestamp=first)
    await dependency(_make_request({_HEADER: code1}), identity=await _identity())

    state["now"] = second
    code2 = generate_totp_code(_SECRET, timestamp=second)
    identity = await dependency(
        _make_request({_HEADER: code2}), identity=await _identity()
    )
    assert identity.subject == "admin-1"
