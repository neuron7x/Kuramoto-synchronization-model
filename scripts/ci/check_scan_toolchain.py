#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verify the security-scan toolchain is pinned + hashed (SEC-002).

A vulnerability scan is only trustworthy if the *scanner itself* is a known,
fixed artifact. If ``pip-audit`` is resolved "latest-at-runtime" (an unpinned
``pip-audit`` / ``pip-audit>=x`` line, or absent from the lock), then the audit
result is unreproducible and an attacker (or a broken index) can silently swap
the auditor. This gate answers two fail-closed questions:

1. **Toolchain pinning** — does ``requirements-scan.lock`` pin ``pip-audit``
   (and ``pip``) to an *exact* ``==`` version carrying at least one well-formed
   ``--hash=sha256:<64-hex>`` entry? An unpinned / range / hash-less scanner
   line is a HARD failure. No "latest-at-runtime" auditor is admissible.

2. **Outcome honesty** — a scan run that could not actually reach the advisory
   database (offline, network error, non-zero auditor exit, missing result)
   must NEVER be classified GREEN. ``classify_scan_outcome`` fails closed to
   ``RED``/``MANUAL``; ``is_false_green`` flags any record that *claims* GREEN
   while the true classification is not GREEN.

Design notes
------------
* ``verify_scan_toolchain`` and ``classify_scan_outcome`` are pure functions
  over text / a plain dict, so tests can feed doctored fixtures (a ``pip-audit``
  with no ``==``, a ``pip-audit>=x`` range, an offline-but-GREEN record) and
  assert the gate fails closed. No filesystem or network needed to test them.
* This gate NEVER regenerates a lock and NEVER runs pip-audit. It reads the
  committed scan lock and (optionally) writes a provenance receipt. Regenerating
  the lock is the controlled ``pip-compile --allow-unsafe`` step documented in
  ``docs/SCAN_TOOLCHAIN_POLICY.md``.

Exit codes
----------
0  -- the scan lock pins every required tool to an exact hashed version.
1  -- any required tool is missing / unpinned / range / hash-less (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_ID = "G-SCAN-TOOLCHAIN"

DEFAULT_SCAN_LOCK = "requirements-scan.lock"

# Tools whose exact pin+hash is MANDATORY (the scanner and its runner). pip-audit
# is the auditor itself; pip is what executes the audited install/resolution.
REQUIRED_HASHED = ("pip-audit",)
# Tools that must at least be pinned with ``==`` (pip is a build backend that the
# lock now pins+hashes under --allow-unsafe, so we also require it hashed below).
REQUIRED_PINNED = ("pip-audit", "pip")

SHA256_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?![0-9a-fA-F])")
REQ_SPEC_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[A-Za-z0-9,._\-]+\])?"
    r"\s*(?P<op>===|==|~=|!=|<=|>=|<|>)?"
    r"\s*(?P<version>[^\s;\\]+)?"
)
DIRECTIVE_PREFIXES = ("-c ", "-r ", "-e ", "--", "-C", "-f ", "-i ")


def _canonical(name: str) -> str:
    """PEP 503 normalization so ``pip-audit`` and ``pip_audit`` are one key."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class ToolPin:
    name: str
    operator: str | None
    version: str | None
    hashes: list[str] = field(default_factory=list)
    line_no: int = 0

    @property
    def is_exact(self) -> bool:
        return self.operator in ("==", "===") and bool(self.version)

    @property
    def is_hashed(self) -> bool:
        return bool(self.hashes)


@dataclass
class ScanToolReport:
    path: str
    exists: bool
    pins: dict[str, ToolPin] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and not self.errors


def _iter_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Group a requirements file into (start_line_no, block_lines)."""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    start = 0
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace():
            if current is not None:
                current.append(raw)
            continue
        if current is not None:
            blocks.append((start, current))
        current = [raw]
        start = idx
    if current is not None:
        blocks.append((start, current))
    return blocks


def parse_pins(text: str) -> dict[str, ToolPin]:
    """Parse a requirements-lock's text into ``canonical name -> ToolPin``."""
    pins: dict[str, ToolPin] = {}
    for start, block in _iter_blocks(text):
        head = block[0].strip()
        if head.startswith(DIRECTIVE_PREFIXES):
            continue
        m = REQ_SPEC_RE.match(head)
        if not m or not m.group("name"):
            continue
        block_text = "\n".join(block)
        name = _canonical(m.group("name"))
        pins[name] = ToolPin(
            name=name,
            operator=m.group("op"),
            version=m.group("version"),
            hashes=SHA256_HASH_RE.findall(block_text),
            line_no=start,
        )
    return pins


def verify_scan_toolchain(
    text: str,
    *,
    path: str = "<memory>",
    required_hashed: tuple[str, ...] = REQUIRED_HASHED,
    required_pinned: tuple[str, ...] = REQUIRED_PINNED,
) -> ScanToolReport:
    """Pure verifier: the scan lock must pin every required tool fail-closed.

    A required tool that is absent, not ``==`` pinned (an unpinned / range /
    operator-less "latest-at-runtime" line), or -- for ``required_hashed`` --
    carries no sha256 hash, is recorded as a HARD error.
    """
    report = ScanToolReport(path=path, exists=True, pins=parse_pins(text))

    for raw in {*required_hashed, *required_pinned}:
        key = _canonical(raw)
        pin = report.pins.get(key)
        if pin is None:
            report.errors.append(
                f"required scan tool {raw!r} is ABSENT from the lock "
                f"(fail-closed: the scanner must be pinned, never latest-at-runtime)"
            )
            continue
        if not pin.is_exact:
            report.errors.append(
                f"line {pin.line_no}: scan tool {raw!r} is not exactly pinned "
                f"(operator {pin.operator!r}, version {pin.version!r}); "
                f"'latest-at-runtime' auditors are inadmissible -- require '=='"
            )
        if _canonical(raw) in {_canonical(n) for n in required_hashed} and not pin.is_hashed:
            report.errors.append(
                f"line {pin.line_no}: scan tool {raw!r} carries no --hash=sha256: "
                f"entry (fail-closed: not installable under pip --require-hashes)"
            )
    return report


def verify_scan_toolchain_file(path: Path) -> ScanToolReport:
    if not path.exists():
        return ScanToolReport(path=str(path), exists=False, errors=[f"missing scan lock: {path}"])
    return verify_scan_toolchain(path.read_text(encoding="utf-8"), path=str(path))


# --------------------------------------------------------------------------- #
# Outcome honesty: an offline / failed scan must never be a false GREEN.       #
# --------------------------------------------------------------------------- #
GREEN = "GREEN"
RED = "RED"
MANUAL = "MANUAL"


def classify_scan_outcome(record: dict[str, object]) -> str:
    """Fail-closed classification of a scan RUN's outcome.

    ``GREEN`` is returned ONLY when the auditor demonstrably ran end-to-end
    against the advisory database and found nothing:

        online is True AND db_reachable is not False AND exit_code == 0
        AND error is falsy AND vulnerabilities_found == 0.

    Any deviation -- offline, unreachable DB, a non-zero/absent exit code, an
    error string, or a positive finding -- fails closed. A run explicitly marked
    ``requires_manual`` degrades to ``MANUAL``; every other failure is ``RED``.
    The *claimed* ``status`` field is deliberately ignored here: this function
    computes the TRUE verdict from evidence, so a lying record cannot pass.
    """
    if record.get("requires_manual") is True:
        return MANUAL

    online = record.get("online", None)
    db_reachable = record.get("db_reachable", None)
    exit_code = record.get("exit_code", None)
    error = record.get("error", None)
    vulns = record.get("vulnerabilities_found", None)

    if online is False or db_reachable is False:
        return RED  # could not reach the advisory DB -> cannot assert clean
    if error:
        return RED
    if exit_code != 0:
        return RED
    if online is not True:
        # no positive evidence the auditor actually reached the network
        return RED
    if not isinstance(vulns, int):
        return RED
    if vulns > 0:
        return RED
    return GREEN


def is_false_green(record: dict[str, object]) -> bool:
    """True iff a record *claims* GREEN but the fail-closed verdict is not GREEN."""
    claimed = str(record.get("status", "")).upper()
    return claimed == GREEN and classify_scan_outcome(record) != GREEN


def build_receipt(report: ScanToolReport) -> dict[str, object]:
    """Machine-readable receipt: the pinned scanner version + digests (SEC-002)."""
    tools: dict[str, object] = {}
    for name, pin in sorted(report.pins.items()):
        if name in {_canonical(n) for n in {*REQUIRED_HASHED, *REQUIRED_PINNED}}:
            tools[name] = {
                "version": pin.version,
                "operator": pin.operator,
                "sha256": sorted(pin.hashes),
                "exact_pin": pin.is_exact,
                "hashed": pin.is_hashed,
            }
    try:
        rel = Path(report.path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        rel = report.path
    return {
        "gate_id": GATE_ID,
        "schema": "scan_toolchain_receipt/v1",
        "generated_by": "scripts/ci/check_scan_toolchain.py",
        "requirement": "SEC-002",
        "scan_lock": rel,
        "scan_lock_exists": report.exists,
        "required_hashed": sorted(_canonical(n) for n in REQUIRED_HASHED),
        "required_pinned": sorted(_canonical(n) for n in REQUIRED_PINNED),
        "pinned_tools": tools,
        "ok": report.ok,
        "offline_policy": (
            "A scan that cannot reach the advisory DB (offline/error/non-zero "
            "exit) is classified RED/MANUAL by classify_scan_outcome -- never a "
            "false GREEN. See docs/SCAN_TOOLCHAIN_POLICY.md."
        ),
        "errors": list(report.errors),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scan_lock",
        nargs="?",
        default=str(ROOT / DEFAULT_SCAN_LOCK),
        help="Scan-tool lock to verify (default: requirements-scan.lock).",
    )
    parser.add_argument(
        "--emit-receipt",
        type=Path,
        default=None,
        help="Write the scan-toolchain receipt JSON to this path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the receipt JSON to stdout instead of the human report.",
    )
    args = parser.parse_args(argv)

    report = verify_scan_toolchain_file(Path(args.scan_lock))
    receipt = build_receipt(report)

    if args.emit_receipt is not None:
        args.emit_receipt.parent.mkdir(parents=True, exist_ok=True)
        args.emit_receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        status = "OK" if report.ok else "FAIL"
        print(f"[{status}] {report.path}")
        for name, pin in sorted(report.pins.items()):
            if name in {_canonical(n) for n in {*REQUIRED_HASHED, *REQUIRED_PINNED}}:
                print(
                    f"        {name}=={pin.version} "
                    f"(exact={pin.is_exact}, hashed={pin.is_hashed}, "
                    f"hashes={len(pin.hashes)})"
                )
        for err in report.errors:
            print(f"        - {err}")

    print(f"{GATE_ID}: {'PASS' if report.ok else 'FAIL'}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
