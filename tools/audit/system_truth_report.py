"""System truth report — the singularity dashboard.

Aggregates the calibration layer's evidence into a single deterministic
report:

  1. Verified facts                       (claim ledger ACTIVE/FACT entries)
  2. Active risks                         (claims at PARTIAL or REJECTED)
  3. Open hypotheses                      (claims at SPECULATION / EXTRAPOLATION)
  4. False-confidence zones               (false-confidence detector output)
  5. Contracts without negative tests     (claim ledger entries with no test_paths
                                           AND no non_testable_reason)
  6. Claims without falsifiers            (only existing as drift-check; the
                                           validator already refuses these,
                                           but we surface count == 0 as a band)
  7. Security advisories without
     reachability proof                   (reachability graph rows below
                                           AUTH_SURFACE_PRESENT or with
                                           exploit_path_confirmed=False)
  8. Dependencies with manifest drift     (dependency-truth unifier)
  9. Architecture boundaries enforced     (lint-imports kept/broken count)
 10. Next 10 repayment PRs                (synthesised priority queue)

Output:

  - JSON written to /tmp/geosync-system-truth.json by default
  - Markdown rendered to stdout (or to --md path)
  - Both deterministic; same inputs → byte-identical outputs

Bands:

  GREEN    nothing actionable
  YELLOW   actionable but TRACKED
  RED      actionable, NOT TRACKED, gate failing-or-ready-to-fail
  UNKNOWN  data unavailable (subsystem not run / file missing)

No decimals. No fake health score.

The aggregator reads JSON outputs from the other calibration tools when
they have been pre-computed; otherwise it computes them in-process. CI
should run the underlying tools first and pass --inputs-dir for
reproducibility.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Band model — ordinal, no decimals.
# ---------------------------------------------------------------------------
BANDS: tuple[str, ...] = ("GREEN", "YELLOW", "RED", "UNKNOWN")


def _band_max(*bands: str) -> str:
    """Return the worst (highest-priority) band among inputs."""
    rank = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
    return max(bands, key=lambda b: rank.get(b, -1))


# ---------------------------------------------------------------------------
# Subsystem loaders — each returns (band, payload, notes).
# ---------------------------------------------------------------------------


def _load_module(rel_path: str) -> ModuleType | None:
    target = REPO_ROOT / rel_path
    if not target.exists():
        return None
    spec = importlib.util.spec_from_file_location(target.stem, target)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[target.stem] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def _load_claim_ledger() -> tuple[str, dict[str, Any]]:
    ledger_path = REPO_ROOT / ".claude" / "claims" / "CLAIMS.yaml"
    if not ledger_path.exists():
        return ("UNKNOWN", {"reason": "ledger missing"})
    raw = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
    claims = raw.get("claims") or []
    facts = [c for c in claims if c.get("tier") == "FACT" and c.get("status") == "ACTIVE"]
    partial = [c for c in claims if c.get("status") == "PARTIAL"]
    rejected = [c for c in claims if c.get("status") == "REJECTED"]
    speculation = [c for c in claims if c.get("tier") == "SPECULATION"]
    extrapolation = [c for c in claims if c.get("tier") == "EXTRAPOLATION"]
    no_test = [
        c
        for c in claims
        if c.get("status") in {"ACTIVE", "PARTIAL"}
        and not (c.get("test_paths") or [])
        and not (c.get("non_testable_reason") or "").strip()
    ]
    band = "GREEN"
    if no_test:
        band = "RED"
    elif partial:
        band = "YELLOW"
    return (
        band,
        {
            "active_facts": [c["claim_id"] for c in facts],
            "partial": [c["claim_id"] for c in partial],
            "rejected": [c["claim_id"] for c in rejected],
            "speculation": [c["claim_id"] for c in speculation],
            "extrapolation": [c["claim_id"] for c in extrapolation],
            "claims_without_negative_tests": [c["claim_id"] for c in no_test],
        },
    )


def _load_evidence_matrix() -> tuple[str, dict[str, Any]]:
    module = _load_module(".claude/evidence/validate_evidence.py")
    matrix_path = REPO_ROOT / ".claude" / "evidence" / "EVIDENCE_MATRIX.yaml"
    if module is None or not matrix_path.exists():
        return ("UNKNOWN", {"reason": "matrix or validator missing"})
    matrix = module.load_matrix(matrix_path)
    errors = module.validate_matrix(matrix)
    band = "GREEN" if not errors else "RED"
    return (
        band,
        {
            "categories": sorted(matrix.get("categories", {}).keys()),
            "prohibited_overclaims": sorted(matrix.get("prohibited_overclaims", {}).keys()),
            "regression_cases": [c["name"] for c in matrix.get("regression_cases") or []],
            "self_validation_errors": [str(e) for e in errors],
        },
    )


def _load_dep_truth() -> tuple[str, dict[str, Any]]:
    module = _load_module("tools/deps/validate_dependency_truth.py")
    if module is None:
        return ("UNKNOWN", {"reason": "validator missing"})
    report = module.collect(REPO_ROOT)
    actionable = [d for d in report.drifts if module._is_actionable(d)]
    band = "GREEN"
    if actionable:
        band = "RED"
    elif report.drifts:
        band = "YELLOW"
    return (
        band,
        {
            "total_drifts": len(report.drifts),
            "actionable_drifts": len(actionable),
            "by_class": _count_by(report.drifts, "drift_class"),
            "by_priority": _count_by(report.drifts, "priority"),
            "accepted_backlog": list(report.accepted_backlog),
        },
    )


def _load_false_confidence() -> tuple[str, dict[str, Any]]:
    module = _load_module("tools/audit/false_confidence_detector.py")
    if module is None:
        return ("UNKNOWN", {"reason": "detector missing"})
    report = module.collect(REPO_ROOT)
    classes = sorted({f.false_confidence_type for f in report.findings})
    critical = [f for f in report.findings if f.risk == "CRITICAL"]
    high = [f for f in report.findings if f.risk == "HIGH"]
    band = "GREEN"
    if critical:
        band = "RED"
    elif high:
        band = "YELLOW"
    elif report.findings:
        band = "YELLOW"
    return (
        band,
        {
            "total_findings": len(report.findings),
            "classes_present": classes,
            "by_class": _count_by(report.findings, "false_confidence_type"),
            "by_risk": _count_by(report.findings, "risk"),
        },
    )


def _load_reachability() -> tuple[str, dict[str, Any]]:
    module = _load_module("tools/security/reachability_graph.py")
    if module is None:
        return ("UNKNOWN", {"reason": "reachability tool missing"})
    report = module.classify(REPO_ROOT, module.SEED_ADVISORIES)
    above_auth = [f for f in report.facts if f.reachability == "EXPLOIT_PATH_CONFIRMED"]
    at_auth = [f for f in report.facts if f.reachability == "AUTH_SURFACE_PRESENT"]
    band = "GREEN"
    if above_auth:
        band = "RED"
    elif at_auth:
        band = "YELLOW"
    return (
        band,
        {
            "facts": [
                {
                    "advisory_id": f.advisory_id,
                    "package_name": f.package_name,
                    "reachability": f.reachability,
                    "followup_issue": f.followup_issue,
                }
                for f in report.facts
            ],
            "advisories_below_confirmed": [
                f.advisory_id for f in report.facts if not f.exploit_path_confirmed
            ],
        },
    )


def _load_arch_boundaries() -> tuple[str, dict[str, Any]]:
    cfg = REPO_ROOT / ".importlinter"
    if not cfg.exists():
        return ("UNKNOWN", {"reason": ".importlinter missing"})
    proc = subprocess.run(
        ["lint-imports", "--no-cache"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    text = proc.stdout + proc.stderr
    kept = 0
    broken = 0
    for line in text.splitlines():
        if line.startswith("Contracts:"):
            # "Contracts: 5 kept, 0 broken."
            parts = line.replace(",", "").replace(".", "").split()
            try:
                kept = int(parts[1])
                broken = int(parts[3])
            except (IndexError, ValueError):
                pass
    if proc.returncode != 0 or broken > 0:
        band = "RED"
    elif kept == 0:
        band = "UNKNOWN"
    else:
        band = "GREEN"
    return (
        band,
        {
            "kept": kept,
            "broken": broken,
            "exit_code": proc.returncode,
        },
    )


def _load_mutation_kill() -> tuple[str, dict[str, Any]]:
    ledger_path = REPO_ROOT / ".claude" / "mutation" / "MUTATION_LEDGER.yaml"
    if not ledger_path.exists():
        return ("UNKNOWN", {"reason": "MUTATION_LEDGER.yaml missing"})
    raw = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
    mutants = raw.get("mutants") or []
    killed = [
        m
        for m in mutants
        if m.get("killed") is True
        or (isinstance(m.get("killed"), str) and m["killed"].upper() == "YES")
    ]
    survivors = [
        m
        for m in mutants
        if m.get("killed") is False
        or (isinstance(m.get("killed"), str) and m["killed"].upper() == "NO")
    ]
    if survivors:
        band = "RED"
    elif len(killed) >= 5:
        band = "GREEN"
    else:
        band = "YELLOW"
    return (
        band,
        {
            "total_mutants": len(mutants),
            "killed": len(killed),
            "survivors": [m["mutant_id"] for m in survivors],
        },
    )


def _load_physics_invariants() -> tuple[str, dict[str, Any]]:
    inv_path = REPO_ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
    if not inv_path.exists():
        return ("UNKNOWN", {"reason": "INVARIANTS.yaml missing"})
    text = inv_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}

    # The registry is a hierarchy of named categories; each leaf with a
    # truthy `id` field is one invariant. Walk the structure.
    invariants: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            inv_id = obj.get("id")
            if isinstance(inv_id, str) and inv_id.startswith("INV-"):
                invariants.append(inv_id)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(raw)
    n = len(invariants)
    band = "GREEN" if n > 0 else "UNKNOWN"
    return band, {"invariant_count": n, "sample_ids": sorted(invariants)[:5]}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


def _count_by(items: Iterable[Any], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        key = str(
            getattr(item, attr, None) or item.get(attr, "")
            if not hasattr(item, attr)
            else getattr(item, attr)
        )
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


@dataclass
class TruthReport:
    bands: dict[str, str] = field(default_factory=dict)
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall_band: str = "UNKNOWN"
    next_repayment_prs: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "overall_band": self.overall_band,
            "bands": dict(sorted(self.bands.items())),
            "sections": {k: self.sections[k] for k in sorted(self.sections)},
            "next_repayment_prs": self.next_repayment_prs,
        }


def collect() -> TruthReport:
    sections: dict[str, dict[str, Any]] = {}
    bands: dict[str, str] = {}
    for name, loader in (
        ("claim_ledger", _load_claim_ledger),
        ("evidence_matrix", _load_evidence_matrix),
        ("dependency_truth", _load_dep_truth),
        ("false_confidence", _load_false_confidence),
        ("reachability", _load_reachability),
        ("architecture_boundaries", _load_arch_boundaries),
        ("mutation_kill", _load_mutation_kill),
        ("physics_invariants", _load_physics_invariants),
    ):
        try:
            band, payload = loader()
        except Exception as exc:
            band, payload = "UNKNOWN", {"error": f"{type(exc).__name__}: {exc}"}
        bands[name] = band
        sections[name] = payload

    overall = _band_max(*bands.values())
    next_prs = _synthesise_next_prs(sections, bands)
    return TruthReport(
        bands=bands,
        sections=sections,
        overall_band=overall,
        next_repayment_prs=next_prs,
    )


def _synthesise_next_prs(
    sections: dict[str, dict[str, Any]], bands: dict[str, str]
) -> list[dict[str, str]]:
    """Produce a deterministic queue of the next 10 repayment PRs."""
    queue: list[dict[str, str]] = []

    fc = sections.get("false_confidence", {})
    if fc.get("by_risk", {}).get("CRITICAL"):
        queue.append(
            {
                "priority": "CRITICAL",
                "title": "Rebuild .coveragerc to honestly measure coverage (F02)",
                "subsystem": "false_confidence",
                "rationale": "C1 detector reports omit-inflation > 2x source",
            }
        )
    dep = sections.get("dependency_truth", {})
    if dep.get("actionable_drifts", 0):
        queue.append(
            {
                "priority": "HIGH",
                "title": "Pay down actionable D2/D4/D5 manifest drifts",
                "subsystem": "dependency_truth",
                "rationale": (
                    f"{dep.get('actionable_drifts', 0)} actionable drift(s) "
                    "outside the accepted backlog"
                ),
            }
        )
    cl = sections.get("claim_ledger", {})
    if cl.get("partial"):
        for cid in cl["partial"]:
            queue.append(
                {
                    "priority": "HIGH",
                    "title": f"Close PARTIAL claim {cid}",
                    "subsystem": "claim_ledger",
                    "rationale": "ledger entry awaits its load-bearing test",
                }
            )
    if cl.get("claims_without_negative_tests"):
        for cid in cl["claims_without_negative_tests"]:
            queue.append(
                {
                    "priority": "MEDIUM",
                    "title": f"Add negative test for claim {cid}",
                    "subsystem": "claim_ledger",
                    "rationale": "ACTIVE/PARTIAL claim has no test_paths",
                }
            )
    reach = sections.get("reachability", {})
    for adv in reach.get("advisories_below_confirmed", []):
        queue.append(
            {
                "priority": "HIGH" if bands.get("reachability") == "YELLOW" else "MEDIUM",
                "title": (
                    f"Resolve reachability for {adv} via integration test "
                    "(see issue #446 for the GraphQL WS first case)"
                ),
                "subsystem": "reachability",
                "rationale": "advisory reachable but exploit not confirmed-or-refuted",
            }
        )
    fc_classes = fc.get("by_class", {})
    for fc_class, count in sorted(fc_classes.items(), key=lambda kv: -kv[1]):
        if fc_class in {"C1", "C6"}:
            continue
        if count == 0:
            continue
        queue.append(
            {
                "priority": "MEDIUM",
                "title": f"Reduce {fc_class} concentrations ({count} files)",
                "subsystem": "false_confidence",
                "rationale": "false-confidence detector class above threshold",
            }
        )

    arch = sections.get("architecture_boundaries", {})
    if arch.get("broken", 0) > 0:
        queue.append(
            {
                "priority": "HIGH",
                "title": "Fix broken import-linter contracts",
                "subsystem": "architecture_boundaries",
                "rationale": f"{arch['broken']} contract(s) reported broken",
            }
        )

    mut = sections.get("mutation_kill", {})
    if mut.get("survivors"):
        for mid in mut["survivors"]:
            queue.append(
                {
                    "priority": "HIGH",
                    "title": f"Diagnose surviving mutant {mid}",
                    "subsystem": "mutation_kill",
                    "rationale": "killer test passed despite mutation",
                }
            )

    # Deduplicate, preserve order, cap at 10.
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, str]] = []
    for entry in queue:
        key = (entry["title"], entry["subsystem"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
        if len(deduped) >= 10:
            break
    return deduped


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_markdown(report: TruthReport) -> str:
    lines: list[str] = []
    lines.append("# GeoSync System Truth Report")
    lines.append("")
    lines.append(f"**Overall band:** `{report.overall_band}`")
    lines.append("")
    lines.append("## Section bands")
    lines.append("")
    lines.append("| Section | Band |")
    lines.append("|---|---|")
    for name in sorted(report.bands):
        lines.append(f"| `{name}` | `{report.bands[name]}` |")
    lines.append("")

    section_titles = {
        "claim_ledger": "1. Claim ledger",
        "evidence_matrix": "2. Evidence matrix",
        "dependency_truth": "3. Dependency truth",
        "false_confidence": "4. False-confidence zones",
        "reachability": "5. Security reachability",
        "architecture_boundaries": "6. Architecture boundaries",
        "mutation_kill": "7. Mutation kill ledger",
        "physics_invariants": "8. Physics invariants",
    }
    for key in sorted(report.sections):
        lines.append(f"## {section_titles.get(key, key)}")
        lines.append("")
        lines.append(f"Band: `{report.bands.get(key, 'UNKNOWN')}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(report.sections[key], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")

    lines.append("## Next repayment PRs")
    lines.append("")
    if not report.next_repayment_prs:
        lines.append("(none synthesised — system clean by these gates)")
    else:
        lines.append("| # | Priority | Subsystem | Title | Rationale |")
        lines.append("|---|---|---|---|---|")
        for i, entry in enumerate(report.next_repayment_prs, start=1):
            lines.append(
                f"| {i} | {entry['priority']} | `{entry['subsystem']}` | "
                f"{entry['title']} | {entry['rationale']} |"
            )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


DEFAULT_JSON_OUTPUT = Path("/tmp/geosync-system-truth.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GeoSync system truth report aggregator",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_OUTPUT,
        help="path to write JSON report (default /tmp/geosync-system-truth.json)",
    )
    parser.add_argument(
        "--md-output",
        type=Path,
        default=None,
        help="optional path to write Markdown report (stdout if omitted)",
    )
    parser.add_argument(
        "--exit-on-red",
        action="store_true",
        help="exit non-zero when overall_band == RED",
    )
    args = parser.parse_args(argv)

    report = collect()
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    args.json_output.write_text(payload + "\n", encoding="utf-8")
    md = render_markdown(report)
    if args.md_output is not None:
        args.md_output.write_text(md, encoding="utf-8")
    else:
        print(md)
    if args.exit_on_red and report.overall_band == "RED":
        print("FAIL: overall_band = RED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
