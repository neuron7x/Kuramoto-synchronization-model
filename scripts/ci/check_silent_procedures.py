#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""SILENT PROCEDURES — an action that did not happen, reported as one that did.

``check_fabricated_measurements.py`` guards the numeric case: a failure handler must not
return a plausible *number*, because "the wavelet transform died" then becomes
indistinguishable from "this series has no memory". Its rule is right, and it explicitly
treats ``None`` as a SAFE failure signal -- one of the three admissible ways out, because
``None`` forces the caller to handle it.

That reasoning has a blind spot, and it follows mechanically from its own premise. It
holds for a function that MEASURES: success returns a value, so ``None`` is unambiguous.
It collapses for a procedure that ACTS. A function typed ``-> None`` returns ``None`` on
success too. There, failure and success are indistinguishable BY CONSTRUCTION, and no
numeric gate can see it -- there is no number to inspect.

Both of the worst defects found on this branch are of exactly this shape:

    def _reconcile_open_orders(self, ctx) -> None:      # live_loop
        try:
            open_orders = list(ctx.connector.open_orders())
        except Exception as exc:
            self._logger.warning(...)
            return                    # <- same None as success.
                                      #    "the venue holds no open orders" and "we never
                                      #    found out what it holds" are now one value, and
                                      #    the loop resumes trading against an order book
                                      #    it never read.

    def _notify_callbacks(self) -> None:               # kill_switch
        for callback in self._callbacks:
            try:
                callback(state)       # <- one of these CANCELS THE OPEN ORDERS
            except Exception as exc:
                LOGGER.exception(...) # <- logged; loop continues; switch reports HALTED
                                      #    while the orders stay live. Fail-open inside
                                      #    the fail-safe.

So the rule this gate enforces is the action-side twin of the numeric one:

    A procedure whose failure handler neither RE-RAISES nor REPORTS leaves its caller
    unable to distinguish "done" from "did not happen".

Three ways to be distinguishable, and a site needs one:

  * re-raise (the failure stays a failure);
  * return a status the caller can test (``-> bool``, a result object) -- what
    ``_reconcile_open_orders`` now does;
  * record the failure in observable state -- what ``SafetyController.failed_effects``
    now does, so a half-enacted halt reloads as a half-enacted halt.

NOT every hit is a defect. A metric that fails to publish, a log line that cannot be
written, a best-effort cache warm -- these are genuinely best-effort, and demanding they
raise would be worse. That is why this gate is a RATCHET over a frozen baseline rather
than a hard zero: it cannot tell "best-effort by design" from "safety effect silently
dropped", and pretending otherwise would just teach people to suppress it. What it CAN
do is stop the count from growing, and make every new one an explicit decision.

The two surfaces where a silent procedure moves capital -- ``geosync/execution/`` and
``geosync/risk/`` -- are called out separately in the report, because that is where the
next ones should be paid down from.

FALSIFICATION: revert 5ede6a30 (reconcile returns bool) or 4d717c38 (failed_effects) and
the count must rise above the baseline. A ratchet that cannot go RED is a comment.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / ".github" / "silent_procedures_baseline.json"
SCAN_ROOT = REPO_ROOT / "geosync"

#: Surfaces where a silently-dropped action moves capital.
CAPITAL_SURFACES = ("geosync/execution/", "geosync/risk/")


def _is_broad(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    return isinstance(t, ast.Name) and t.id in ("Exception", "BaseException")


def _is_procedure(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A procedure: annotated ``-> None``, or never returns a value.

    A measurer (``-> float``, ``-> bool``, ``-> Order``) is out of scope: there, ``None``
    IS distinguishable from success, and the numeric gate already covers the rest.
    """
    returns = fn.returns
    if isinstance(returns, ast.Constant) and returns.value is None:
        return True
    if returns is not None:
        return False
    return not any(isinstance(n, ast.Return) and n.value is not None for n in ast.walk(fn))


def _handler_reports(handler: ast.ExceptHandler) -> bool:
    """Does the handler re-raise? (The only signal detectable from the handler alone.)

    Recording failure in state -- ``self._state.failed_effects = ...`` -- happens AFTER
    the loop, not inside the handler, so it cannot be read here. That is a deliberate
    limit: this gate detects the shape, and the baseline carries the judgement.
    """
    return any(isinstance(n, ast.Raise) for n in ast.walk(handler))


def find_silent_procedures() -> list[str]:
    hits: list[str] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_procedure(fn):
                continue
            for handler in ast.walk(fn):
                if (
                    isinstance(handler, ast.ExceptHandler)
                    and _is_broad(handler)
                    and not _handler_reports(handler)
                ):
                    hits.append(f"{rel}::{fn.name}")
                    break
    return sorted(set(hits))


def _load_baseline() -> list[str]:
    if not BASELINE.is_file():
        return []
    return list(json.loads(BASELINE.read_text(encoding="utf-8")).get("silent", []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Silent-procedure ratchet")
    parser.add_argument("--write", action="store_true", help="freeze the current set")
    args = parser.parse_args(argv)

    current = find_silent_procedures()
    capital = [h for h in current if h.startswith(CAPITAL_SURFACES)]

    if args.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Procedures (-> None) whose broad `except` neither re-raises nor "
                        "reports: the caller cannot tell 'done' from 'did not happen'. "
                        "RATCHET -- this list may only SHRINK. Not every entry is a bug "
                        "(a metric that fails to publish is genuinely best-effort), which "
                        "is why it is frozen rather than forced to zero. Pay down from the "
                        "capital surfaces first."
                    ),
                    "version": 1,
                    "count": len(current),
                    "capital_surface_count": len(capital),
                    "silent": current,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"Baseline frozen: {len(current)} silent procedures ({len(capital)} on capital surfaces)."
        )
        return 0

    baseline = _load_baseline()
    if not baseline:
        print("No baseline. Run with --write to freeze the current set.")
        return 1

    new = sorted(set(current) - set(baseline))
    fixed = sorted(set(baseline) - set(current))

    if new:
        print(f"[-] silent-procedure ratchet RED: {len(new)} NEW silent procedure(s)\n")
        for h in new:
            mark = "  [CAPITAL SURFACE]" if h.startswith(CAPITAL_SURFACES) else ""
            print(f"  + {h}{mark}")
        print(
            "\nA procedure whose failure handler neither re-raises nor reports leaves its\n"
            "caller unable to tell 'done' from 'did not happen'. Re-raise, return a status,\n"
            "or record the failure in observable state. If it is genuinely best-effort, say\n"
            "so in the docstring and re-freeze with --write."
        )
        return 1

    if fixed:
        print(
            f"[-] silent-procedure ratchet RED: {len(fixed)} entr(ies) no longer silent "
            f"but still in the baseline -- the ledger must be tightened:\n"
        )
        for h in fixed:
            print(f"  - {h}")
        print("\n  python scripts/ci/check_silent_procedures.py --write")
        return 1

    # Report CANDIDATES, not defects. The full capital population was adjudicated
    # against the source (docs/DETECTOR_GROUND_TRUTH.json): precision 0.43, 95% CI
    # [0.27, 0.61]. Saying "30 silent procedures on capital surfaces" invites the
    # reading "30 defects", and roughly half of them are best-effort by design. A count
    # is not a defect count until something OUTSIDE the detector says so.
    # See scripts/ci/calibrate_detectors.py.
    print(
        f"[+] silent-procedure ratchet held: {len(current)} candidates "
        f"({len(capital)} on capital surfaces). No new debt."
    )
    print(
        "    precision 0.43 (95% CI 0.27-0.61, n=30 adjudicated) -- these are CANDIDATES; "
        "~half the capital-surface hits are best-effort by design."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
