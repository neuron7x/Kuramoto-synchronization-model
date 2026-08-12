# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Non-vacuity battery for the mutation-kill ratchet.

The ratchet is only worth its name if it FAILS when a floor is lowered and
HOLDS when nothing regressed. These tests pin both directions hermetically —
monkeypatching the git/probe boundary so they run in milliseconds without a
live probe — so the gate cannot silently rot into a pass-always no-op (the
exact failure mode that makes a measured kill-rate a lie).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_MOD_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_mutation_kill_ratchet.py"
_spec = importlib.util.spec_from_file_location("check_mutation_kill_ratchet", _MOD_PATH)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _no_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    # If any probe runs in these tests the boundary mock is wrong — make it loud.
    def _boom(*_a: Any, **_k: Any) -> tuple[int, dict[str, Any]]:
        raise AssertionError("ratchet probed despite no claim-critical change")

    monkeypatch.setattr(gate, "_probe_module", _boom)


def test_clean_tree_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    # base floors == current floors, nothing changed -> hold (exit 0), no probe.
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: gate._load_ledger())
    monkeypatch.setattr(gate, "_changed_files", lambda ref: set())
    _no_probe(monkeypatch)
    assert gate.main(["--base-ref", "HEAD"]) == 0


def test_lowering_a_floor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # base ref froze a HIGHER floor than the current ledger -> monotone-up
    # violation -> fail (exit 1), even with nothing else changed.
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    higher = {m: dict(spec) for m, spec in ledger.items()}
    higher[mod]["floor"] = float(ledger[mod]["floor"]) + 0.5
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: higher)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: set())
    _no_probe(monkeypatch)
    assert gate.main(["--base-ref", "HEAD"]) == 1


def test_regression_below_floor_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    # a claim-critical module changed and re-probing reports a kill-rate below
    # floor -> fail (exit 1). The probe boundary is mocked to a regressed report.
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})

    def _regressed(module: str, tests: str, floor: float) -> tuple[int, dict[str, Any]]:
        return 1, {
            "kill_rate": floor - 0.1,
            "killed": 0,
            "total": 1,
            "survivors": [{"lineno": 1, "kind": "boolop", "detail": "And->Or"}],
        }

    monkeypatch.setattr(gate, "_probe_module", _regressed)
    assert gate.main(["--base-ref", "HEAD"]) == 1


def test_meeting_floor_on_change_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    # a claim-critical module changed but re-probing still meets the floor -> hold.
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})

    def _ok(module: str, tests: str, floor: float) -> tuple[int, dict[str, Any]]:
        # Echo the ledger's OWN recorded counts: the gate now cross-checks killed/total
        # against the probe report, so a hard-coded 1/1 stub would report a false mismatch
        # for any module whose real counts differ (it did, the moment a 2/2 module sorted
        # first). The stub must simulate an honest probe, not a fixed one.
        spec = ledger[module]
        return 0, {
            "kill_rate": floor,
            "killed": int(spec["killed"]),
            "total": int(spec["total"]),
            "survivors": [],
        }

    monkeypatch.setattr(gate, "_probe_module", _ok)
    assert gate.main(["--base-ref", "HEAD"]) == 0


def test_baseline_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # if the probe cannot establish a baseline (exit 2 / empty report) the gate
    # fails closed (exit 2) rather than passing vacuously.
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})
    monkeypatch.setattr(gate, "_probe_module", lambda *a: (2, {}))
    assert gate.main(["--base-ref", "HEAD"]) == 2


# --- recursion K(K): the verifier probed by itself surfaced these gaps --- #


def test_base_ledger_reads_committed_ledger() -> None:
    # Exercises the real git boundary the hermetic tests mock away: a valid ref
    # yields the committed ledger (non-empty). Kills the L102 `!= 0`->`== 0`
    # survivor, under which a successful `git show` would wrongly return {}.
    assert gate._base_ledger("HEAD") != {}


def test_unresolvable_base_ref_fails_closed() -> None:
    # DEFECT 3: an UNRESOLVABLE base ref (typo, unfetched origin/main) must not
    # silently return {} — that makes every module look new and the monotone-up
    # floor check no-op (fail-open). It must raise so the gate can fail closed.
    with pytest.raises(gate.BaseLedgerUnreadable):
        gate._base_ledger("nonexistent-ref-zzzzzz")


def test_main_exits_fail_closed_on_unresolvable_base(monkeypatch: pytest.MonkeyPatch) -> None:
    # DEFECT 3: the unresolvable-base condition must surface as a non-zero
    # (exit 2 = could-not-establish-baseline) return from main, never a pass.
    monkeypatch.setattr(gate, "_changed_files", lambda ref: set())
    _no_probe(monkeypatch)
    assert gate.main(["--base-ref", "nonexistent-ref-zzzzzz"]) == 2


def test_broken_probe_report_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    # The probe ran (rc=1, a regression exit) but emitted no parseable report.
    # The gate must fail closed (exit 2), not crash on a missing key. Kills the
    # L151 `rc == 2 or "kill_rate" not in report`->`and` survivor: under `and`
    # this (rc!=2, empty report) case slips through to a KeyError.
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})
    monkeypatch.setattr(gate, "_probe_module", lambda *a: (1, {}))
    assert gate.main(["--base-ref", "HEAD"]) == 2


def test_recorded_counts_must_reproduce(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fabricated 99/99 that meets its floor must not pass on the strength of the rate."""
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})

    def _mismatch(module: str, tests: str, floor: float) -> tuple[int, dict[str, Any]]:
        return 0, {"kill_rate": 1.0, "killed": 99, "total": 99, "survivors": []}

    monkeypatch.setattr(gate, "_probe_module", _mismatch)
    assert gate.main(["--base-ref", "HEAD"]) == 1


def test_newly_enrolled_module_is_probed_on_the_mr_that_adds_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keying probe selection on 'source or tests changed' admitted new entries unprobed."""
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    base = {k: v for k, v in ledger.items() if k != mod}
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: base)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: set())  # nothing changed

    probed: list[str] = []

    def _record(module: str, tests: str, floor: float) -> tuple[int, dict[str, Any]]:
        probed.append(module)
        spec = ledger[module]
        return 0, {
            "kill_rate": floor,
            "killed": int(spec["killed"]),
            "total": int(spec["total"]),
            "survivors": [],
        }

    monkeypatch.setattr(gate, "_probe_module", _record)
    assert gate.main(["--base-ref", "HEAD"]) == 0
    assert probed == [mod], f"the newly enrolled module was not probed: {probed}"


def test_zero_site_enrolment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """`total == 0` is reported by the probe as kill-rate 1.0 -- free credit for no evidence."""
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    forged = {**ledger, mod: {**ledger[mod], "killed": 0, "total": 0}}
    monkeypatch.setattr(gate, "_load_ledger", lambda: forged)
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: forged)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})
    monkeypatch.setattr(
        gate,
        "_probe_module",
        lambda *a: (0, {"kill_rate": 1.0, "killed": 0, "total": 0, "survivors": []}),
    )
    assert gate.main(["--base-ref", "HEAD"]) == 1


def test_status_label_matches_the_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`status = "ok" if rate >= floor else "REGRESSED"` feeds ONLY the printed line.

    Every other case here asserts the exit code, and the exit code is decided by a separate
    `if rate < floor`. So an inverted label — every held module printed as REGRESSED, every
    real regression printed as ok — survived the whole suite. An operator reading a green
    pipeline full of the word REGRESSED, or a red one full of "ok", is being actively misled.
    """
    ledger = gate._load_ledger()
    mod = sorted(ledger)[0]
    floor = float(ledger[mod]["floor"])
    monkeypatch.setattr(gate, "_base_ledger", lambda ref: ledger)
    monkeypatch.setattr(gate, "_changed_files", lambda ref: {mod})

    def _at_floor(module: str, tests: str, f: float) -> tuple[int, dict[str, Any]]:
        spec = ledger[module]
        return 0, {
            "kill_rate": f,
            "killed": int(spec["killed"]),
            "total": int(spec["total"]),
            "survivors": [],
        }

    monkeypatch.setattr(gate, "_probe_module", _at_floor)
    assert gate.main(["--base-ref", "HEAD"]) == 0
    held = capsys.readouterr().out
    assert f"  ok: {mod}" in held, f"a module AT its floor was not labelled ok:\n{held}"
    assert "REGRESSED" not in held, f"a held module was labelled REGRESSED:\n{held}"

    def _below_floor(module: str, tests: str, f: float) -> tuple[int, dict[str, Any]]:
        spec = ledger[module]
        return 0, {
            "kill_rate": max(0.0, floor - 0.5),
            "killed": int(spec["killed"]),
            "total": int(spec["total"]),
            "survivors": [],
        }

    monkeypatch.setattr(gate, "_probe_module", _below_floor)
    assert gate.main(["--base-ref", "HEAD"]) == 1
    regressed = capsys.readouterr().out
    assert f"  REGRESSED: {mod}" in regressed, (
        f"a module BELOW its floor was not labelled REGRESSED:\n{regressed}"
    )
