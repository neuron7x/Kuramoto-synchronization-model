#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Verify that every ``requirements*.lock`` is hash-locked and fully pinned (ENV-003).

Fail-closed dependency-lock gate. It answers one question for each lock file:

    Is every requirement pinned to an exact version *and* carrying at least one
    well-formed ``--hash=sha256:<64-hex>`` entry, with no unconstrained
    (``>=`` / ``~=`` / operator-less) transitive resolution slipping through?

This is the CI counterpart to ``pip install --require-hashes``: a lock that
passes this gate is one that pip would accept in hash-checking mode (build
backends such as setuptools/pip/wheel excepted -- see ``ALLOW_UNHASHED_NAMES``).

Design notes
------------
* ``verify_lock`` is a pure function over the *text* of a lock file so tests can
  feed doctored fixtures (a line with no ``--hash``, an unpinned ``name>=x``)
  and assert the gate fails closed. No filesystem or network needed to test it.
* Fail-closed everywhere: a missing hash, an unpinned requirement, a malformed
  digest, or a vacuous (zero-requirement) lock all yield a HARD failure.
* This gate NEVER regenerates or mutates a lock. It only reads and verifies.
  Regeneration is a controlled, documented ``pip-compile --generate-hashes``
  step (see ``docs/DEPENDENCY_LOCK_POLICY.md``).

Severity model
--------------
HARD failures (exit code 1 -- the fail-closed contract):
    * a requirement is not pinned with ``==`` (range / operator-less / URL)
    * a requirement carries zero ``--hash=`` entries
    * a hash is not ``sha256:`` + exactly 64 lowercase hex chars
    * a duplicate requirement name
    * fewer than ``--min-requirements`` requirements in a lock (vacuous pass)
    * a named lock file is missing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_ID = "G-LOCK-HASHES"

# Canonical set of locks this gate governs. Order is stable for reporting.
DEFAULT_LOCKS = ("requirements.lock", "requirements-dev.lock", "requirements-scan.lock")

# Build-backend / bootstrap distributions that pip-compile intentionally leaves
# unpinned (its "unsafe" set) unless ``--allow-unsafe`` is passed. pip does not
# require hashes for these when they are already present in the environment, so
# they are exempt from the hash requirement -- but ONLY these exact names.
ALLOW_UNHASHED_NAMES = frozenset({"pip", "setuptools", "wheel", "distribute"})

SHA256_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})(?![0-9a-fA-F])")
# A requirement spec: distribution name, optional [extras], an operator, a version.
REQ_SPEC_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[A-Za-z0-9,._\-]+\])?"
    r"\s*(?P<op>===|==|~=|!=|<=|>=|<|>)?"
    r"\s*(?P<version>[^\s;\\]+)?"
)
# Non-requirement directives that may appear at column 0 in a requirements file.
DIRECTIVE_PREFIXES = ("-c ", "-r ", "-e ", "--", "-C", "-f ", "-i ")


@dataclass
class Requirement:
    name: str
    raw_name: str
    operator: str | None
    version: str | None
    hashes: list[str] = field(default_factory=list)
    line_no: int = 0


@dataclass
class LockReport:
    path: str
    exists: bool
    requirement_count: int = 0
    hashed_count: int = 0
    unhashed_count: int = 0
    unpinned_count: int = 0
    malformed_hash_count: int = 0
    duplicate_count: int = 0
    errors: list[str] = field(default_factory=list)
    exempt_unhashed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.exists and not self.errors


def _canonical(name: str) -> str:
    """PEP 503 normalization so ``PyYAML`` and ``pyyaml`` are the same key."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _iter_blocks(text: str) -> list[tuple[int, list[str]]]:
    """Group a requirements file into (start_line_no, block_lines).

    A block starts at a column-0, non-blank, non-comment line and extends over
    the following indented continuation lines (the ``--hash`` tail).
    """
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    start = 0
    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[:1].isspace():
            # continuation (hash / marker) line -- belongs to current block
            if current is not None:
                current.append(raw)
            continue
        # column-0 content line -> new block
        if current is not None:
            blocks.append((start, current))
        current = [raw]
        start = idx
    if current is not None:
        blocks.append((start, current))
    return blocks


def verify_lock(text: str, *, path: str = "<memory>", min_requirements: int = 1) -> LockReport:
    """Pure verifier: parse lock *text* and return a fail-closed report.

    Marks the report with an error for every unpinned requirement, every
    requirement lacking a well-formed sha256 hash, every malformed digest, and
    every duplicate name. A lock with fewer than ``min_requirements`` pinned
    requirements is treated as vacuous and fails closed.
    """
    report = LockReport(path=path, exists=True)
    seen: dict[str, int] = {}

    for start, block in _iter_blocks(text):
        head = block[0].strip()
        if head.startswith(DIRECTIVE_PREFIXES):
            continue
        block_text = "\n".join(block)
        m = REQ_SPEC_RE.match(head)
        if not m or not m.group("name"):
            report.errors.append(f"line {start}: unparseable requirement line: {head!r}")
            continue

        raw_name = m.group("name") + (m.group("extras") or "")
        name = _canonical(m.group("name"))
        op = m.group("op")
        version = m.group("version")

        hashes = SHA256_HASH_RE.findall(block_text)
        # Detect malformed hash attempts: a ``--hash=`` that our strict regex rejected.
        malformed = [
            tok
            for tok in re.findall(r"--hash=\S+", block_text)
            if not SHA256_HASH_RE.match(tok)
        ]

        req = Requirement(
            name=name,
            raw_name=raw_name,
            operator=op,
            version=version,
            hashes=hashes,
            line_no=start,
        )
        report.requirement_count += 1

        # Duplicate detection (canonical name).
        if name in seen:
            report.duplicate_count += 1
            report.errors.append(
                f"line {start}: duplicate requirement {raw_name!r} "
                f"(first seen line {seen[name]})"
            )
        else:
            seen[name] = start

        # Pin discipline: must be an exact '==' (or PEP 440 '===') pin.
        if op not in ("==", "===") or not version:
            report.unpinned_count += 1
            report.errors.append(
                f"line {start}: unpinned/unconstrained requirement {raw_name!r} "
                f"(operator {op!r}); locks must pin exact '==' versions"
            )

        # Malformed hashes are always a hard error.
        if malformed:
            report.malformed_hash_count += len(malformed)
            report.errors.append(
                f"line {start}: {raw_name!r} has malformed hash token(s): {malformed}"
            )

        # Hash presence: required unless the distribution is an exempt backend.
        if req.hashes:
            report.hashed_count += 1
        elif name in ALLOW_UNHASHED_NAMES:
            report.unhashed_count += 1
            report.exempt_unhashed.append(raw_name)
        else:
            report.unhashed_count += 1
            report.errors.append(
                f"line {start}: requirement {raw_name!r} carries no --hash=sha256: entry "
                f"(fail-closed: not installable under pip --require-hashes)"
            )

    if report.requirement_count < min_requirements:
        report.errors.append(
            f"vacuous lock: {report.requirement_count} requirement(s) < "
            f"min_requirements={min_requirements}; a hash gate over an empty lock is not proof"
        )
    return report


def verify_lock_file(path: Path, *, min_requirements: int = 1) -> LockReport:
    if not path.exists():
        return LockReport(path=str(path), exists=False, errors=[f"missing lock file: {path}"])
    report = verify_lock(
        path.read_text(encoding="utf-8"),
        path=str(path),
        min_requirements=min_requirements,
    )
    return report


_PIP_COMPILE_HDR_RE = re.compile(r"autogenerated by (pip-compile[^\n]*)", re.IGNORECASE)
_PIP_COMPILE_CMD_RE = re.compile(r"^#\s+(pip-compile .+)$", re.MULTILINE)


def _detect_tool(path_str: str) -> str:
    """Read a lock's header to honestly record which tool produced it.

    Returns the generating command (e.g. ``pip-compile --generate-hashes ...``)
    when the file is pip-compile output, else ``verify-only`` -- the gate itself
    never regenerates a lock, so a lock with no generator header is only verified.
    """
    p = Path(path_str)
    if not p.exists():
        return "missing"
    head = "\n".join(p.read_text(encoding="utf-8").splitlines()[:12])
    cmd = _PIP_COMPILE_CMD_RE.search(head)
    if cmd:
        return cmd.group(1).strip()
    if _PIP_COMPILE_HDR_RE.search(head):
        return "pip-compile"
    return "verify-only"


def _rel(path_str: str) -> str:
    try:
        return Path(path_str).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path_str


def build_provenance(reports: list[LockReport]) -> dict:
    """Machine-readable per-lock provenance.

    The gate is a *verifier*; it does not regenerate. Per-lock ``tool`` is read
    honestly from each lock's own pip-compile header (the controlled generator),
    falling back to ``verify-only`` for locks with no generator provenance.
    """
    return {
        "gate_id": GATE_ID,
        "schema": "lock_provenance/v1",
        "generated_by": "scripts/ci/check_lock_hashes.py",
        "gate_mode": "verify-only",
        "hash_algorithm": "sha256",
        "allow_unhashed_names": sorted(ALLOW_UNHASHED_NAMES),
        "locks": [
            {
                "path": _rel(r.path),
                "exists": r.exists,
                "line_count_requirements": r.requirement_count,
                "hashed_count": r.hashed_count,
                "unhashed_count": r.unhashed_count,
                "unpinned_count": r.unpinned_count,
                "malformed_hash_count": r.malformed_hash_count,
                "duplicate_count": r.duplicate_count,
                "exempt_unhashed": sorted(r.exempt_unhashed),
                "fully_hashed": r.exists and r.unhashed_count == 0,
                "ok": r.ok,
                "tool": _detect_tool(r.path),
            }
            for r in reports
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "locks",
        nargs="*",
        help="Lock files to verify (default: the canonical requirements*.lock set).",
    )
    parser.add_argument(
        "--min-requirements",
        type=int,
        default=10,
        help="Fail if a lock has fewer than N requirements (guards a vacuous pass).",
    )
    parser.add_argument(
        "--emit-provenance",
        type=Path,
        default=None,
        help="Write per-lock provenance JSON to this path (does not affect exit code).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the provenance JSON to stdout instead of the human report.",
    )
    args = parser.parse_args(argv)

    lock_paths = [Path(p) for p in args.locks] or [ROOT / name for name in DEFAULT_LOCKS]

    reports = [verify_lock_file(p, min_requirements=args.min_requirements) for p in lock_paths]
    provenance = build_provenance(reports)

    if args.emit_provenance is not None:
        args.emit_provenance.parent.mkdir(parents=True, exist_ok=True)
        args.emit_provenance.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(provenance, indent=2))
    else:
        for r in reports:
            status = "OK" if r.ok else "FAIL"
            print(
                f"[{status}] {r.path}: {r.requirement_count} reqs, "
                f"{r.hashed_count} hashed, {r.unhashed_count} unhashed, "
                f"{r.unpinned_count} unpinned"
            )
            if r.exempt_unhashed:
                print(f"        exempt (build backend, no hash required): {', '.join(sorted(r.exempt_unhashed))}")
            for err in r.errors:
                print(f"        - {err}")

    ok = all(r.ok for r in reports)
    print(f"{GATE_ID}: {'PASS' if ok else 'FAIL'} over {len(reports)} lock(s)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
