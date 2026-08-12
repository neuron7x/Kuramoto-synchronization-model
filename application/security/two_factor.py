# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for generating and validating time-based one-time passwords (TOTP)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import string
import struct
import threading
from datetime import datetime, timezone
from typing import Callable

__all__ = [
    "TotpReplayGuard",
    "decode_totp_secret",
    "find_totp_counter",
    "generate_totp_code",
    "verify_totp_code",
]


_HASH_FACTORIES: dict[str, Callable[[], hashlib._Hash]] = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}


def _normalise_timestamp(timestamp: datetime | None) -> datetime:
    if timestamp is None:
        return datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _resolve_hash_factory(name: str) -> Callable[[], hashlib._Hash]:
    try:
        return _HASH_FACTORIES[name.upper()]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(
            "Unsupported TOTP algorithm. Choose from SHA1, SHA256, or SHA512."
        ) from exc


def decode_totp_secret(secret: str) -> bytes:
    """Decode a base32 encoded TOTP secret into raw key bytes."""

    if not secret:
        raise ValueError("Two-factor secret must not be empty")
    cleaned = secret.strip().upper().replace(" ", "").replace("-", "")
    if not cleaned:
        raise ValueError("Two-factor secret must contain base32 characters")
    allowed = set(string.ascii_uppercase + "234567=")
    if any(ch not in allowed for ch in cleaned):
        raise ValueError("Two-factor secret contains invalid base32 characters")
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    candidate = cleaned + padding
    try:
        key = base64.b32decode(candidate, casefold=True)
    except binascii.Error as exc:
        raise ValueError("Two-factor secret is not valid base32") from exc
    if len(key) < 10:
        raise ValueError("Two-factor secret must decode to at least 80 bits")
    return key


def _generate_hotp(secret: bytes, counter: int, digits: int, *, algorithm: str) -> str:
    if counter < 0:
        raise ValueError("Counter must be non-negative")
    if not (4 <= digits <= 10):
        raise ValueError("Digits must be between 4 and 10 for TOTP codes")
    hash_factory = _resolve_hash_factory(algorithm)
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(secret, counter_bytes, hash_factory).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    hotp = binary % (10**digits)
    return f"{hotp:0{digits}d}"


def generate_totp_code(
    secret: str | bytes,
    *,
    timestamp: datetime | None = None,
    period_seconds: int = 30,
    digits: int = 6,
    algorithm: str = "SHA1",
) -> str:
    """Generate the current TOTP code for *secret* at *timestamp*."""

    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")
    resolved_timestamp = _normalise_timestamp(timestamp)
    counter = int(resolved_timestamp.timestamp()) // period_seconds
    key = secret if isinstance(secret, bytes) else decode_totp_secret(secret)
    return _generate_hotp(key, counter, digits, algorithm=algorithm)


def _normalise_code(code: str, *, digits: int) -> str | None:
    candidate = "".join(ch for ch in code if ch.isdigit())
    if len(candidate) != digits:
        return None
    return candidate


def find_totp_counter(
    secret: str,
    code: str,
    *,
    timestamp: datetime | None = None,
    period_seconds: int = 30,
    digits: int = 6,
    drift_windows: int = 1,
    algorithm: str = "SHA1",
) -> int | None:
    """Return the time-step counter *code* matches under RFC 6238, else ``None``.

    Exposing the matched counter (not just a bool) lets callers enforce
    single-use: the same accepted code resolves to one counter, so a replay
    guard can reject a second use of that ``(subject, counter)`` pair.
    """

    if period_seconds <= 0:
        raise ValueError("period_seconds must be positive")
    if drift_windows < 0:
        raise ValueError("drift_windows must be non-negative")
    normalised_code = _normalise_code(code, digits=digits)
    if normalised_code is None:
        return None
    key = decode_totp_secret(secret)
    resolved_timestamp = _normalise_timestamp(timestamp)
    counter = int(resolved_timestamp.timestamp()) // period_seconds
    window_range = range(-drift_windows, drift_windows + 1)
    for offset in window_range:
        candidate_counter = counter + offset
        if candidate_counter < 0:
            continue
        expected = _generate_hotp(key, candidate_counter, digits, algorithm=algorithm)
        if hmac.compare_digest(expected, normalised_code):
            return candidate_counter
    return None


def verify_totp_code(
    secret: str,
    code: str,
    *,
    timestamp: datetime | None = None,
    period_seconds: int = 30,
    digits: int = 6,
    drift_windows: int = 1,
    algorithm: str = "SHA1",
) -> bool:
    """Return ``True`` when *code* is valid for *secret* under RFC 6238."""

    return (
        find_totp_counter(
            secret,
            code,
            timestamp=timestamp,
            period_seconds=period_seconds,
            digits=digits,
            drift_windows=drift_windows,
            algorithm=algorithm,
        )
        is not None
    )


class TotpReplayGuard:
    """In-process single-use ledger for accepted TOTP codes.

    A TOTP code validates across ``2*drift_windows + 1`` time steps, so without
    state a single captured code is replayable for up to
    ``period_seconds * (2*drift_windows + 1)`` seconds (e.g. ~90 s at 30 s/±1).
    This guard records each accepted ``(subject, counter)`` and rejects a second
    use within that validity window, then prunes expired entries.

    Process-local by design: it closes the single-instance replay window. A
    multi-process / multi-host deployment must back this with a shared store
    (e.g. Redis) keyed identically; that is deliberately out of scope here.
    """

    def __init__(self, *, period_seconds: int = 30, drift_windows: int = 1) -> None:
        if period_seconds <= 0:
            raise ValueError("period_seconds must be positive")
        if drift_windows < 0:
            raise ValueError("drift_windows must be non-negative")
        self._period_seconds = period_seconds
        self._drift_windows = drift_windows
        self._seen: dict[tuple[str, int], float] = {}
        self._lock = threading.Lock()

    def register(self, subject: str, counter: int, *, now: datetime | None = None) -> bool:
        """Record an accepted ``(subject, counter)``; return ``False`` on replay.

        Returns ``True`` when the pair is fresh (and records it), ``False`` when
        it was already consumed within its validity window.
        """

        if not subject:
            raise ValueError("subject must be a non-empty string")
        moment = _normalise_timestamp(now)
        epoch = moment.timestamp()
        # Retain for the full window a code can still validate, measured from
        # acceptance: period * (2*drift + 1). Measuring from `now` (not the
        # counter) keeps the guard correct regardless of the counter's absolute
        # magnitude and errs toward longer retention (stronger replay defence).
        expiry = epoch + float(self._period_seconds * (2 * self._drift_windows + 1))
        key = (subject, counter)
        with self._lock:
            self._prune(epoch)
            if key in self._seen:
                return False
            self._seen[key] = expiry
            return True

    def _prune(self, epoch: float) -> None:
        expired = [key for key, expiry in self._seen.items() if expiry <= epoch]
        for key in expired:
            del self._seen[key]
