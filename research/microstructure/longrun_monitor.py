"""Health monitor for the long-running L2 collector.

Parses the collector's log tail and emits structured health metrics:

    * last_flush_ts         — timestamp of most recent successful flush
    * gap_sec               — seconds since last successful flush
    * disconnects_last_hour — count of `connection dropped` in last 3600s
    * dns_failures_last_hour — gaierror subclass of disconnects
    * rows_last_flush       — row count of the last flushed shard batch
    * verdict               — HEALTHY | DEGRADED | STALE | UNREACHABLE

Zero network calls; read-only on log file. Designed for cron / systemd
watchdog invocation and for tests on synthetic log fixtures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_TS_FMT = "%Y-%m-%d %H:%M:%S"
_TS_LEN = 19  # len("YYYY-MM-DD HH:MM:SS"), NOT len(_TS_FMT) which counts % directives
_FLUSH_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+\S+\s+flushed\s+(?P<rows>\d+)\s+rows"
)
_DROP_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+WARNING\s+\S+\s+connection dropped"
)
_DNS_RE = re.compile(r"gaierror")

GAP_HEALTHY_SEC: int = 120
GAP_DEGRADED_SEC: int = 600
GAP_STALE_SEC: int = 3600
DISCONNECTS_DEGRADED_PER_HOUR: int = 10


@dataclass(frozen=True)
class HealthReport:
    verdict: str
    gap_sec: float
    disconnects_last_hour: int
    dns_failures_last_hour: int
    last_flush_ts_utc: str | None
    last_flush_rows: int | None
    log_path: str
    reason: str | None


def _parse_line_timestamp(line: str) -> datetime | None:
    if len(line) < _TS_LEN:
        return None
    try:
        return datetime.strptime(line[:_TS_LEN], _TS_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_log_tail(text: str, now_utc: datetime) -> HealthReport:
    """Parse up-to-N-lines of collector log and produce a HealthReport.

    The caller is responsible for reading the tail of the log file and
    passing the text in; this keeps the module IO-free and testable.
    """
    last_flush_ts: datetime | None = None
    last_flush_rows: int | None = None
    disconnects: int = 0
    dns_failures: int = 0
    cutoff = now_utc.timestamp() - 3600.0

    for line in text.splitlines():
        flush_match = _FLUSH_RE.match(line)
        if flush_match:
            ts = _parse_line_timestamp(line)
            if ts is not None and (last_flush_ts is None or ts > last_flush_ts):
                last_flush_ts = ts
                last_flush_rows = int(flush_match.group("rows"))
            continue
        drop_match = _DROP_RE.match(line)
        if drop_match:
            ts = _parse_line_timestamp(line)
            if ts is None:
                continue
            if ts.timestamp() >= cutoff:
                disconnects += 1
                if _DNS_RE.search(line):
                    dns_failures += 1

    if last_flush_ts is None:
        return HealthReport(
            verdict="UNREACHABLE",
            gap_sec=float("inf"),
            disconnects_last_hour=disconnects,
            dns_failures_last_hour=dns_failures,
            last_flush_ts_utc=None,
            last_flush_rows=None,
            log_path="",
            reason="no flush line found in log tail",
        )

    gap_sec = max(0.0, now_utc.timestamp() - last_flush_ts.timestamp())

    reasons: list[str] = []
    if gap_sec >= GAP_STALE_SEC:
        verdict = "STALE"
        reasons.append(f"gap_sec={gap_sec:.0f} >= STALE threshold {GAP_STALE_SEC}")
    elif gap_sec >= GAP_DEGRADED_SEC:
        verdict = "DEGRADED"
        reasons.append(f"gap_sec={gap_sec:.0f} >= DEGRADED threshold {GAP_DEGRADED_SEC}")
    elif disconnects >= DISCONNECTS_DEGRADED_PER_HOUR:
        verdict = "DEGRADED"
        reasons.append(
            f"disconnects_last_hour={disconnects} >= threshold {DISCONNECTS_DEGRADED_PER_HOUR}"
        )
    elif gap_sec >= GAP_HEALTHY_SEC:
        verdict = "DEGRADED"
        reasons.append(f"gap_sec={gap_sec:.0f} >= HEALTHY threshold {GAP_HEALTHY_SEC}")
    else:
        verdict = "HEALTHY"

    return HealthReport(
        verdict=verdict,
        gap_sec=gap_sec,
        disconnects_last_hour=disconnects,
        dns_failures_last_hour=dns_failures,
        last_flush_ts_utc=last_flush_ts.isoformat(timespec="seconds"),
        last_flush_rows=last_flush_rows,
        log_path="",
        reason=" ; ".join(reasons) if reasons else None,
    )


def read_log_tail(path: Path, max_bytes: int = 256 * 1024) -> str:
    """Read the last `max_bytes` of a log file (safe on very large files)."""
    if not path.exists():
        return ""
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > max_bytes:
            fh.seek(size - max_bytes)
            fh.readline()  # skip potentially partial first line
        data = fh.read()
    return data.decode("utf-8", errors="replace")
