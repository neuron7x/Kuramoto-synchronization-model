#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Debt-baseline monotonicity meta-gate — closes the ``--write`` laundering hole.

``check_code_hygiene.py`` / ``check_skip_ratchet.py`` freeze debt and fail on
new violators — but their own ``--write`` regenerates the baseline from the
current tree with NO comparison to the prior baseline. So the cheapest
response to a red gate is: add the debt, run ``--write``, commit the larger
baseline; the next ``verify`` reports "held" while debt grew. In a
deadline-driven, many-agent repo that escape converges the ratchet to a
rubber stamp.

This meta-gate removes the escape. It diffs the committed baseline *totals*
in the working tree against ``--base-ref`` (default ``origin/main``) and
fails if ANY dimension total increased. ``--write`` that pays debt DOWN
(totals shrink) passes; ``--write`` that launders debt UP cannot land. The
per-dimension hygiene/skip ratchets still catch identity-level changes; this
gate guarantees the aggregate can only fall.

Fail-closed: if the base ref or a base baseline cannot be read, the gate
fails (it cannot prove monotonicity) rather than passing vacuously.

Usage::

    python scripts/ci/check_debt_baseline_monotonic.py
    python scripts/ci/check_debt_baseline_monotonic.py --base-ref origin/main

Exit codes::

    0  — every baseline total <= the base ref's total
    1  — a baseline total grew, or the base ref could not be read
    2  — a baseline JSON is inadmissible (NaN/Infinity, or not an object)
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Load the sibling fail-closed JSON helper by absolute path. A plain
# ``from scripts.ci._safe_json import ...`` only resolves when the repo root is
# on ``sys.path`` (pytest / ``python -m``); when this gate runs exactly as its
# acceptor documents — ``python scripts/ci/check_debt_baseline_monotonic.py``
# from the repo root — ``sys.path[0]`` is ``scripts/ci`` and the package import
# raises. We cannot ``sys.path.insert`` (the release-gate path-hack probe
# fail-closes on any first-party ``sys.path`` mutation), so we load by path.
_SAFE_JSON_PATH = Path(__file__).resolve().with_name("_safe_json.py")
_safe_json_spec = importlib.util.spec_from_file_location("_geosync_safe_json", _SAFE_JSON_PATH)
if _safe_json_spec is None or _safe_json_spec.loader is None:  # pragma: no cover - defensive
    raise ImportError(f"cannot load fail-closed JSON helper at {_SAFE_JSON_PATH}")
_safe_json = importlib.util.module_from_spec(_safe_json_spec)
_safe_json_spec.loader.exec_module(_safe_json)
loads_finite_dict = _safe_json.loads_finite_dict
load_finite_dict = _safe_json.load_finite_dict

# Each tracked baseline -> how to reduce its JSON payload to per-dimension totals.
HYGIENE = "docs/CODE_DEBT_BASELINE.json"
SKIP = "docs/SKIP_RATCHET_BASELINE.json"


def _hygiene_totals(payload: dict[str, object]) -> dict[str, int]:
    out: dict[str, int] = {}
    sym = payload.get("symbol_debt", {})
    assert isinstance(sym, dict)
    for dim, entries in sym.items():
        out[f"symbol:{dim}"] = len(entries)
    fc = payload.get("file_count_debt", {})
    assert isinstance(fc, dict)
    for dim, counts in fc.items():
        out[f"count:{dim}"] = sum(counts.values())
    return out


def _skip_totals(payload: dict[str, object]) -> dict[str, int]:
    skips = payload.get("skips", {})
    assert isinstance(skips, dict)
    return {"skips": sum(skips.values())}


_REDUCERS = {HYGIENE: _hygiene_totals, SKIP: _skip_totals}


def _read_working(rel: str) -> dict[str, object]:
    return load_finite_dict(ROOT / rel)


def _read_base(rel: str, base_ref: str) -> dict[str, object] | None:
    proc = subprocess.run(
        ["git", "show", f"{base_ref}:{rel}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return loads_finite_dict(proc.stdout)


# A baseline total may legitimately GROW only when the measurement itself
# changed (a better detector or a widened gated scope) and NO runtime code was
# touched in the same diff. This is the metric/policy split: recalibrate the
# instrument in isolation, never alongside a code change (which is where debt —
# or a laundering attempt — would hide). These files define the measurement.
_DETECTOR_FILES = frozenset(
    {
        "scripts/ci/check_code_hygiene.py",
        "scripts/ci/check_skip_ratchet.py",
        "docs/CODE_QUALITY_MANIFEST.json",
    }
)


def _is_test_path(rel: str) -> bool:
    if "/tests/" in rel or "/test/" in rel:
        return True
    name = rel.rsplit("/", 1)[-1]
    return name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py")


def _changed_files(base_ref: str) -> list[str] | None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return [f.strip() for f in proc.stdout.splitlines() if f.strip()]


def _runtime_roots() -> list[str]:
    payload = load_finite_dict(ROOT / "docs" / "CODE_QUALITY_MANIFEST.json")
    return list(payload["runtime_roots"])


def _recalibration_allowed(changed: list[str], runtime_roots: list[str]) -> bool:
    """Pure decision: growth is a recalibration iff the detector/manifest changed
    and NO runtime (non-test) code did. Any runtime edit alongside growth is real
    debt or laundering, so it must NOT qualify."""
    if not any(f in _DETECTOR_FILES for f in changed):
        return False
    roots = tuple(r + "/" for r in runtime_roots)
    runtime_code_changed = any(
        f.endswith(".py") and f.startswith(roots) and not _is_test_path(f) for f in changed
    )
    return not runtime_code_changed


def _is_recalibration(base_ref: str) -> bool:
    """True iff the diff is a pure measurement change (detector/manifest) with
    no runtime-code edit — the only context in which a total may grow."""
    changed = _changed_files(base_ref)
    if changed is None:
        return False  # cannot prove isolation -> fail closed (growth blocks)
    return _recalibration_allowed(changed, _runtime_roots())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debt-baseline monotonicity meta-gate.")
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args(argv)

    grew: list[tuple[str, str, int, int]] = []
    for rel, reducer in _REDUCERS.items():
        try:
            base_payload = _read_base(rel, args.base_ref)
        except (_safe_json.NonFiniteJSONError, TypeError, ValueError) as exc:
            # A poisoned base baseline (NaN/Infinity, or a non-dict payload)
            # cannot be reduced to a trustworthy total. Fail closed with a
            # clear error rather than letting a nan sail past the > check.
            print(f"ERROR: base baseline {rel}@{args.base_ref} is not admissible JSON: {exc}")
            return 2
        if base_payload is None:
            # New baseline absent from base ref: any positive total is fresh
            # debt that must be justified, not silently admitted. Treat the
            # base as all-zero so the gate fails closed on a non-empty ledger.
            base_totals: dict[str, int] = {}
            print(f"NOTE: {rel} not found at {args.base_ref}; treating base totals as 0.")
        else:
            base_totals = reducer(base_payload)
        try:
            cur_totals = reducer(_read_working(rel))
        except (_safe_json.NonFiniteJSONError, TypeError, ValueError) as exc:
            # A NaN/Infinity in the working baseline would make the reducer sum
            # to nan, and ``nan > base`` is False — debt growth would go
            # UNDETECTED and the gate would PASS. Reject the payload instead.
            print(f"ERROR: working baseline {rel} is not admissible JSON: {exc}")
            return 2

        for dim, cur in sorted(cur_totals.items()):
            base = base_totals.get(dim, 0)
            if cur > base:
                grew.append((rel, dim, base, cur))

    if not grew:
        print(f"Debt-baseline monotonicity held: no baseline total grew vs {args.base_ref}.")
        return 0

    # A total grew. Allowed ONLY as an isolated recalibration (the metric/policy
    # split): the detector/manifest changed and no runtime code did. Any runtime
    # edit alongside growth is real debt or a laundering attempt — fail closed.
    recalibration = _is_recalibration(args.base_ref)
    tag = "RECALIBRATION" if recalibration else "ERROR"
    for rel, dim, base, cur in grew:
        print(f"{tag}: {rel} [{dim}] grew {base} -> {cur}.")

    if recalibration:
        print(
            "Allowed: this diff changes the measurement (detector/manifest) with "
            "no runtime-code edit, so the growth is a recalibration, not new debt. "
            "Review the metric change deliberately."
        )
        return 0

    print(
        "A baseline total increased alongside (or without) a runtime change. New "
        "debt must be refactored away, not frozen: do NOT --write to admit it. A "
        "genuine detector/scope change must land ALONE (no runtime-code edit)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
