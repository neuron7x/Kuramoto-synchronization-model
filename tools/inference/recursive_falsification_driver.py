#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Recursive falsification driver (WP-07) — admissibility infrastructure.

Chains the EXISTING components into one loop:

    observed statistic -> null challenge -> claim classification ->
    residual decision -> tightened context -> next iteration

Each iteration emits exactly one of the act's five allowed outcomes
(``REPRODUCED``, ``REFUTED``, ``NARROWED``, ``STRICTER_RULE``, ``PROMOTED``) and
the loop terminates on refutation or on stability. It binds:

* ``analytics.signals.null_baseline`` for the null ensemble (real computation);
* ``analytics.signals.claim_maturity.evaluate_promotion`` for the claim tier —
  so the loop can **never** promote past the evidence it holds. With only the
  synthetic-tier tokens available here, the ceiling is ``MEASURED_SYNTHETIC``;
  any attempt to promote higher is refused by the ladder, not by this driver.

Honest scope. This is a loop *harness*, run here on a seeded synthetic observed
statistic. Survival of a synthetic statistic against a synthetic null is a
structural property of the harness, **not** evidence of a market signal and
**not** a predictive or physics claim. The ``observed_statistic`` callable is
injectable so a real kernel/data source can be substituted without changing the
loop; until then the claim ceiling stays ``MEASURED_SYNTHETIC``.

The loop earns the name only because it can kill its own hypothesis: a statistic
indistinguishable from the null terminates the run ``REFUTED`` with a cause.

Exit codes::

    0  loop ran and produced a terminal ledger (REFUTED or BOUNDED_STABLE)
    1  fail-closed abort (a step could not be classified)
    2  malformed invocation
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]

#: Tokens available on the synthetic path. The ladder caps the claim here.
_SYNTHETIC_EVIDENCE = ("observability", "synthetic_measurement")
_SYNTHETIC_CEILING = "MEASURED_SYNTHETIC"

#: A statistic this close to the null centre is treated as indistinguishable.
_REFUTE_BAND = 0.05

#: Consecutive survivals (at the ceiling, with no tightening headroom) → stable.
_STABLE_AFTER = 2


def _load_module(rel: str, name: str) -> ModuleType:
    path = _ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _percentile_in_null(observed: float, null: Any) -> float:
    """Fraction of the null ensemble at or below the observed statistic."""
    import numpy as np

    arr = np.asarray(null, dtype=np.float64)
    return float((arr <= observed).mean())


def _synthetic_observed(seed: int, iteration: int) -> float:
    """Deterministic stand-in observed statistic (no market meaning)."""
    h = hashlib.sha256(f"{seed}:{iteration}".encode()).digest()
    # Map to a value near the standard-normal tail so a non-trivial fraction of
    # seeds land inside the refutation band and a non-trivial fraction survive.
    return (int.from_bytes(h[:4], "big") / 2**32) * 6.0 - 3.0


def run_loop(
    *,
    seed: int,
    max_iter: int = 6,
    null_n: int = 1024,
    observed_statistic: Callable[[int, int], float] | None = None,
) -> dict[str, Any]:
    """Run the recursive falsification loop and return a content-hashed ledger."""
    nb = _load_module("analytics/signals/null_baseline.py", "_nb_loop")
    cm = _load_module("analytics/signals/claim_maturity.py", "_cm_loop")
    observe = observed_statistic or _synthetic_observed

    steps: list[dict[str, Any]] = []
    survivals = 0
    n = null_n
    terminal: str | None = None
    claim_tier = "UNOBSERVED"

    for it in range(max_iter):
        observed = observe(seed, it)
        null_array, _ = nb.make_gaussian_null(n, seed + it)
        pct = _percentile_in_null(observed, null_array)
        # Distance of the observed percentile from the null centre (0.5).
        extremity = abs(pct - 0.5)

        if extremity < _REFUTE_BAND:
            steps.append(
                {
                    "iteration": it,
                    "outcome": "REFUTED",
                    "null_n": n,
                    "percentile": round(pct, 6),
                    "cause": "observed statistic is indistinguishable from the null (within band)",
                }
            )
            terminal = "REFUTED"
            break

        # Survived this null. The first survival earns the synthetic ceiling via
        # the real ladder; it can never be promoted higher without real-data
        # tokens, so subsequent survivals only tighten the test.
        if claim_tier != _SYNTHETIC_CEILING:
            verdict = cm.evaluate_promotion("UNOBSERVED", _SYNTHETIC_CEILING, _SYNTHETIC_EVIDENCE)
            if not verdict.allowed:
                steps.append(
                    {"iteration": it, "outcome": "REFUTED", "cause": "synthetic ceiling unearned"}
                )
                terminal = "REFUTED"
                break
            claim_tier = _SYNTHETIC_CEILING
            steps.append(
                {
                    "iteration": it,
                    "outcome": "PROMOTED",
                    "null_n": n,
                    "percentile": round(pct, 6),
                    "promoted_to": claim_tier,
                    "boundary": cm.CLAIM_BOUNDARY,
                }
            )
        else:
            survivals += 1
            # Tighten: a larger null is a stricter test. No headroom → stable.
            if n < null_n * 4:
                n *= 2
                steps.append(
                    {
                        "iteration": it,
                        "outcome": "STRICTER_RULE",
                        "null_n": n,
                        "percentile": round(pct, 6),
                        "rule": "doubled null ensemble size",
                    }
                )
            else:
                steps.append(
                    {
                        "iteration": it,
                        "outcome": "NARROWED",
                        "null_n": n,
                        "percentile": round(pct, 6),
                        "claim": f"bounded synthetic survival at {claim_tier}",
                    }
                )
                if survivals >= _STABLE_AFTER:
                    terminal = "BOUNDED_STABLE"
                    break

    if terminal is None:
        terminal = "BOUNDED_STABLE" if claim_tier == _SYNTHETIC_CEILING else "REFUTED"

    ledger: dict[str, Any] = {
        "schema_version": 1,
        "seed": seed,
        "terminal_verdict": terminal,
        "claim_tier": claim_tier,
        "claim_ceiling": _SYNTHETIC_CEILING,
        "is_predictive_claim": False,
        "steps": steps,
    }
    ledger["ledger_sha256"] = hashlib.sha256(
        json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ledger


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-iter", type=int, default=6)
    parser.add_argument("--out", help="write the recursion ledger here")
    args = parser.parse_args(argv)

    ledger = run_loop(seed=args.seed, max_iter=args.max_iter)
    text = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(
        f"recursion terminal={ledger['terminal_verdict']} tier={ledger['claim_tier']} "
        f"steps={len(ledger['steps'])} (synthetic; not a predictive claim)"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
