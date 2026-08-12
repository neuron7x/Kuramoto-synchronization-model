# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Operator-attention signal layer over the governed metrics.

The hard gates (``check_ten_axes``, ``check_mutation_kill_ratchet``) are
fail-closed: they REJECT a change the moment a metric crosses its frozen safe
range, and are silent otherwise. That is the right contract for a merge gate,
but it gives an operator no *graded* view: a metric riding one whitespace of
headroom above its floor looks identical to one with a comfortable margin, right
up until the change that finally breaches it.

This module raises the missing signal. For every governed metric it bands the
observed value against its declared safe range and emits a structured
``OperatorSignal``:

* ``RED``  — the metric REGRESSED below its frozen value (observed < frozen),
  OR the safe range cannot be confirmed at all: an unbaselined probe (stale or
  missing baseline) or an empty composition report. A safety signal fails
  CLOSED — it goes RED precisely when it cannot verify safety, never silently
  green. Surfaced here so the operator sees *which* metric and *by how much*,
  not just a gate exit code.
* ``WARN`` — the metric holds its frozen value but is intrinsically WEAK: its
  absolute score sits below ``ATTENTION_FLOOR`` (a majority of the population is
  in debt). These are the axes an operator should keep in view even when nothing
  regressed. This is the standing attention the hard gates never raise.
* ``OK``   — no regression and a healthy absolute score.

Note on why the band is absolute, not headroom-relative: the ten-axis baseline
is frozen *at* the current value by construction, so "headroom above the frozen
floor" is ~0 for every probe immediately after a re-freeze and would flood the
operator with meaningless WARNs. The meaningful early signal is the absolute
weakness of a probe, which the frozen floor does not capture.

Two metric families are watched, both cheap (no mutation re-probing):

1. Ten-axis composition scores: RED on regression vs
   ``docs/TEN_AXES_BASELINE.json``, WARN on absolute score < ``ATTENTION_FLOOR``.
2. Mutation-kill floors (``docs/MUTATION_KILL_BASELINE.json``). Any module whose
   floor is below 1.0 is a standing ``WARN``: its claim is only partially
   covered, and the operator should know which claims ride a reduced floor.

Exit is fail-closed on ``RED`` (a metric left its safe range → operator MUST
see it); ``WARN``/``OK`` exit 0 but print an attention banner. The banding logic
(:func:`band_signal`, :func:`signals_from_reports`) is pure and unit-tested with
positive and negative controls.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

TEN_AXES_BASELINE = ROOT / "docs" / "TEN_AXES_BASELINE.json"
MUTATION_BASELINE = ROOT / "docs" / "MUTATION_KILL_BASELINE.json"
SIGNAL_ARTIFACT = ROOT / "artifacts" / "operator_signals.json"

# A ten-axis probe scoring below this is intrinsically weak: score = 1 -
# debt/population, so < 0.5 means the majority of the measured population is in
# debt. Such a probe warrants standing operator attention even with nothing
# regressed. 0.5 is the natural majority-in-debt boundary, not a tuned constant.
ATTENTION_FLOOR = 0.5
# Floating-point slack so an exactly-at-floor metric is never mis-signalled as a
# breach. Matches the ten-axis gate's own comparison tolerance.
EPS = 1e-9

OK = "OK"
WARN = "WARN"
RED = "RED"
_PRECEDENCE = (OK, WARN, RED)


def worst(levels: list[str]) -> str:
    """Aggregate signal levels -- RED dominates WARN dominates OK."""
    return max(levels, key=_PRECEDENCE.index) if levels else OK


@dataclass(frozen=True)
class OperatorSignal:
    """One graded event about one metric against its safe range."""

    level: str  # OK | WARN | RED
    source: str  # which gate/ledger the metric comes from
    metric: str  # the metric's identifier
    observed: float  # currently measured value
    floor: float  # low edge of the safe range (>= floor is safe)
    headroom: float  # observed - floor (negative == breach)
    direction: str  # OK | THIN_HEADROOM | BELOW_SAFE
    detail: str  # human-readable note


def band_signal(
    observed: float,
    frozen: float,
    *,
    source: str,
    metric: str,
    attention_floor: float = ATTENTION_FLOOR,
    detail: str = "",
) -> OperatorSignal:
    """Band one observed value into a graded signal.

    RED if it REGRESSED below its frozen value (left the safe range). Otherwise
    WARN if its absolute value is below ``attention_floor`` (intrinsically weak,
    standing attention). Otherwise OK.
    """
    headroom = observed - frozen
    if headroom < -EPS:
        level, direction = RED, "REGRESSED"
    elif observed < attention_floor - EPS:
        level, direction = WARN, "WEAK_ABSOLUTE"
    else:
        level, direction = OK, "OK"
    return OperatorSignal(
        level=level,
        source=source,
        metric=metric,
        observed=round(observed, 6),
        floor=round(frozen, 6),
        headroom=round(headroom, 6),
        direction=direction,
        detail=detail,
    )


def signals_from_reports(
    current: dict,
    baseline: dict,
    ledger: dict,
    *,
    attention_floor: float = ATTENTION_FLOOR,
) -> list[OperatorSignal]:
    """Pure core: derive every operator signal from already-loaded inputs.

    ``current`` / ``baseline`` are ten-axis reports (``build_report`` shape);
    ``ledger`` is the mutation-kill baseline. No IO, no measurement -- unit
    testable with synthetic inputs.
    """
    signals: list[OperatorSignal] = []

    # (1) Ten-axis probes: RED on regression vs frozen, WARN on absolute weakness.
    base_scores = {
        p["id"]: p["score"]
        for p in baseline.get("probes", [])
        if p.get("state") == "MEASURED" and "score" in p
    }
    weakest = current.get("weakest_axis")
    measured = [
        p for p in current.get("probes", []) if p.get("state") == "MEASURED" and "score" in p
    ]

    # Fail-closed integrity gate. A signal is a SAFETY mechanism: it must go RED
    # exactly when it CANNOT confirm the safe range, never silently green. Two
    # ways that happens, both breaches:
    #   * the current report has no measured probe at all -- build_report is
    #     empty or broken, so nothing is being watched;
    #   * a measured probe has no frozen floor -- the baseline is missing, stale,
    #     or the probe was renamed, so a regression against it is invisible.
    # Without this gate a destroyed/absent baseline reads as OK (fail-open).
    if not measured:
        signals.append(
            OperatorSignal(
                level=RED,
                source="ten_axes",
                metric="<report>",
                observed=0.0,
                floor=0.0,
                headroom=0.0,
                direction="EMPTY_REPORT",
                detail="no measured probe -- the composition report is empty or broken",
            )
        )

    for probe in measured:
        pid = probe["id"]
        verdict = " [VERDICT AXIS]" if probe.get("axis") == weakest else ""
        if pid not in base_scores:
            # Fail-closed: an unbaselined measured probe cannot be checked for
            # regression. Never OK -- the baseline is stale or the probe unknown.
            signals.append(
                OperatorSignal(
                    level=RED,
                    source="ten_axes",
                    metric=pid,
                    observed=round(probe["score"], 6),
                    floor=0.0,
                    headroom=0.0,
                    direction="UNBASELINED",
                    detail=f"axis={probe.get('axis')}{verdict} -- no frozen floor; "
                    "cannot verify against a safe range",
                )
            )
            continue
        signals.append(
            band_signal(
                probe["score"],
                base_scores[pid],
                source="ten_axes",
                metric=pid,
                attention_floor=attention_floor,
                detail=f"axis={probe.get('axis')}{verdict}",
            )
        )

    # (2) Mutation-kill floors. A floor below 1.0 is a standing WARN: the
    #     module's claim rides a reduced kill-rate. Observed == floor here (the
    #     ledger records the accepted floor, not a fresh re-probe), so this
    #     surfaces reduced-coverage claims without asserting a live measurement.
    for module, entry in sorted((ledger.get("modules") or {}).items()):
        floor = float(entry.get("floor", 1.0))
        if floor >= 1.0 - EPS:
            continue
        killed = entry.get("killed")
        total = entry.get("total")
        signals.append(
            OperatorSignal(
                level=WARN,
                source="mutation_kill",
                metric=module,
                observed=round(floor, 6),
                floor=1.0,
                headroom=round(floor - 1.0, 6),
                direction="THIN_HEADROOM",
                detail=f"claim rides reduced floor ({killed}/{total} logic sites killed)",
            )
        )

    return signals


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _render(signals: list[OperatorSignal]) -> str:
    lines: list[str] = []
    by_level = {RED: [], WARN: [], OK: []}
    for s in signals:
        by_level[s.level].append(s)
    _ARROW = {
        "REGRESSED": "↓ REGRESSED below frozen",
        "WEAK_ABSOLUTE": "→ weak absolute score",
        "THIN_HEADROOM": "→ reduced floor",
        "UNBASELINED": "✗ no frozen floor (baseline stale/missing)",
        "EMPTY_REPORT": "✗ empty composition report",
    }
    for level in (RED, WARN):
        for s in by_level[level]:
            arrow = _ARROW.get(s.direction, s.direction)
            lines.append(
                f"  [{level}] {s.source}:{s.metric}  {arrow}  "
                f"observed={s.observed} floor={s.floor} headroom={s.headroom:+g}  {s.detail}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit the signal report as JSON to stdout"
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="exit 0 even on RED (surface signals without failing the run)",
    )
    args = parser.parse_args(argv)

    # Cheap: re-runs the file-count / ledger-read probes, never a mutation probe.
    from check_ten_axes import build_report

    current = build_report()
    baseline = _load(TEN_AXES_BASELINE)
    ledger = _load(MUTATION_BASELINE)

    signals = signals_from_reports(current, baseline, ledger)
    overall = worst([s.level for s in signals])

    payload = {
        "schema_version": "1.0",
        "overall": overall,
        "counts": {lvl: sum(1 for s in signals if s.level == lvl) for lvl in (RED, WARN, OK)},
        "attention_floor": ATTENTION_FLOOR,
        "signals": [asdict(s) for s in signals],
    }
    SIGNAL_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_ARTIFACT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        rendered = _render(signals)
        if overall == OK:
            sys.stdout.write("OPERATOR SIGNAL: OK -- every governed metric holds its safe range.\n")
        else:
            banner = "BREACH" if overall == RED else "ATTENTION"
            sys.stdout.write(
                f"OPERATOR SIGNAL: {overall} ({banner}) -- "
                f"{payload['counts'][RED]} RED, {payload['counts'][WARN]} WARN\n"
            )
            sys.stdout.write(rendered + "\n")
        try:
            disp = SIGNAL_ARTIFACT.relative_to(ROOT)
        except ValueError:  # artifact redirected outside the repo (e.g. a test tmp dir)
            disp = SIGNAL_ARTIFACT
        sys.stdout.write(f"wrote {disp}\n")

    if overall == RED and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
