#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Falsifier for the offline execution-forensics evidence boundary.

Black-box probes through the CLI only (no import of the module under test):
each probe states the refusal the contract promises. Exit 0 only when every
probe is refused exactly as contracted; the first probe the tool accepts, or
refuses for another reason, exits 1 and names itself. Nothing here proves the
arithmetic is right (the unit and property suites do that); this proves the
boundary still refuses.

    python scripts/ci/execution_forensics_falsifier.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "execution_forensics" / "fills_sample.csv"
EXACT_DIGITS = 50  # the module's exact-arithmetic budget; a change here is a contract change


class Falsified(AssertionError):
    """A probe the boundary should have refused was accepted."""


def _cli(*args: str) -> tuple[int, str, str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    proc = subprocess.run(  # nosec B603 - explicit argv, no shell
        [sys.executable, "-m", "tools.execution_forensics", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _expect(condition: bool, probe: str, detail: str) -> None:
    if not condition:
        raise Falsified(f"{probe}: {detail}")


def _headers() -> list[str]:
    return SAMPLE.read_text(encoding="utf-8").splitlines()[0].split(",")


def _row(**changes: str) -> dict[str, str]:
    base = dict(zip(_headers(), SAMPLE.read_text(encoding="utf-8").splitlines()[1].split(",")))
    base.update(changes)
    return base


def _csv(*rows: dict[str, str], header: Sequence[str] | None = None) -> bytes:
    columns = list(header or _headers())
    lines = [",".join(columns), *(",".join(row[h] for h in columns) for row in rows)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _run_on(work: Path, probe: str, raw: bytes) -> tuple[int, str, str]:
    path = work / f"{probe}.csv"
    path.write_bytes(raw)
    return _cli("--fills", str(path))


def _expect_refused(work: Path, probe: str, raw: bytes, fragment: str) -> None:
    code, _, err = _run_on(work, probe, raw)
    _expect(code == 2, probe, f"exit {code}: accepted or wrong error class")
    _expect(fragment in err, probe, f"refused for another reason: {err.strip()}")


def _report(work: Path, probe: str, raw: bytes) -> dict[str, object]:
    code, out, err = _run_on(work, probe, raw)
    _expect(code == 0, probe, f"exit {code}: {err.strip()}")
    loaded: dict[str, object] = json.loads(out)
    return loaded


def _group(report: dict[str, object]) -> dict[str, object]:
    groups = report["groups"]
    assert isinstance(groups, list)
    first: dict[str, object] = groups[0]
    return first


def probe_replay_chain(work: Path) -> None:
    fills = work / "fills.csv"
    fills.write_bytes(SAMPLE.read_bytes())
    report = work / "report.json"
    code, out, err = _cli("--fills", str(fills), "--out", str(report))
    _expect(code == 0, "create", f"exit {code}: {err}")
    code, out, err = _cli("--fills", str(fills), "--verify", str(report))
    _expect(code == 0 and "PASS" in out, "verify-clean", f"exit {code}: {err}")

    code, _, err = _cli("--fills", str(fills), "--out", str(report))
    _expect(code == 2, "no-overwrite", f"exit {code}: report was overwritten or error class wrong")

    before = fills.read_bytes()
    code, _, err = _cli("--fills", str(fills), "--out", str(fills))
    _expect(code == 2 and fills.read_bytes() == before, "no-self-overwrite", f"exit {code}: {err}")

    fills.write_bytes(before.replace(b"60010", b"60011"))
    code, _, err = _cli("--fills", str(fills), "--verify", str(report))
    _expect(code == 3 and "source_sha256 differs" in err, "tampered-source", f"exit {code}: {err}")
    fills.write_bytes(before)

    saved = json.loads(report.read_text(encoding="utf-8"))
    saved["report_sha256"] = "0" * 64
    forged = work / "forged.json"
    forged.write_text(json.dumps(saved), encoding="utf-8")
    code, _, err = _cli("--fills", str(fills), "--verify", str(forged))
    _expect(code == 3 and "digest does not match" in err, "forged-digest", f"exit {code}: {err}")

    saved = json.loads(report.read_text(encoding="utf-8"))
    saved["groups"][0]["fee_quote_total"] = "0"  # digest left stale on purpose
    edited = work / "edited.json"
    edited.write_text(json.dumps(saved), encoding="utf-8")
    code, _, err = _cli("--fills", str(fills), "--verify", str(edited))
    _expect(code == 3, "edited-total", f"exit {code}: a rewritten total passed replay")

    corrupt = work / "corrupt.json"
    corrupt.write_text("{", encoding="utf-8")
    code, _, err = _cli("--fills", str(fills), "--verify", str(corrupt))
    _expect(code == 3 and "unreadable" in err, "corrupt-report", f"exit {code}: {err}")

    code, _, err = _cli("--fills", str(work / "absent.csv"))
    _expect(code == 2, "absent-source", f"exit {code}: {err}")


def probe_fabrication_is_refused(work: Path) -> None:
    unsourced = _group(
        _report(
            work,
            "unsourced-fee",
            _csv(
                _row(
                    fee_asset="BNB",
                    fee_amount="0.001",
                    fee_quote_value="",
                    fee_conversion_source="",
                )
            ),
        )
    )
    _expect(
        unsourced["fee_quote_total"] is None,
        "unsourced-fee",
        f"valued as {unsourced['fee_quote_total']!r}",
    )
    _expect(
        unsourced["execution_shortfall_plus_fees_quote"] is None,
        "unsourced-fee-cost",
        "cost not null",
    )
    _expect(
        unsourced["evidence_state"] == "PARTIAL_UNKNOWN_COST",
        "unsourced-fee-state",
        str(unsourced["evidence_state"]),
    )

    no_arrival = _group(
        _report(
            work, "no-arrival", _csv(_row(arrival_price="", arrival_at_utc="", arrival_source=""))
        )
    )
    _expect(no_arrival["arrival_slippage_quote"] is None, "no-arrival", "slippage not null")

    _expect_refused(
        work, "future-arrival", _csv(_row(arrival_at_utc="2026-10-20T10:00:02Z")), "future"
    )
    _expect_refused(
        work, "scientific-quantity", _csv(_row(quantity="1e-1")), "non-canonical decimal"
    )
    _expect_refused(
        work,
        "offset-timestamp",
        _csv(_row(executed_at_utc="2026-10-20T12:00:01+02:00")),
        "timestamp",
    )
    _expect_refused(work, "date-only", _csv(_row(executed_at_utc="2026-10-20Z")), "timestamp")
    _expect_refused(work, "negative-fee", _csv(_row(fee_amount="-0.6")), "non-canonical decimal")
    _expect_refused(
        work,
        "unsourced-cross-valuation",
        _csv(
            _row(
                fee_asset="BNB", fee_amount="0.001", fee_quote_value="0.3", fee_conversion_source=""
            )
        ),
        "coexist",
    )
    _expect_refused(
        work,
        "orphan-arrival-source",
        _csv(_row(arrival_price="", arrival_at_utc="", arrival_source="x")),
        "orphan",
    )
    _expect_refused(work, "duplicate-trade", _csv(_row(), _row()), "duplicate trade")
    _expect_refused(
        work,
        "conflicting-arrival",
        _csv(_row(), _row(trade_id="EXAMPLE_T9", arrival_price="60001")),
        "conflicting arrival",
    )
    wide = "1." + "3" * (EXACT_DIGITS - 1)
    _expect_refused(
        work, "rounded-arithmetic", _csv(_row(quantity=wide, price="7.7")), "exact arithmetic"
    )
    _expect_refused(work, "header-order", _csv(_row(), header=list(reversed(_headers()))), "order")
    _expect_refused(work, "empty-source", b"", "empty")


PROBES: Sequence[tuple[str, Callable[[Path], None]]] = (
    ("replay chain", probe_replay_chain),
    ("fabrication refused", probe_fabrication_is_refused),
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="geosync-forensics-falsifier-") as tmp:
        for name, probe in PROBES:
            try:
                probe(Path(tmp))
            except Falsified as exc:
                print(f"FALSIFIED [{name}] {exc}", file=sys.stderr)
                return 1
            print(f"refused as contracted: {name}")
    print(f"PASS: {len(PROBES)} probe groups, every fabrication refused")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
