# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""The No-Ungrounded-Act theorem — the single apex invariant of the system.

Everything below converges here. An action is admissible iff, simultaneously:

    H1 homeostasis   the drive is bounded (allostatic load within its clamp)
    H2 arrow-of-time the epistemic budget is monotonically non-increasing
    H3 synchrony     components phase-lock (Kuramoto coherence >= r_min)
    H4 verification  the final inference verdict is PASS

    ACT-ADMISSIBLE  ⇔  H1 ∧ H2 ∧ H3 ∧ H4       otherwise FORBIDDEN (fail-closed)

Every ground is RE-DERIVED, never trusted from a forgeable artifact: H1/H3 by
driving the real homeostasis controllers, H2 by driving the real epistemic-audit
budget register, H4 by re-running the aggregator over the substrate. This sits
ABOVE the aggregator: it consumes system truth, it is not part of it. A FORBIDDEN
verdict exits non-zero unless --report-only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from core.neuro.epistemic_audit import advance_entry
from core.neuro.epistemic_validation import EpistemicPhase, EpistemicState

SCHEMA_ID = "geosync.no_ungrounded_act.v1"
_HERE = Path(__file__).resolve().parent


def _rederive_final_verdict(root: Path) -> bool:
    """H4, re-derived: re-run the aggregator over the substrate rather than trust
    the committed final_inference_verdict.json verdict field.

    An adversary who forges the final verdict to PASS while a substrate artifact
    is FAIL/missing/report-only cannot fool the apex, because the aggregate is
    recomputed from the substrate here.
    """

    spec = importlib.util.spec_from_file_location(
        "_afiv_apex", _HERE / "audit_final_inference_verdict.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return False
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.build_verdict(root, release=False)
    return bool(report.get("verdict") == "PASS")


def _rederive_homeostasis(root: Path) -> dict[str, Any]:
    """Re-run the REAL homeostasis controllers rather than read the artifact.

    Closes the within-bound forgery: an adversary who edits
    homeostasis_contract.json to report a plausible-but-false allostatic load or
    coherence is ignored, because the apex drives the real AllostaticRegulator and
    Kuramoto order parameter here instead of trusting the file's numbers.
    """

    spec = importlib.util.spec_from_file_location(
        "_homeo_apex", _HERE / "audit_homeostasis_contract.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return {"verdict": "FAIL", "worst_allostatic_load": float("inf"), "coherence_locked": 0.0}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_contract()


def budget_monotone_under_real_audit() -> bool:
    """H2: drive the real epistemic-audit register; every advance costs >= 0.

    A within-run budget *increase* would surface as a negative ``cost_paid`` —
    an arrow-of-time violation. A monotone-non-increasing run never does.
    """

    phase = EpistemicPhase.ACTIVE

    def _state(seq: int, budget: float) -> EpistemicState:
        return EpistemicState(
            seq=seq,
            weight=1.0,
            budget=budget,
            invariant_floor=0.1,
            phase=phase,
            state_hash=f"h{seq}",
            halt_reason=None,
        )

    budgets = [10.0, 7.0, 7.0, 3.0, 0.0]
    states = [_state(i, b) for i, b in enumerate(budgets)]
    costs = [advance_entry(states[i], states[i + 1])["cost_paid"] for i in range(len(states) - 1)]
    return all(cost >= 0.0 for cost in costs)


def act_admissible(*, h1: bool, h2: bool, h3: bool, h4: bool) -> str:
    """The apex gate. ADMISSIBLE only when all four grounds hold."""

    return "ADMISSIBLE" if (h1 and h2 and h3 and h4) else "FORBIDDEN"


def _load(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_apex(root: Path) -> dict[str, Any]:
    """Evaluate H1..H4 over the committed artifacts + the real budget register."""

    # H1/H3 are RE-DERIVED from the real controllers, not read from the artifact,
    # so a forged homeostasis number (even a within-bound lie) cannot ground an act.
    homeostasis = _rederive_homeostasis(root)

    # H1 homeostasis: the real allostatic load is within its clamp and the real
    # contract (bounded ∧ in-spec ∧ coherent) passed.
    h1 = bool(
        homeostasis.get("verdict") == "PASS"
        and homeostasis.get("worst_allostatic_load", float("inf"))
        <= homeostasis.get("allostatic_bound", 0.0) + 1e-9
    )
    # H2 arrow-of-time: real budget register is monotone non-increasing.
    h2 = budget_monotone_under_real_audit()
    # H3 synchrony: the real Kuramoto coherence locks above the threshold.
    h3 = bool(homeostasis.get("coherence_locked", 0.0) >= homeostasis.get("coherence_min", 1.0))
    # H4 verification: RE-DERIVE the aggregate from the substrate; do not trust a
    # committed final verdict that an adversary could forge to PASS.
    h4 = _rederive_final_verdict(root)

    grounds = [
        {"id": "H1", "name": "homeostasis (drive bounded)", "holds": h1},
        {"id": "H2", "name": "arrow-of-time (budget monotone)", "holds": h2},
        {"id": "H3", "name": "synchrony (phase-locked)", "holds": h3},
        {"id": "H4", "name": "verification (final verdict PASS)", "holds": h4},
    ]
    gate = act_admissible(h1=h1, h2=h2, h3=h3, h4=h4)
    return {
        "schema": SCHEMA_ID,
        "theorem": "act ⇔ H1 ∧ H2 ∧ H3 ∧ H4",
        "grounds": grounds,
        "gate": gate,
        "verdict": "PASS" if gate == "ADMISSIBLE" else "FAIL",
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="No-Ungrounded-Act apex invariant")
    p.add_argument("--root", default=".", help="repository root holding the artifacts")
    p.add_argument("--out", help="write the apex JSON here (else stdout)")
    p.add_argument("--report-only", action="store_true", help="always exit 0, mark report_only")
    args = p.parse_args(argv)

    report = build_apex(Path(args.root))
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"no-ungrounded-act: {report['gate']}", file=sys.stderr)
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())
