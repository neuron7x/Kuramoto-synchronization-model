from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.hyperdirect_veto import (  # noqa: E402
    HyperdirectConfig,
    HyperdirectVeto,
    HyperdirectVetoError,
)

__all__ = ["AttackResult", "run_battery", "main"]


@dataclass(frozen=True)
class AttackResult:
    """One adversarial probe.

    ``broken`` means the protected invariant was violated — the primitive
    failed its job. ``boundary`` means the attack succeeds *by design*:
    a documented limitation, reported honestly rather than hidden as a
    pass. Only ``broken`` fails the battery.
    """

    rung: str
    broken: bool
    boundary: bool
    detail: str


def _r(rung: str, *, broken: bool, detail: str, boundary: bool = False) -> AttackResult:
    return AttackResult(rung=rung, broken=broken, boundary=boundary, detail=detail)


def a1_averaging_attack() -> AttackResult:
    """One saturated channel, rest zero, enormous margin.

    mean is tiny; if the gate averaged, this would PASS. It must veto.
    """
    gate = HyperdirectVeto()
    d = gate.evaluate({"hot": 0.99, "a": 0.0, "b": 0.0, "c": 0.0}, evidence_margin=1e12)
    broken = d.passed
    return _r(
        "A1-averaging",
        broken=broken,
        detail=f"passed={d.passed} reason={d.reason!r} c_aggregate={d.c_aggregate:.4f}",
    )


def a2_channel_split_dilution() -> AttackResult:
    """Adversary decomposes one big conflict into many small ones.

    A 0.9 signal split into 9 channels of 0.1 drops max below the
    ceiling AND drops the mean. HyperdirectVeto, by construction, cannot
    defend against an adversary who controls channel decomposition —
    that is exactly why HDV-007 makes residual-channel provenance a
    *caller* contract. We report this as a BOUNDARY, not a pass: the
    primitive is honest about what it does not protect.
    """
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    concentrated = gate.evaluate({"x": 0.9}, evidence_margin=0.5)
    diluted = gate.evaluate({f"x{i}": 0.1 for i in range(9)}, evidence_margin=0.5)
    bypass = (not concentrated.passed) and diluted.passed
    return _r(
        "A2-channel-split",
        broken=False,
        boundary=bypass,
        detail=(
            f"concentrated.passed={concentrated.passed} "
            f"diluted.passed={diluted.passed} -> decomposition bypass "
            f"{'CONFIRMED (documented boundary, HDV-007 caller contract)' if bypass else 'not reachable'}"
        ),
    )


def a3_margin_inflation() -> AttackResult:
    """No finite evidence margin may override a single-channel STOP."""
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    worst = False
    for margin in (1.0, 1e6, 1e18, sys.float_info.max):
        d = gate.evaluate({"hot": 0.9, "b": 0.2}, evidence_margin=margin)
        if d.passed:
            worst = True
    return _r(
        "A3-margin-inflation",
        broken=worst,
        detail=f"max margin {sys.float_info.max:.3e} still vetoed={not worst}",
    )


def a4_empty_channel_state() -> AttackResult:
    """Empty conflict is a valid 'no residual conflict' state (HDV-006).

    It is only a leak if it bypasses the base margin. It must not.
    """
    gate = HyperdirectVeto(HyperdirectConfig(base_margin=0.5, conflict_gain=1.0))
    below = gate.evaluate({}, evidence_margin=0.49)
    at_or_above = gate.evaluate({}, evidence_margin=0.51)
    leak = below.passed  # base margin not enforced on empty conflict
    return _r(
        "A4-empty-state",
        broken=leak,
        detail=(
            f"empty+below-base passed={below.passed} (must be False); "
            f"empty+above-base passed={at_or_above.passed} (expected True)"
        ),
    )


def a5_float_precision_boundary() -> AttackResult:
    """The ceiling is a hard >= edge; probe the nextafter neighbourhood."""
    gate = HyperdirectVeto(HyperdirectConfig(hard_ceiling=0.8))
    just_below = math.nextafter(0.8, 0.0)
    exact = gate.evaluate({"x": 0.8}, evidence_margin=1e9)
    under = gate.evaluate({"x": just_below}, evidence_margin=1e9)
    broken = exact.passed or (not under.passed)
    return _r(
        "A5-float-boundary",
        broken=broken,
        detail=(
            f"ceiling exact vetoed={not exact.passed} (must be True); "
            f"nextafter-below passed={under.passed} (must be True)"
        ),
    )


def a6_nonfinite_injection() -> AttackResult:
    """NaN/inf in any numeric input must fail-closed, never PASS."""
    gate = HyperdirectVeto()
    leaked = False
    cases: list[tuple[dict[str, float], float]] = [
        ({"x": math.nan}, 1.0),
        ({"x": math.inf}, 1.0),
        ({"x": 0.1}, math.nan),
        ({"x": 0.1}, math.inf),
    ]
    for conflict, margin in cases:
        try:
            gate.evaluate(conflict, evidence_margin=margin)
            leaked = True  # returned a decision instead of raising
        except HyperdirectVetoError:
            pass
    return _r(
        "A6-nonfinite",
        broken=leaked,
        detail=f"all non-finite inputs fail-closed={not leaked}",
    )


def a7_safety_monotonicity(trials: int = 5000) -> AttackResult:
    """Raising any channel must never flip a veto into a pass.

    Random search for a counterexample to weak safety-monotonicity.
    """
    rng = random.Random(20260515)
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    violation: str | None = None
    for _ in range(trials):
        keys = [f"k{i}" for i in range(rng.randint(1, 5))]
        base = {k: round(rng.uniform(0.0, 0.79), 4) for k in keys}
        margin = rng.uniform(0.0, 1.5)
        before = gate.evaluate(base, evidence_margin=margin)
        if before.passed:
            continue
        bump_key = rng.choice(keys)
        bumped = dict(base)
        bumped[bump_key] = min(1.0, base[bump_key] + rng.uniform(0.0, 0.2))
        after = gate.evaluate(bumped, evidence_margin=margin)
        if after.passed:
            violation = f"{base}->{bumped} margin={margin}"
            break
    return _r(
        "A7-safety-monotonicity",
        broken=violation is not None,
        detail=violation or f"{trials} trials: more conflict never relaxed a veto",
    )


def a8_determinism(trials: int = 4000) -> AttackResult:
    """No clock/RNG/state: identical inputs -> identical decisions."""
    rng = random.Random(7)
    gate = HyperdirectVeto(HyperdirectConfig(conflict_gain=1.0))
    drift: str | None = None
    for _ in range(trials):
        conflict = {f"c{i}": round(rng.uniform(0.0, 1.0), 6) for i in range(rng.randint(0, 6))}
        margin = rng.uniform(-1.0, 2.0)
        first = gate.evaluate(conflict, evidence_margin=margin)
        second = gate.evaluate(dict(conflict), evidence_margin=margin)
        if first != second:
            drift = f"{conflict} margin={margin}"
            break
    return _r(
        "A8-determinism",
        broken=drift is not None,
        detail=drift or f"{trials} trials: bit-identical on repeat",
    )


def run_battery() -> list[AttackResult]:
    return [
        a1_averaging_attack(),
        a2_channel_split_dilution(),
        a3_margin_inflation(),
        a4_empty_channel_state(),
        a5_float_precision_boundary(),
        a6_nonfinite_injection(),
        a7_safety_monotonicity(),
        a8_determinism(),
    ]


def main() -> int:
    results = run_battery()
    width = max(len(r.rung) for r in results)
    broken_any = False
    for r in results:
        if r.broken:
            tag = "BROKEN"
            broken_any = True
        elif r.boundary:
            tag = "BOUNDARY"
        else:
            tag = "SURVIVED"
        print(f"[{tag:8}] {r.rung:<{width}}  {r.detail}")
    if broken_any:
        print("\nFALSIFIED: at least one protected invariant was violated.")
        return 1
    print("\nAll protected invariants survived. Boundaries are documented, not hidden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
