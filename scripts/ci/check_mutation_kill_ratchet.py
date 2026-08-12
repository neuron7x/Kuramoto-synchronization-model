#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mutation-kill ratchet — the falsification loop's K operator as a gate.

A measured kill-rate is just a number until something fails on its regression.
This makes the number enforced: for every claim-critical module in
``docs/MUTATION_KILL_BASELINE.json``, when that module's SOURCE or its TESTS
change in a PR, this re-runs ``tools/mutation_probe.py --only-logic`` against it
and fails if the comparison/boolean-operator kill-rate dropped below the frozen
``floor``. So a change that weakens the tests for these modules — letting a
behaviour mutation survive — cannot merge.

The floors are monotone-up: a PR may RAISE a floor (after closing a survivor)
but never lower one. Closing a survivor and ratcheting the floor is the only
sanctioned direction; silently admitting a regression is impossible.

Re-probing is skipped for any module whose source and tests are both untouched
(the kill-rate cannot have changed), so the gate is cheap on the common PR and
only pays the probe cost when a claim-critical module is actually edited.

Fail-closed: if the baseline tests do not pass, or the probe cannot run, the
gate fails (it cannot prove the floor holds) rather than passing vacuously.

Usage::

    python scripts/ci/check_mutation_kill_ratchet.py [--base-ref origin/main]

Exit codes::

    0  — every changed claim-critical module meets its floor; no floor lowered
    1  — a module regressed below floor, or a floor was lowered
    2  — could not establish a baseline / load the probe (fail closed)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = ROOT / "docs" / "MUTATION_KILL_BASELINE.json"
_PROBE_PATH = ROOT / "tools" / "mutation_probe.py"


def _probe_module(module: str, tests: str, floor: float) -> tuple[int, dict[str, Any]]:
    """Run mutation_probe as a CLI (its own --fail-under does the floor check).

    Black-box on purpose: the gate verifies the tool the same way a developer
    invokes it, so it cannot drift from the tool's real behaviour. Returns the
    probe's exit code (non-zero on baseline-fail or below --fail-under) and the
    parsed JSON report.
    """
    with tempfile.NamedTemporaryFile("r", suffix=".json", delete=False) as fh:
        out_path = fh.name
    proc = subprocess.run(
        [
            sys.executable,
            str(_PROBE_PATH),
            module,
            "--tests",
            tests,
            "--only-logic",
            "--fail-under",
            str(floor),
            "--json",
            out_path,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(Path(out_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}
    report["_probe_stdout_tail"] = proc.stdout[-4000:]
    report["_probe_stderr_tail"] = proc.stderr[-4000:]
    Path(out_path).unlink(missing_ok=True)
    return proc.returncode, report


def _load_ledger(text: str | None = None) -> dict[str, dict[str, Any]]:
    payload = json.loads(text if text is not None else LEDGER_PATH.read_text(encoding="utf-8"))
    modules = payload.get("modules", {})
    assert isinstance(modules, dict)
    return modules


class BaseLedgerUnreadable(RuntimeError):
    """The base ref itself could not be resolved — no floor can be established."""


def _ref_resolvable(base_ref: str) -> bool:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _base_ledger(base_ref: str) -> dict[str, dict[str, Any]]:
    proc = subprocess.run(
        ["git", "show", f"{base_ref}:docs/MUTATION_KILL_BASELINE.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        # Distinguish two failure modes that both make `git show` non-zero:
        #  * a RESOLVABLE ref that simply has no baseline file yet -> legitimate
        #    empty base (a brand-new module set), return {} and continue.
        #  * an UNRESOLVABLE ref (typo, unfetched origin/main) -> fail closed.
        #    Returning {} here would make every module look new, so the
        #    monotone-up floor check silently no-ops (the fail-open defect).
        if not _ref_resolvable(base_ref):
            raise BaseLedgerUnreadable(
                f"base ref {base_ref!r} is unresolvable; cannot establish a "
                "mutation-kill floor (fail-closed)"
            )
        return {}
    return _load_ledger(proc.stdout)


def _changed_files(base_ref: str) -> set[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {f.strip() for f in proc.stdout.splitlines() if f.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mutation-kill ratchet.")
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args(argv)

    ledger = _load_ledger()
    try:
        base = _base_ledger(args.base_ref)
    except BaseLedgerUnreadable as exc:
        print(f"ERROR: {exc}")
        return 2
    changed = _changed_files(args.base_ref)
    failed = False

    # 1) monotone-up: a floor may only rise versus the base ref.
    for mod, spec in sorted(ledger.items()):
        if mod in base and float(spec["floor"]) < float(base[mod]["floor"]):
            failed = True
            print(
                f"ERROR: {mod} floor lowered {base[mod]['floor']} -> {spec['floor']} "
                "(mutation-kill floors only rise)."
            )

    # 2) re-probe every module whose source or tests changed -- AND every NEWLY ENROLLED one.
    #
    # Keying only on "source or tests changed" left the enrolling MR itself unverified: a new
    # entry for an untouched module was accepted on the word of whoever typed it, and the
    # module would not be probed until it next changed. That is the one moment the numbers are
    # asserted for the first time, so it is exactly the moment to check them. (Found by
    # adversarial review of the first real enrolment batch, in which four of six new entries
    # were accepted unprobed.)
    newly_enrolled = set(ledger) - set(base)
    to_probe = [
        (mod, spec)
        for mod, spec in sorted(ledger.items())
        if mod in changed
        or mod in newly_enrolled
        or any(t in changed for t in str(spec["tests"]).split())
    ]
    if not to_probe:
        print("Mutation-kill ratchet held: no claim-critical module changed.")
        return 1 if failed else 0

    for mod, spec in to_probe:
        tests = str(spec["tests"])
        floor = float(spec["floor"])
        rc, report = _probe_module(mod, tests, floor)
        if rc == 2 or "kill_rate" not in report:
            print(
                f"ERROR: could not establish baseline for {mod} (probe exit {rc}); cannot verify floor."
            )
            print("---- mutation probe stdout tail ----")
            print(str(report.get("_probe_stdout_tail", "")).strip())
            print("---- mutation probe stderr tail ----")
            print(str(report.get("_probe_stderr_tail", "")).strip())
            print("---- end mutation probe diagnostics ----")
            return 2
        rate = float(report["kill_rate"])
        # A module with no logic-mutation sites is reported by the probe as kill-rate 1.0 --
        # a vacuous perfect score. Enrolling one buys coverage credit for zero evidence, so
        # zero-site modules are refused enrolment outright rather than left to discipline.
        if int(report["total"]) <= 0:
            print(
                f"ERROR: {mod} has no logic-mutation sites (total=0); the probe reports that "
                "as kill-rate 100% and it is not evidence. Do not enrol zero-site modules."
            )
            failed = True
        # Cross-check the RECORDED counts against what the probe just measured. Comparing only
        # the rate against the floor left killed/total unverified for free -- a fabricated
        # "99/99" on a module that really has 1 mutation site passed silently.
        for field in ("killed", "total"):
            recorded = spec.get(field)
            if recorded is not None and int(recorded) != int(report[field]):
                print(
                    f"ERROR: {mod} ledger records {field}={recorded} but the probe measured "
                    f"{report[field]} -- the enrolment's own numbers do not reproduce."
                )
                failed = True
        status = "ok" if rate >= floor else "REGRESSED"
        print(
            f"  {status}: {mod} logic kill-rate {rate:.1%} "
            f"(floor {floor:.0%}, {report['killed']}/{report['total']})"
        )
        if rate < floor:
            failed = True
            for m in report.get("survivors", []):
                print(f"      survivor {mod}:{m['lineno']} [{m['kind']}] {m['detail']}")

    if failed:
        print(
            "A claim-critical module's tests weakened (a behaviour mutation now "
            "survives) or a floor was lowered. Close the survivor and keep the "
            "floor, or this cannot merge."
        )
        return 1
    print("Mutation-kill ratchet held: every changed claim-critical module meets its floor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
