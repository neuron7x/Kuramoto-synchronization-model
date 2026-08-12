# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Evidence-bound epistemic-integrity weighting over the categorical claims audit.

The categorical auditor (:mod:`geosync.proof.audit`) hands every claim in
``docs/CLAIMS.yaml`` one of five verdicts (SUPPORTED / REFUTED / DANGLING /
NOT_TESTED / FORBIDDEN_LANGUAGE). This layer answers the question the categorical
verdict *cannot*: **how much is a SUPPORTED actually worth?**

A SUPPORTED whose falsifier can never fail (kills no injected mutant) is a green
light with no bulb behind it -- "a test that cannot fail is worthless". So each
SUPPORTED is CALIBRATED by its falsifier's *demonstrated* falsification power:
the recorded logic-mutation kill-rate of the module(s) the falsifier exercises.

DESIGN CONTRACT (the anti-laundering core)
------------------------------------------
* EVIDENCE-BOUND. The weight is a function of TWO inputs only: the audit rows
  and the ALREADY-RECORDED mutation manifests
  (``docs/MUTATION_KILL_BASELINE.json`` and
  ``artifacts/test_strength/mutation.modules.json``). This module runs NO
  mutations -- mutation probes rewrite source in place and must never run
  concurrently; refreshing evidence is a separate, opt-in, strictly-serial job.
* A falsifier with NO recorded mutation evidence is honestly marked
  ``UNMEASURED`` -- a distinct sentinel, NEVER a number, and NEVER 1.0. When a
  scalar is forced for aggregation it floors to 0.0: an unmeasured SUPPORTED
  contributes ZERO earned trust (fail-closed). This is the exact opposite of
  ``mutation_probe.Report.kill_rate``, which defaults ``total==0 -> 1.0`` -- the
  "unmeasured test looks proven-strong" trap. We deliberately do NOT inherit it.
* NO MAGIC NUMBERS. Every quantity is either (a) a MEASURED procedure output
  (killed / total from ``mutation_probe --only-logic``) or (b) a definitional
  endpoint of the signed epistemic scale {-1, 0, +1}. No hand-tuned weight,
  multiplier, or threshold enters the score. Tier (ANCHORED / EXTRAPOLATED) and
  priority (P0 / P1 / P2) are REPORTED as separate axes; they are never folded
  into the number as constants.
* SCOPE is stated, never hidden: falsification power here is LOGIC-falsification
  power (compare / boolop mutants -- the frozen ``--only-logic`` procedure).
  Constant / arithmetic mutants are deliberately out of scope.

The report is bound into the same tamper-evident envelope the categorical audit
uses (:func:`geosync.proof.run._content_digest`), so an external party trusts the
bytes, not the author.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# REUSE the categorical audit's verdict vocabulary and REJECT-class definition
# verbatim -- the weighting must never disagree with the audit about what a
# REJECT is. Zero new verdict constants are introduced here.
from geosync.proof.audit import (
    NOT_TESTED,
    REJECT,
    SUPPORTED,
    verdict_class,
)

# REUSE the provenance / tamper-evidence helpers verbatim -- the integrity report
# is the same species of provenance-bound artifact and must hash by the same rule.
from geosync.proof.run import (
    DIGEST_KEY,
    _content_digest,
    _relpath,
    _sha256_file,
    _utc_timestamp,
)

ROOT = Path(__file__).resolve().parents[2]
AUDIT_JSON = ROOT / "artifacts" / "geosync_proof" / "audit.json"
CLAIMS_YAML = ROOT / "docs" / "CLAIMS.yaml"
MUTATION_BASELINE = ROOT / "docs" / "MUTATION_KILL_BASELINE.json"
MUTATION_MODULES = ROOT / "artifacts" / "test_strength" / "mutation.modules.json"
ARTIFACT = ROOT / "artifacts" / "geosync_proof" / "integrity.json"

WEIGHTING_VERSION = "1"
REPRO_COMMAND = "python -m geosync.proof.weighting"

# --- SCOPE ------------------------------------------------------------------
# The recorded manifests are produced by ``tools/mutation_probe.py --only-logic``
# (compare / boolop AST swaps). Every power number carries this scope so a reader
# never mistakes it for full mutation coverage.
SCOPE = "logic:compare+boolop (mutation_probe --only-logic)"

# --- DEFINITIONAL SCALE ANCHORS (NOT tuned; these DEFINE the [-1, 1] scale) ---
# +1  maximal earned trust: a SUPPORTED claim whose falsifier kills EVERY
#     injected logic mutant (measured kill-rate == 1.0).
#  0  no net epistemic force: honestly untested, OR a SUPPORTED whose falsifier
#     was MEASURED to kill nothing (the Karpathy zero -- a passing but toothless
#     test earns nothing), OR a SUPPORTED whose teeth were never measured.
# -1  maximal NEGATIVE force: the claim's own machinery testifies against it
#     (falsifier FIRED, or is a phantom the auditor cannot collect, or breaches
#     the language firewall). These are exactly the audit's REJECT class.
G_REFUTED = -1.0
G_NEUTRAL = 0.0
G_MAX = 1.0

# The ONLY floor applied to an UNMEASURED power when a scalar is unavoidable.
# Any positive epsilon would itself be an unprovenanced magic constant, so 0.0 is
# the sole non-arbitrary choice: you may not credit teeth you never measured.
UNMEASURED_SCALAR_FLOOR = 0.0


# ===========================================================================
# Recorded mutation evidence  (READ-ONLY; never re-probed here)
# ===========================================================================
@dataclass(frozen=True)
class ModuleRecord:
    """One module's recorded logic-mutation result from a persisted manifest.

    ``killed`` / ``total`` are counts straight from ``mutation_probe --only-logic``.
    ``tests`` is the record's declared test file(s) -- the second join key when a
    claim's falsifier node lives in one of them.
    """

    module: str
    killed: int
    total: int
    tests: tuple[str, ...]
    manifest: str


def _split_tests(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        return ()
    return tuple(t for t in raw.split() if t)


def records_from_manifests(baseline: dict, modules: dict) -> list[ModuleRecord]:
    """Normalise both recorded manifests into a flat list of :class:`ModuleRecord`.

    * ``docs/MUTATION_KILL_BASELINE.json`` (the frozen ratchet ledger): each
      ``modules[path] = {killed, total, tests, ...}``.
    * ``artifacts/test_strength/mutation.modules.json``: each
      ``per_module[path] = {killed, valid_mutants, tests, ...}`` -- ``total`` is
      ``valid_mutants`` (mutants that compiled and are non-equivalent).

    No arithmetic beyond field selection; the counts are consumed verbatim.
    """
    out: list[ModuleRecord] = []
    for path, rec in sorted((baseline or {}).get("modules", {}).items()):
        out.append(
            ModuleRecord(
                module=path,
                killed=int(rec.get("killed", 0)),
                total=int(rec.get("total", 0)),
                tests=_split_tests(rec.get("tests")),
                manifest="MUTATION_KILL_BASELINE.json",
            )
        )
    for path, rec in sorted((modules or {}).get("per_module", {}).items()):
        out.append(
            ModuleRecord(
                module=path,
                killed=int(rec.get("killed", 0)),
                total=int(rec.get("valid_mutants", 0)),
                tests=_split_tests(rec.get("tests")),
                manifest="mutation.modules.json",
            )
        )
    return out


def load_records(
    baseline_path: Path = MUTATION_BASELINE,
    modules_path: Path = MUTATION_MODULES,
) -> list[ModuleRecord]:
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    )
    modules = json.loads(modules_path.read_text(encoding="utf-8")) if modules_path.exists() else {}
    return records_from_manifests(baseline, modules)


# ===========================================================================
# Falsification power
# ===========================================================================
_MEASURED = "MEASURED"
_UNMEASURED = "UNMEASURED"


@dataclass(frozen=True)
class FalsificationPower:
    """Demonstrated LOGIC-falsification power of a claim's falsifier, in [0, 1].

    ``state == "MEASURED"``   -> ``value`` is ``killed / total`` in [0, 1] and
                                 ``n_mutants`` (= pooled total) rides alongside as
                                 provenance. ``value == 0.0`` is a MEASURED zero
                                 (the falsifier ran against mutants and killed
                                 none) -- real teeth data, distinct from unmeasured.
    ``state == "UNMEASURED"`` -> ``value is None`` (a sentinel, NOT a number). No
                                 recorded run joins to this claim, or the joined
                                 record(s) had zero valid mutants (no teeth were
                                 DEMONSTRATED -- which is emphatically NOT perfect
                                 teeth, unlike mutation_probe's total==0 -> 1.0).

    :meth:`scalar` is the ONLY place a scalar is forced, and it floors UNMEASURED
    to :data:`UNMEASURED_SCALAR_FLOOR` (0.0). It is never 1.0.
    """

    state: str
    value: float | None
    n_mutants: int
    scope: str
    matched_modules: tuple[str, ...]
    reason: str = ""

    @property
    def measured(self) -> bool:
        return self.state == _MEASURED

    def scalar(self) -> float:
        """Collapse to a single number for aggregation -- fail-closed on UNMEASURED.

        MEASURED   -> the measured kill-rate.
        UNMEASURED -> 0.0. Explicitly NOT 1.0: an unmeasured falsifier has
        demonstrated no teeth, so it earns no calibrated support.
        """
        if self.state == _MEASURED and self.value is not None:
            return self.value
        return UNMEASURED_SCALAR_FLOOR

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "value": self.value,
            "scalar": round(self.scalar(), 6),
            "n_mutants": self.n_mutants,
            "scope": self.scope,
            "matched_modules": list(self.matched_modules),
            "reason": self.reason,
        }


def _unmeasured(reason: str, matched: tuple[str, ...] = ()) -> FalsificationPower:
    return FalsificationPower(
        state=_UNMEASURED,
        value=None,
        n_mutants=0,
        scope=SCOPE,
        matched_modules=matched,
        reason=reason,
    )


def _falsifier_test_file(test_id: object) -> str | None:
    if not isinstance(test_id, str) or not test_id:
        return None
    return test_id.split("::", 1)[0]


def _claim_files(claim: dict) -> set[str]:
    """Every repo-relative file a claim points at: its evidence_paths plus its
    falsifier's test file. These are matched against the mutation records."""
    files: set[str] = set()
    for p in claim.get("evidence_paths", []) or []:
        if isinstance(p, str):
            files.add(p)
    tf = _falsifier_test_file(claim.get("test_id"))
    if tf:
        files.add(tf)
    return files


def falsification_power(claim: dict, records: Sequence[ModuleRecord]) -> FalsificationPower:
    """Pooled logic-mutation kill-rate of the module(s) a claim's falsifier drives.

    Join (deterministic, two keys, no heuristics):
      1. SOURCE key   -- a recorded module whose path is one of the claim's files
         (``evidence_paths``).
      2. TESTS key    -- a recorded module whose declared ``tests`` include the
         claim's falsifier test file.

    Pool: ``killed = sum, total = sum`` over matched records. Then:
      * no match           -> UNMEASURED(no_record)
      * total == 0         -> UNMEASURED(zero_mutants)   (no teeth DEMONSTRATED)
      * otherwise          -> MEASURED(killed / total)   in [0, 1]

    Every input is a measured count; nothing is invented.
    """
    files = _claim_files(claim)
    matched: list[ModuleRecord] = []
    for r in records:
        if r.module in files or any(t in files for t in r.tests):
            matched.append(r)

    if not matched:
        return _unmeasured("no_record")

    modules = tuple(sorted({r.module for r in matched}))
    killed = sum(r.killed for r in matched)
    total = sum(r.total for r in matched)
    if total == 0:
        return _unmeasured("zero_mutants", modules)
    return FalsificationPower(
        state=_MEASURED,
        value=killed / total,
        n_mutants=total,
        scope=SCOPE,
        matched_modules=modules,
        reason="",
    )


def calibrated_support(verdict: str, power: FalsificationPower) -> float:
    """Earned trust of ONE claim = 1{verdict == SUPPORTED} x falsification_power.

    Only a SUPPORTED verdict can earn support, and only up to its demonstrated
    teeth. An unmeasured or toothless SUPPORTED earns 0.0.
    """
    return power.scalar() if verdict == SUPPORTED else 0.0


# ===========================================================================
# Per-claim signed contribution  g in [-1, 1]
# ===========================================================================
def claim_contribution(verdict: str, power: FalsificationPower) -> float:
    """Signed epistemic force of one claim on the [-1, 1] scale.

    SUPPORTED           -> +falsification_power  (0.0 if toothless / unmeasured)
    NOT_TESTED          ->  0.0                  (no net force)
    REFUTED / DANGLING / FORBIDDEN_LANGUAGE -> -1.0   (audit REJECT class;
                           the claim's own machinery testifies against it)

    Every value is a definitional endpoint or the MEASURED kill-rate. No interior
    constant is tuned. DANGLING maps to -1 (not an interior value) because the
    source audit already classes it REJECT: a named-but-uncollectable falsifier is
    a phantom guarantee, as bad as one that fired.
    """
    if verdict == SUPPORTED:
        return power.scalar()
    if verdict == NOT_TESTED:
        return G_NEUTRAL
    if verdict_class(verdict) == REJECT:  # REFUTED, DANGLING, FORBIDDEN_LANGUAGE
        return G_REFUTED
    return G_NEUTRAL


# ===========================================================================
# Aggregation  (weakest-link gate x size-weighted strength)
# ===========================================================================
@dataclass
class ScoredClaim:
    id: str
    priority: str
    tier: str
    verdict: str
    g: float
    power: FalsificationPower


def _merge_views(audit_rows: Iterable[dict], claims: Iterable[dict]) -> list[dict]:
    """Attach each claim's ``evidence_paths`` (from CLAIMS.yaml) to its audit row
    (which carries the verdict + test_id) by ``id``. The join key for mutation
    evidence lives in evidence_paths, which the audit report does not copy."""
    by_id = {str(c.get("id")): c for c in claims}
    views: list[dict] = []
    for row in audit_rows:
        cid = str(row.get("id"))
        src = by_id.get(cid, {})
        views.append(
            {
                "id": cid,
                "priority": str(row.get("priority", "")),
                "tier": str(row.get("tier", "")),
                "verdict": str(row.get("verdict", "")),
                "test_id": row.get("test_id"),
                "evidence_paths": src.get("evidence_paths", []),
            }
        )
    return views


def score_views(views: Sequence[dict], records: Sequence[ModuleRecord]) -> list[ScoredClaim]:
    scored: list[ScoredClaim] = []
    for v in views:
        power = falsification_power(v, records)
        g = claim_contribution(v["verdict"], power)
        scored.append(
            ScoredClaim(
                id=v["id"],
                priority=v.get("priority", ""),
                tier=v.get("tier", ""),
                verdict=v["verdict"],
                g=g,
                power=power,
            )
        )
    return scored


def _tally(members: Sequence[ScoredClaim]) -> dict:
    t: dict[str, int] = {}
    for m in members:
        t[m.verdict] = t.get(m.verdict, 0) + 1
    return dict(sorted(t.items()))


def _band_report(scored: Sequence[ScoredClaim]) -> dict:
    """Per-priority band diagnostics. The FLOOR (min g) is the weakest-link
    instrument: one REFUTED claim drives its band floor to -1 regardless of how
    many green claims share the band. Priority is expressed STRUCTURALLY (which
    band), never as a numeric multiplier."""
    bands: dict[str, list[ScoredClaim]] = {}
    for s in scored:
        bands.setdefault(s.priority or "<none>", []).append(s)
    out: dict[str, dict] = {}
    for p, members in sorted(bands.items()):
        gs = [m.g for m in members]
        supported = [m for m in members if m.verdict == SUPPORTED]
        measured = [m for m in supported if m.power.measured]
        out[p] = {
            "n": len(members),
            "floor_g": round(min(gs), 6),
            "mean_g": round(sum(gs) / len(gs), 6),
            "supported": len(supported),
            "supported_calibrated": len(measured),
            "verdicts": _tally(members),
        }
    return out


def integrity_score(scored: Sequence[ScoredClaim]) -> dict:
    """The headline epistemic-integrity measure E and its full accountancy.

    E = G * sum_c (g(c) + 1) / (2N)

      * N            = number of scored claims (a MEASURED count, the size weight)
      * (g + 1) / 2  = the exact affine remap of the definitional [-1, 1] scale to
                       [0, 1] (parameter-free; not tuning). Sum_max = 2N.
      * G (reject gate) = 0 if ANY claim is in the audit's REJECT class
        (REFUTED / DANGLING / FORBIDDEN_LANGUAGE), else 1. This mirrors the
        categorical audit's own weakest-link aggregate: E collapses to 0 exactly
        when the audit would REJECT, so a REFUTED claim can NEVER be hidden behind
        any number of green claims.

    Co-reported (mandatory) is ``calibration_coverage`` = the fraction of
    SUPPORTED claims whose teeth were actually MEASURED. E over mostly-uncalibrated
    SUPPORTEDs is a weak measure and must say so: a high E at low coverage is a red
    flag, not a pass.
    """
    n = len(scored)
    reject_ids = [s.id for s in scored if verdict_class(s.verdict) == REJECT]
    gate = 0 if reject_ids else 1

    raw_strength = 0.0 if n == 0 else sum((s.g + 1.0) / 2.0 for s in scored) / n
    e = gate * raw_strength

    supported = [s for s in scored if s.verdict == SUPPORTED]
    measured = [s for s in supported if s.power.measured]
    coverage: float | None = (len(measured) / len(supported)) if supported else None

    # Tier of E follows its weakest input. E is ANCHORED only when there is at
    # least one SUPPORTED claim AND every SUPPORTED one has MEASURED teeth
    # (coverage == 1.0) AND nothing is rejected. Anything short of that -- no
    # SUPPORTEDs to stand on, an uncalibrated SUPPORTED, or a REJECT -- leaves E
    # EXTRAPOLATED. No numeric coverage threshold is invented; the rule is exact.
    e_tier = "ANCHORED" if (supported and coverage == 1.0 and gate == 1) else "EXTRAPOLATED"

    return {
        "value": round(e, 6),
        "reject_gate": gate,
        "reject_class_ids": sorted(reject_ids),
        "raw_strength": round(raw_strength, 6),
        "sum_max": 2 * n,
        "n_claims": n,
        "calibration_coverage": (round(coverage, 6) if coverage is not None else None),
        "supported_total": len(supported),
        "supported_calibrated": len(measured),
        "tier": e_tier,
        "scope": SCOPE,
        "procedure": (
            "E = reject_gate * sum_c (g(c)+1) / (2N); "
            "g(SUPPORTED)=logic-mutation kill-rate (0.0 if unmeasured/toothless), "
            "g(NOT_TESTED)=0, g(REFUTED|DANGLING|FORBIDDEN_LANGUAGE)=-1; "
            "reject_gate=0 iff any REJECT-class verdict. Inputs: "
            "artifacts/geosync_proof/audit.json x recorded mutation manifests "
            "(docs/MUTATION_KILL_BASELINE.json, "
            "artifacts/test_strength/mutation.modules.json). "
            f"Repro: {REPRO_COMMAND}"
        ),
    }


# ===========================================================================
# File-bound report  (provenance + tamper-evidence)
# ===========================================================================
def _load_claims_yaml(path: Path) -> list[dict]:
    import yaml  # local import: PyYAML is already an audit dependency

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(doc, dict):
        return list(doc.get("claims", []))
    return list(doc or [])


def build_report(
    audit_path: Path = AUDIT_JSON,
    claims_path: Path = CLAIMS_YAML,
    baseline_path: Path = MUTATION_BASELINE,
    modules_path: Path = MUTATION_MODULES,
) -> dict:
    """Read the existing categorical audit + recorded mutation manifests and emit
    the provenance-bound, tamper-evident epistemic-integrity report. Runs NO
    mutations and mutates NO source."""
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    claims = _load_claims_yaml(claims_path)
    records = load_records(baseline_path, modules_path)

    views = _merge_views(audit.get("claims", []), claims)
    scored = score_views(views, records)

    e = integrity_score(scored)
    bands = _band_report(scored)

    rows = [
        {
            "id": s.id,
            "priority": s.priority,
            "tier": s.tier,
            "verdict": s.verdict,
            "g": round(s.g, 6),
            "calibrated_support": round(calibrated_support(s.verdict, s.power), 6),
            "power": s.power.as_dict(),
        }
        for s in scored
    ]

    report: dict[str, object] = {
        "weighting_version": WEIGHTING_VERSION,
        "repro_command": REPRO_COMMAND,
        "timestamp_utc": _utc_timestamp(),
        "scope": SCOPE,
        # Bind to the exact input bytes: any edit to the audit, the claims, or a
        # mutation manifest changes one of these hashes and invalidates the report.
        "audit_source": _relpath(audit_path),
        "audit_sha256": _sha256_file(audit_path) if audit_path.exists() else None,
        "audit_content_digest": audit.get(DIGEST_KEY),
        "claims_source": _relpath(claims_path),
        "claims_sha256": _sha256_file(claims_path) if claims_path.exists() else None,
        "mutation_baseline_source": _relpath(baseline_path),
        "mutation_baseline_sha256": (
            _sha256_file(baseline_path) if baseline_path.exists() else None
        ),
        "mutation_modules_source": _relpath(modules_path),
        "mutation_modules_sha256": (_sha256_file(modules_path) if modules_path.exists() else None),
        "epistemic_integrity": e,
        "bands": bands,
        "claims": rows,
    }
    report[DIGEST_KEY] = _content_digest(report)
    return report


def write_report(report: dict, path: Path = ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def summary_line(report: dict) -> str:
    e = report["epistemic_integrity"]
    cov = e["calibration_coverage"]
    cov_s = "n/a" if cov is None else f"{cov:.3f}"
    return (
        f"E={e['value']:.4f} tier={e['tier']} "
        f"reject_gate={e['reject_gate']} "
        f"calibration_coverage={cov_s} "
        f"({e['supported_calibrated']}/{e['supported_total']} SUPPORTED calibrated) "
        f"N={e['n_claims']} scope={e['scope']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Epistemic-integrity weighting over the claims audit.")
    ap.add_argument("--audit", type=Path, default=AUDIT_JSON)
    ap.add_argument("--claims", type=Path, default=CLAIMS_YAML)
    ap.add_argument("--baseline", type=Path, default=MUTATION_BASELINE)
    ap.add_argument("--modules", type=Path, default=MUTATION_MODULES)
    ap.add_argument("--out", type=Path, default=ARTIFACT)
    ap.add_argument(
        "--no-write", action="store_true", help="print the summary, do not write the artifact"
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    report = build_report(args.audit, args.claims, args.baseline, args.modules)
    if not args.no_write:
        write_report(report, args.out)
    sys.stdout.write(summary_line(report) + "\n")
    # Fail-closed exit: nonzero iff the reject gate is down (the audit would REJECT).
    return 0 if report["epistemic_integrity"]["reject_gate"] == 1 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
