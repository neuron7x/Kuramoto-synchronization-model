#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physics documentation canon gate — make the canon machine-checkable.

The physics layer is described across a catalog of laws
(``physics_contracts/catalog.yaml``), an invariant registry
(``.claude/physics/INVARIANTS.yaml``), and a network of docs. Before this gate,
nothing forced a *single* canonical specification to stay in sync with those
substrates, and nothing stopped a physics domain from being silently omitted or
mislabelled. This gate closes that gap.

It binds every catalog law and every registry invariant to exactly one of seven
classified domains (``docs/PHYSICS_CANON.manifest.json``) and fail-closes when:

* a law / invariant is not classified (completeness — nothing silently dropped);
* the committed manifest disagrees with what the substrates actually contain
  (drift — the canon went stale);
* a registry section has no domain mapping (an unclassified physics surface);
* a canonical physics doc carries overclaim language (forecast / alpha /
  predictor / market-law) outside a quoted/negated context;
* the documentation index is missing entries, has unknown roles/domains, or
  points at files that do not exist.

``--write`` regenerates the manifest from the substrates (the gate is also its
own generator, mirroring ``check_physics_law_witness_index.py --write``); the
default mode verifies the committed manifest and the canonical docs.

Maturity vocabulary (per the physics-documentation audit): ``FORMAL_LAW``,
``INVARIANT``, ``DERIVED_COMPUTATIONAL_PROPERTY``, ``HYPOTHESIS``,
``NON_CLAIM_ANALOGY``. A domain may never imply a maturity above its evidence.

Exit codes::

    0  manifest in sync and canonical docs clean (or --write applied)
    1  drift, unclassified surface, overclaim, or doc-index fault
    2  a substrate / manifest file is unreadable
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "physics_contracts" / "catalog.yaml"
REGISTRY = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
MANIFEST = ROOT / "docs" / "PHYSICS_CANON.manifest.json"
DOC_INDEX = ROOT / "docs" / "DOCUMENTATION_INDEX.manifest.json"

# Canonical physics docs whose prose must stay free of overclaim language.
CANON_DOCS: tuple[Path, ...] = (
    ROOT / "docs" / "PHYSICS_CANON.md",
    ROOT / "docs" / "PHYSICS_GLOSSARY.md",
    ROOT / "docs" / "PHYSICS_MATURITY_MATRIX.md",
)

SCHEMA_VERSION = "1.0"

# --- domain buckets ---------------------------------------------------------

# Seven classified buckets. ``kind`` records whether a domain is a physical
# law, a research hypothesis, a non-physics computational contract, a
# conceptual analogy, or a research ontology — so a neuro-modulator or an
# ontology axiom can never be read as a market-physics law (audit NC-03).
BUCKET_POLICY: dict[str, dict[str, str]] = {
    "graph_geometry": {
        "kind": "physics_law",
        "maturity": "FORMAL_LAW",
        "allowed_claim": "Discrete graph-curvature theorems (Ollivier/Forman, "
        "Gauss-Bonnet) hold within their stated validity domain.",
        "forbidden_claim": "No claim that market structure is governed by curvature.",
        "verification_command": "pytest -q tests/unit/physics -k 'ricci or curvature'",
    },
    "nonlinear_synchronization": {
        "kind": "physics_law",
        "maturity": "FORMAL_LAW",
        "allowed_claim": "Kuramoto / Ott-Antonsen / Lyapunov results hold for the "
        "stated coupling model and finite-size regime.",
        "forbidden_claim": "No claim that asset returns synchronize as a market law.",
        "verification_command": "pytest -q tests/unit/physics -k 'kuramoto or lyapunov'",
    },
    "computational_physics_contract": {
        "kind": "derived_computational_property",
        "maturity": "DERIVED_COMPUTATIONAL_PROPERTY",
        "allowed_claim": "Thermodynamic / fluctuation / determinism identities are "
        "derived properties of the implementation, not empirical market facts.",
        "forbidden_claim": "No claim that markets obey these identities.",
        "verification_command": "pytest -q tests/unit/physics -k 'thermo or determinism or uncertainty'",
    },
    "market_microstructure_hypothesis": {
        "kind": "research_hypothesis",
        "maturity": "HYPOTHESIS",
        "allowed_claim": "Microstructure descriptors are falsifiable research "
        "hypotheses; promotion needs real-data evidence with hashes and a null baseline.",
        "forbidden_claim": "No out-of-sample edge, profitability, or rank is asserted.",
        "verification_command": "pytest -q tests/unit -k 'dro_ara or manifold or coherence'",
    },
    "neuro_symbolic_analogy": {
        "kind": "non_claim_analogy",
        "maturity": "NON_CLAIM_ANALOGY",
        "allowed_claim": "Neuro-modulator dynamics are engineering analogies used as "
        "risk instrumentation; the biological labels are arithmetic proxies.",
        "forbidden_claim": "Not a biological claim and not a market-physics law.",
        "verification_command": "pytest -q tests/unit -k 'serotonin or dopamine or gaba or cryptobiosis'",
    },
    "execution_infrastructure": {
        "kind": "execution_contract",
        "maturity": "INVARIANT",
        "allowed_claim": "Sizing / order-management / bus / kernel invariants are "
        "machine-checkable contracts of the computation.",
        "forbidden_claim": "Not a claim of profitability or live-venue readiness.",
        "verification_command": "pytest -q tests/unit -k 'kelly or oms or signalbus or hpc'",
    },
    "personal_research_ontology": {
        "kind": "research_ontology",
        "maturity": "NON_CLAIM_ANALOGY",
        "allowed_claim": "Gradient-ontology and cosmological-compute axioms are the "
        "author's research framing, scoped to the system's own substrate.",
        "forbidden_claim": "Not physics of markets and not an empirical claim.",
        "verification_command": "pytest -q tests/unit -k 'gradient or pncc'",
    },
}

# Registry top-level section -> bucket. Fail-closed: an unmapped section is an
# unclassified physics surface, not a silent pass.
SECTION_TO_BUCKET: dict[str, str] = {
    "gradient_ontology": "personal_research_ontology",
    "pncc": "personal_research_ontology",
    "kuramoto": "nonlinear_synchronization",
    "capital_weighted_kuramoto": "nonlinear_synchronization",
    "higher_order_kuramoto": "nonlinear_synchronization",
    "explosive_sync": "nonlinear_synchronization",
    "ott_antonsen": "nonlinear_synchronization",
    "lyapunov_exponent": "nonlinear_synchronization",
    "stuart_landau_es": "nonlinear_synchronization",
    "spectral_gap": "nonlinear_synchronization",
    # Seven-Law Constitutional Physics Act (Laws T1–T7): synchronization-side
    # laws (Kuramoto-Ricci onset, Lyapunov spectrum, coupling calibration,
    # pinning control of chaos) are formal nonlinear-synchronization results.
    "law_t1_kuramoto_ricci_sync_onset": "nonlinear_synchronization",
    "law_t2_lyapunov_full_spectrum": "nonlinear_synchronization",
    "law_t3_coupling_calibration": "nonlinear_synchronization",
    "law_t7_pinning_control": "nonlinear_synchronization",
    "ricci": "graph_geometry",
    "ricci_flow": "graph_geometry",
    "kuramoto_ricci_semantics": "graph_geometry",
    "thermodynamics": "computational_physics_contract",
    "stochastic_thermodynamics": "computational_physics_contract",
    "free_energy": "computational_physics_contract",
    "robust_free_energy": "computational_physics_contract",
    "gabor_uncertainty": "computational_physics_contract",
    # Law T5 predictability horizon under a Landauer energy budget is a
    # thermodynamic/computational-physics contract, not a market claim.
    "law_t5_predictability_landauer": "computational_physics_contract",
    "dro_ara": "market_microstructure_hypothesis",
    "coherence_bridge": "market_microstructure_hypothesis",
    "adaptive_criticality": "market_microstructure_hypothesis",
    "serotonin": "neuro_symbolic_analogy",
    "dopamine": "neuro_symbolic_analogy",
    "gaba": "neuro_symbolic_analogy",
    "cryptobiosis": "neuro_symbolic_analogy",
    "neuro_homeostatic": "neuro_symbolic_analogy",
    "kelly": "execution_infrastructure",
    "oms": "execution_infrastructure",
    "signalbus": "execution_infrastructure",
    "hpc": "execution_infrastructure",
    "api_contract": "execution_infrastructure",
    "rebus": "execution_infrastructure",
    # Law T6 bit-identical reproducibility kit is a determinism/reproducibility
    # infrastructure contract (sibling of hpc seeded reproducibility).
    "law_t6_determinism_kit": "execution_infrastructure",
}

# Law dotted-id prefix -> bucket. Order matters: longer/more specific first.
LAW_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("kuramoto_ricci.", "graph_geometry"),
    ("ricci.", "graph_geometry"),
    ("kuramoto.", "nonlinear_synchronization"),
    ("thermo.", "computational_physics_contract"),
    ("ecs.", "computational_physics_contract"),
    ("dro_ara.", "market_microstructure_hypothesis"),
    ("manifold.", "market_microstructure_hypothesis"),
    ("serotonin.", "neuro_symbolic_analogy"),
    ("dopamine.", "neuro_symbolic_analogy"),
    ("gaba.", "neuro_symbolic_analogy"),
    ("kelly.", "execution_infrastructure"),
    ("oms.", "execution_infrastructure"),
    ("signalbus.", "execution_infrastructure"),
    ("hpc.", "execution_infrastructure"),
    ("pncc.", "personal_research_ontology"),
)

# Overclaim patterns scanned in canonical physics docs (subset of the
# product-category firewall, sufficient for prose review).
OVERCLAIM_PATTERNS: tuple[str, ...] = (
    r"validated[ -]alpha",
    r"proven[ -](predictor|alpha|edge|market[ -]law)",
    r"guaranteed[ -](edge|profit|return)",
    r"deployable[ -](alpha|strategy|signal)",
    r"(price|market|return|alpha)[ -]predictor",
    r"law[ -]of[ -]markets",
    r"market[ -]physics[ -]proven",
)
_OVERCLAIM = tuple(re.compile(p, re.IGNORECASE) for p in OVERCLAIM_PATTERNS)
# A line is exempt if it negates / quotes / enumerates the banned phrasing.
_NEGATION = re.compile(
    r"\b(not|no|never|without|forbid|forbidden|banned|excluded?|must not|"
    r"cannot|disallow|prohibit)\b",
    re.IGNORECASE,
)

DOC_INDEX_ROLES = frozenset(
    {
        "canonical",
        "audit",
        "agent",
        "archive",
        "evidence",
        "research_draft",
        "ops",
        "deprecated",
        "general",
    }
)
DOC_INDEX_DOMAINS = frozenset(
    {"physics", "governance", "inference", "data", "release", "agent", "general"}
)


# --- extraction -------------------------------------------------------------


def _rel(path: Path) -> str:
    """Repo-relative path for messages; falls back to the name if outside ROOT."""

    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return path.name


def load_law_ids() -> list[str]:
    """Return every dotted law id from the catalog (sorted, unique)."""

    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    entries = data.get("laws", data) if isinstance(data, dict) else data
    ids = {str(e["id"]) for e in entries if isinstance(e, dict) and "id" in e}
    return sorted(ids)


def load_invariant_sections() -> dict[str, list[str]]:
    """Return ``section -> [invariant ids]`` from the registry."""

    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("INVARIANTS.yaml top level is not a mapping")
    out: dict[str, list[str]] = {}
    for section, body in data.items():
        ids: list[str] = []
        _collect_ids(body, ids)
        if ids:
            out[str(section)] = sorted(set(ids))
    return out


def _collect_ids(node: Any, acc: list[str]) -> None:
    """Recursively collect ``id: INV-*`` values under a registry node."""

    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str) and value.startswith("INV-"):
                acc.append(value)
            else:
                _collect_ids(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_ids(item, acc)


def classify_law(law_id: str) -> str | None:
    for prefix, bucket in LAW_PREFIX_RULES:
        if law_id.startswith(prefix):
            return bucket
    return None


# --- manifest build ---------------------------------------------------------


def build_manifest() -> dict[str, Any]:
    """Build the canonical manifest from the substrates; raise on any gap."""

    law_ids = load_law_ids()
    sections = load_invariant_sections()

    domains: dict[str, dict[str, Any]] = {
        name: {**BUCKET_POLICY[name], "laws": [], "invariants": []} for name in BUCKET_POLICY
    }

    unclassified_laws = []
    for law_id in law_ids:
        bucket = classify_law(law_id)
        if bucket is None:
            unclassified_laws.append(law_id)
        else:
            domains[bucket]["laws"].append(law_id)

    unmapped_sections = []
    total_invariants = 0
    for section, ids in sections.items():
        bucket = SECTION_TO_BUCKET.get(section)
        if bucket is None:
            unmapped_sections.append(section)
            continue
        domains[bucket]["invariants"].extend(ids)
        total_invariants += len(ids)

    if unclassified_laws:
        raise ValueError(f"unclassified laws (no prefix rule): {unclassified_laws}")
    if unmapped_sections:
        raise ValueError(f"unmapped registry sections (no domain): {unmapped_sections}")

    for d in domains.values():
        d["laws"] = sorted(d["laws"])
        d["invariants"] = sorted(d["invariants"])

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "scripts/ci/check_physics_docs_canon.py --write",
        "sources": {
            "laws": "physics_contracts/catalog.yaml",
            "invariants": ".claude/physics/INVARIANTS.yaml",
        },
        "maturity_vocabulary": [
            "FORMAL_LAW",
            "INVARIANT",
            "DERIVED_COMPUTATIONAL_PROPERTY",
            "HYPOTHESIS",
            "NON_CLAIM_ANALOGY",
        ],
        "domains": domains,
        "totals": {"laws": len(law_ids), "invariants": total_invariants},
    }


def _dump(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


# --- checks -----------------------------------------------------------------


def check_manifest(manifest_text: str) -> list[str]:
    """Compare the committed manifest against the freshly built one."""

    errors: list[str] = []
    expected = build_manifest()
    try:
        committed = json.loads(manifest_text)
    except json.JSONDecodeError as exc:
        return [f"manifest is not valid JSON: {exc}"]

    if committed != expected:
        # Pinpoint the divergence per domain rather than dumping the whole tree.
        exp_d = expected["domains"]
        com_d = committed.get("domains", {})
        for name in sorted(exp_d):
            for field in ("laws", "invariants"):
                e = set(exp_d[name][field])
                c = set(com_d.get(name, {}).get(field, []))
                if e != c:
                    missing = sorted(e - c)
                    extra = sorted(c - e)
                    errors.append(f"domain {name}.{field} drift: missing={missing} extra={extra}")
        if committed.get("totals") != expected["totals"]:
            errors.append(
                f"totals drift: committed={committed.get('totals')} expected={expected['totals']}"
            )
        if not errors:
            errors.append("manifest differs from rebuild (policy/metadata field drift)")
    return errors


def check_canon_docs() -> list[str]:
    """Scan canonical physics docs for unquoted overclaim language."""

    errors: list[str] = []
    for doc in CANON_DOCS:
        if not doc.is_file():
            errors.append(f"missing canonical doc: {_rel(doc)}")
            continue
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if _NEGATION.search(line):
                continue
            for pat in _OVERCLAIM:
                if pat.search(line):
                    errors.append(
                        f"{_rel(doc)}:{lineno} overclaim '{pat.pattern}': {line.strip()[:80]}"
                    )
    return errors


def check_doc_index() -> list[str]:
    """Validate the documentation index manifest."""

    errors: list[str] = []
    if not DOC_INDEX.is_file():
        return [f"missing {_rel(DOC_INDEX)}"]
    try:
        data = json.loads(DOC_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"documentation index is not valid JSON: {exc}"]
    entries = data.get("entries", data) if isinstance(data, dict) else data
    if not isinstance(entries, list) or not entries:
        return ["documentation index has no entries"]
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {i} is not an object")
            continue
        for key in ("path", "role", "domain", "claim_bearing"):
            if key not in entry:
                errors.append(f"entry {i} missing key '{key}'")
        role = entry.get("role")
        if role is not None and role not in DOC_INDEX_ROLES:
            errors.append(f"entry {entry.get('path')!r} unknown role {role!r}")
        domain = entry.get("domain")
        if domain is not None and domain not in DOC_INDEX_DOMAINS:
            errors.append(f"entry {entry.get('path')!r} unknown domain {domain!r}")
        path = entry.get("path")
        if isinstance(path, str) and not (ROOT / path).exists():
            errors.append(f"entry path does not exist: {path}")
    return errors


# --- main -------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate the manifest")
    args = parser.parse_args(argv)

    try:
        if args.write:
            manifest = build_manifest()
            MANIFEST.write_text(_dump(manifest), encoding="utf-8")
            print(
                f"physics-docs-canon: wrote {MANIFEST.relative_to(ROOT)} "
                f"({manifest['totals']['laws']} laws, {manifest['totals']['invariants']} invariants)"
            )
            return 0
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"physics-docs-canon: substrate error: {exc}", file=sys.stderr)
        return 2

    if not MANIFEST.is_file():
        print(
            f"physics-docs-canon: missing {MANIFEST.relative_to(ROOT)} " "(run with --write)",
            file=sys.stderr,
        )
        return 1

    try:
        manifest_text = MANIFEST.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"physics-docs-canon: manifest unreadable: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    try:
        errors.extend(check_manifest(manifest_text))
    except (ValueError, yaml.YAMLError) as exc:
        print(f"physics-docs-canon: substrate error: {exc}", file=sys.stderr)
        return 2
    errors.extend(check_canon_docs())
    errors.extend(check_doc_index())

    if errors:
        print("physics-docs-canon: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    expected = build_manifest()
    print(
        "physics-docs-canon: clean — "
        f"{expected['totals']['laws']} laws + {expected['totals']['invariants']} invariants "
        f"classified across {len(expected['domains'])} domains; canon docs + index verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
