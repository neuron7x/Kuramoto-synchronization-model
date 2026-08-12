"""Tests for the long-running collector health monitor."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.microstructure.longrun_monitor import (
    DISCONNECTS_DEGRADED_PER_HOUR,
    HealthReport,
    parse_log_tail,
    read_log_tail,
)


def _line(ts: datetime, kind: str, payload: str) -> str:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S") + ",000"
    if kind == "flush":
        return f"{stamp} INFO binance_perp_l2 flushed {payload}"
    if kind == "drop":
        return f"{stamp} WARNING binance_perp_l2 connection dropped: {payload}"
    return f"{stamp} INFO binance_perp_l2 {payload}"


def test_parse_log_tail_healthy_under_recent_flush() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    text = "\n".join(
        [
            _line(now - timedelta(seconds=180), "flush", "4500 rows across 10 shards"),
            _line(now - timedelta(seconds=60), "flush", "4700 rows across 10 shards"),
        ]
    )
    r = parse_log_tail(text, now_utc=now)
    assert r.verdict == "HEALTHY"
    assert r.gap_sec == 60.0
    assert r.last_flush_rows == 4700
    assert r.disconnects_last_hour == 0


def test_parse_log_tail_degraded_on_old_flush() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    text = _line(now - timedelta(seconds=700), "flush", "4500 rows across 10 shards")
    r = parse_log_tail(text, now_utc=now)
    assert r.verdict == "DEGRADED"
    assert 600 <= r.gap_sec < 3600


def test_parse_log_tail_stale_after_hour() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    text = _line(now - timedelta(seconds=4000), "flush", "4500 rows across 10 shards")
    r = parse_log_tail(text, now_utc=now)
    assert r.verdict == "STALE"
    assert r.gap_sec >= 3600


def test_parse_log_tail_unreachable_on_empty_log() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    r = parse_log_tail("", now_utc=now)
    assert r.verdict == "UNREACHABLE"
    assert r.last_flush_ts_utc is None
    assert r.last_flush_rows is None


def test_parse_log_tail_counts_disconnects_and_dns() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    lines = [_line(now - timedelta(seconds=60), "flush", "5000 rows across 10 shards")]
    for k in range(3):
        lines.append(
            _line(now - timedelta(seconds=300 + k * 10), "drop", "ConnectionClosedError(None)")
        )
    for k in range(2):
        lines.append(
            _line(
                now - timedelta(seconds=1800 + k * 30),
                "drop",
                "gaierror(-3, 'Temporary failure in name resolution')",
            )
        )
    r = parse_log_tail("\n".join(lines), now_utc=now)
    assert r.verdict == "HEALTHY"  # gap 60s, disconnects 5 < 10 threshold
    assert r.disconnects_last_hour == 5
    assert r.dns_failures_last_hour == 2


def test_parse_log_tail_degraded_on_disconnect_storm_even_when_gap_low() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    lines = [_line(now - timedelta(seconds=30), "flush", "5000 rows across 10 shards")]
    for k in range(DISCONNECTS_DEGRADED_PER_HOUR + 2):
        lines.append(_line(now - timedelta(seconds=60 + k * 10), "drop", "OSError"))
    r = parse_log_tail("\n".join(lines), now_utc=now)
    assert r.verdict == "DEGRADED"
    assert r.disconnects_last_hour >= DISCONNECTS_DEGRADED_PER_HOUR
    assert r.gap_sec < 120


def test_parse_log_tail_ignores_disconnects_older_than_one_hour() -> None:
    now = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
    lines = [_line(now - timedelta(seconds=30), "flush", "5000 rows across 10 shards")]
    for k in range(20):
        lines.append(
            _line(
                now - timedelta(seconds=3600 + 60 + k * 10),
                "drop",
                "stale noise",
            )
        )
    r = parse_log_tail("\n".join(lines), now_utc=now)
    assert r.disconnects_last_hour == 0
    assert r.verdict == "HEALTHY"


def test_read_log_tail_handles_large_file(tmp_path: Path) -> None:
    log = tmp_path / "big.log"
    payload = "2026-04-18 12:00:00,000 INFO binance_perp_l2 flushed 1 rows across 10 shards\n"
    log.write_text(payload * 50000, encoding="utf-8")  # ~4MB
    text = read_log_tail(log, max_bytes=4096)
    assert len(text) <= 4096
    assert "flushed" in text


def test_read_log_tail_missing_file_returns_empty() -> None:
    with tempfile.TemporaryDirectory() as td:
        missing = Path(td) / "no-such-file.log"
        assert read_log_tail(missing) == ""


def test_health_report_schema_fields() -> None:
    r = HealthReport(
        verdict="HEALTHY",
        gap_sec=0.5,
        disconnects_last_hour=0,
        dns_failures_last_hour=0,
        last_flush_ts_utc="2026-04-18T12:00:00+00:00",
        last_flush_rows=4500,
        log_path="/tmp/x",
        reason=None,
    )
    assert r.verdict == "HEALTHY"
    assert r.last_flush_rows == 4500
    assert r.reason is None
