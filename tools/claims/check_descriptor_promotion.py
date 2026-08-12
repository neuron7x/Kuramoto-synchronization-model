#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed descriptor-to-physics promotion firewall.

GeoSync ships many **descriptors** — correlation-graph Ricci curvature,
phase-coherence statistics, market proxies, simplicial-topology features.
A descriptor is a computed quantity over data. It is *not* a physical law,
*not* the physical phase of a system, *not* market consensus, *not* a
predictor, and *not* alpha. The provenance vocabulary in ``docs/CLAIMS.yaml``
(``ANCHORED`` / ``EXTRAPOLATED`` …) and ``FORBIDDEN_CLAIMS.md`` already
firewall *status* wording and *product-category* drift. This gate closes a
third, orthogonal gap: **silent promotion**, where prose quietly asserts that
a descriptor *is* (or *measures*, or *proves*, or *predicts*) the physical /
causal / consensual / tradable thing it merely correlates with.

``scripts/ci/check_claim_boundary.py`` firewalls product-category drift over
the canonical surface; this checker reuses its proven idiom (NFKC + dash +
whitespace normalisation, JSON allowlist with stale-entry detection,
``file:line`` reporting) but targets a different deny-set: **promotion
assertions** that bind a descriptor token to a physical/causal/predictive/
trading target through a promotion verb.

The six forbidden promotions (see ``docs/claims/descriptor_promotion_policy.md``):

    1. descriptor              -> physical law
    2. proxy phase             -> physical phase
    3. correlation-graph Ricci -> L2 microstructure Ricci
    4. coherence descriptor    -> market consensus
    5. topology descriptor     -> predictive validity
    6. feature                 -> alpha

A promotion fires only when a descriptor token and a promotion verb and a
target token co-occur on one normalised line. Honest descriptor discipline —
negations (``is NOT a physical law``, ``does not imply``), proxy-disclosure
(``a proxy for slippage``), and provenance-tiered hedges — is explicitly
*not* a promotion and passes. Reviewed mechanism / quotation references live
in ``.github/descriptor_promotion_allow.json``; a new, unreviewed promotion,
or a stale allowlist entry, fails the build.

Run locally before push::

    python tools/claims/check_descriptor_promotion.py

Exit codes::

    0  — no unreviewed descriptor->physics/prediction/trading promotions
    1  — at least one unreviewed promotion, OR a stale allowlist entry
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = ROOT / ".github" / "descriptor_promotion_allow.json"

# Canonical claim surface: top-level docs + the docs/ tree + the claim-bearing
# indicator code whose docstrings describe outputs to a reader. Identical
# surface philosophy to check_claim_boundary.py so the two gates cover the
# same prose.
SCAN_GLOBS: tuple[str, ...] = ("*.md", "docs/**/*.md")
CODE_SURFACE_FILES: tuple[str, ...] = (
    "core/indicators/kuramoto_ricci_composite.py",
    "core/indicators/market_state_contract.py",
    "core/indicators/hurst.py",
    "core/indicators/entropy.py",
)
# Append-only *records* that legitimately quote promotion phrasing as the very
# thing they warn against (policy, forbidden-claims ledger, audit findings,
# ADRs, archived/immutable reports). Scanning them would flag the warning.
EXCLUDE_DIR_PREFIXES: tuple[str, ...] = (
    "docs/archive/",
    "docs/audit/",
    "docs/adr/",
    "docs/releases/",
    "docs/claims/",  # this firewall's own policy doc enumerates banned phrasing
)
EXCLUDE_FILES: frozenset[str] = frozenset(
    {
        "FORBIDDEN_CLAIMS.md",
        "CLAIMS.md",
        "PRODUCT_CATEGORY.md",
    }
)

# --- Promotion lexicon -------------------------------------------------------
#
# A promotion is the conjunction (descriptor-token, promotion-verb, target).
# Each rule below pre-binds the relevant tokens into a single regex over a
# normalised line so the three pieces must co-occur. The verb sits between the
# descriptor and target with a bounded gap so unrelated sentence fragments do
# not collide.
#
# NEGATION SAFETY: descriptor discipline in this repo is written as honest
# negation ("is NOT a physical law", "does not imply", "is not the physical
# phase") and proxy-disclosure ("a proxy for slippage"). Those must pass. A
# shared negation guard strips any line carrying a negation cue near the verb
# before the deny-rules run.

# Promotion verbs that bind a descriptor to a stronger ontological category.
_PROMO_VERB = r"(?:is|are|equals?|becomes?|measures?|captures?|proves?|establishes?|constitutes?|represents?|reflects?|reveals?|predicts?|forecasts?|implies|encodes?|is the)"

# Negation cues anywhere on the line demote it from promotion to discipline.
# "proxy for" is proxy-DISCLOSURE (honest), not promotion.
_NEGATION = re.compile(
    r"(?:"
    r"\bnot\b|\bnever\b|\bno\b|\bn't\b|\bcannot\b|\bdoes not\b|\bdo not\b|"
    r"\bisn't\b|\baren't\b|\bwithout\b|\bproxy for\b|\bstand[- ]?in for\b|"
    r"\bdescriptor for\b|\bsurrogate for\b|\bnot a claim\b"
    r")"
)


@dataclass(frozen=True)
class PromotionRule:
    """One forbidden descriptor->target promotion."""

    rule_id: str
    why: str
    pattern: re.Pattern[str]


def _rule(rule_id: str, why: str, raw: str) -> PromotionRule:
    return PromotionRule(rule_id=rule_id, why=why, pattern=re.compile(raw))


# Each pattern: <descriptor token> ... <verb> ... <target token>, bounded gap.
# Patterns operate on the NFKC + dash + case-folded + space-collapsed line.
PROMOTION_RULES: tuple[PromotionRule, ...] = (
    # 1. descriptor -> physical law
    _rule(
        "descriptor-to-physical-law",
        "descriptor promoted to a physical law",
        rf"\b(?:descriptor|metric|indicator|statistic|feature)\b.{{0,40}}{_PROMO_VERB}\b.{{0,24}}\b(?:physical law|law of (?:nature|physics|markets)|fundamental law)\b",
    ),
    # 2. proxy phase -> physical phase
    _rule(
        "proxy-phase-to-physical-phase",
        "proxy/estimated phase promoted to physical phase",
        rf"\b(?:proxy phase|estimated phase|phase proxy|phase descriptor|computed phase)\b.{{0,40}}{_PROMO_VERB}\b.{{0,24}}\b(?:physical phase|true phase|real phase|actual phase)\b",
    ),
    # 3. correlation-graph Ricci -> L2 microstructure Ricci
    _rule(
        "correlation-ricci-to-microstructure-ricci",
        "correlation-graph Ricci promoted to L2-microstructure Ricci",
        rf"\b(?:correlation[- ]graph ricci|correlation ricci|graph ricci)\b.{{0,40}}{_PROMO_VERB}\b.{{0,24}}\b(?:l2 microstructure ricci|microstructure ricci|order[- ]book ricci|l2 ricci)\b",
    ),
    # 4. coherence descriptor -> market consensus
    _rule(
        "coherence-to-market-consensus",
        "coherence descriptor promoted to market consensus",
        rf"\b(?:coherence|phase coherence|plv|order parameter)\b.{{0,40}}{_PROMO_VERB}\b.{{0,24}}\b(?:market consensus|collective belief|market agreement|consensus of the market)\b",
    ),
    # 5. topology descriptor -> predictive validity. The promotion verb here is
    #    itself predictive ("predicts"/"forecasts"), so the descriptor binds
    #    directly to the prediction target without a separate copula.
    _rule(
        "topology-to-predictive-validity",
        "topology descriptor promoted to predictive validity",
        r"\b(?:topology|topological feature|simplicial (?:feature|complex)|persistent homology|betti)\b.{0,40}"
        r"(?:"
        r"(?:is|are|has|have|provides?|establishes?|demonstrates?)\b.{0,24}\bpredictive validity\b"
        r"|(?:predicts?|forecasts?)\b.{0,16}\b(?:price|market|return|direction)\b"
        r"|(?:is|are)\b.{0,16}\bout[- ]of[- ]sample (?:edge|alpha|predictive)\b"
        r")",
    ),
    # 6. feature -> alpha
    _rule(
        "feature-to-alpha",
        "feature/descriptor promoted to alpha",
        rf"\b(?:feature|descriptor|signal feature|indicator)\b.{{0,40}}{_PROMO_VERB}\b.{{0,24}}\b(?:alpha|tradable edge|trading edge|excess return|profitable strategy)\b",
    ),
)

_UNICODE_DASHES = dict.fromkeys((0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212), ord("-"))


def _normalise(line: str) -> str:
    """Case-fold, NFKC-normalise, map unicode dashes to ASCII, collapse runs."""
    folded = unicodedata.normalize("NFKC", line).translate(_UNICODE_DASHES).casefold()
    return re.sub(r"\s+", " ", folded).strip()


@dataclass(frozen=True)
class AllowEntry:
    file: str
    match: str
    reason: str


@dataclass(frozen=True)
class Violation:
    file: str
    lineno: int
    rule_id: str
    why: str
    text: str


def _load_allowlist() -> list[AllowEntry]:
    if not ALLOWLIST_PATH.exists():
        return []
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    entries: list[AllowEntry] = []
    for item in payload.get("allow", []):
        entries.append(
            AllowEntry(
                file=item["file"],
                match=_normalise(item["match"]),
                reason=item.get("reason", ""),
            )
        )
    return entries


def _iter_surface() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for glob in SCAN_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in EXCLUDE_FILES:
                continue
            if any(rel.startswith(prefix) for prefix in EXCLUDE_DIR_PREFIXES):
                continue
            if path not in seen:
                seen.add(path)
                files.append(path)
    for rel in CODE_SURFACE_FILES:
        path = ROOT / rel
        if path.is_file() and path not in seen:
            seen.add(path)
            files.append(path)
    return files


def scan_line(norm: str) -> list[tuple[str, str]]:
    """Return ``(rule_id, why)`` for every promotion rule a normalised line trips.

    A line carrying a negation / proxy-disclosure cue is descriptor discipline,
    not promotion, and trips nothing.
    """
    if _NEGATION.search(norm):
        return []
    hits: list[tuple[str, str]] = []
    for rule in PROMOTION_RULES:
        if rule.pattern.search(norm):
            hits.append((rule.rule_id, rule.why))
    return hits


def _scan() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_surface():
        rel = path.relative_to(ROOT).as_posix()
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            norm = _normalise(raw)
            for rule_id, why in scan_line(norm):
                violations.append(
                    Violation(file=rel, lineno=lineno, rule_id=rule_id, why=why, text=norm)
                )
    return violations


def evaluate() -> tuple[list[Violation], list[AllowEntry], int]:
    """Return ``(unreviewed, stale, surface_count)`` for reuse in tests."""
    allow = _load_allowlist()
    violations = _scan()
    used_allow: set[AllowEntry] = set()
    unreviewed: list[Violation] = []
    for v in violations:
        matched = next(
            (e for e in allow if e.file == v.file and e.match in v.text),
            None,
        )
        if matched is None:
            unreviewed.append(v)
        else:
            used_allow.add(matched)
    stale = [e for e in allow if e not in used_allow]
    return unreviewed, stale, len(_iter_surface())


def main() -> int:
    unreviewed, stale, surface_count = evaluate()

    if unreviewed:
        print("ERROR: unreviewed descriptor-to-physics/prediction/trading promotions.")
        print("A descriptor (Ricci on a correlation graph, phase coherence, a market")
        print("proxy, a topology feature) is not a physical law, not the physical phase,")
        print("not market consensus, not predictive validity, and not alpha. Reword to")
        print("the descriptor boundary (see docs/claims/descriptor_promotion_policy.md),")
        print(f"or add a reasoned entry to {ALLOWLIST_PATH.relative_to(ROOT).as_posix()}:\n")
        for v in unreviewed:
            print(f"  {v.file}:{v.lineno}: [{v.rule_id}] {v.text[:120]}")
        print(f"\n{len(unreviewed)} unreviewed promotion(s).")
        return 1

    if stale:
        print("ERROR: stale descriptor-promotion allowlist entries (no longer match).")
        print("Remove them so the allowlist stays an honest ledger:\n")
        for e in stale:
            print(f"  {e.file}: {e.match[:90]!r}")
        return 1

    print(
        f"Descriptor-promotion firewall passed: {surface_count} canonical surfaces "
        f"(docs + claim-bearing code) scanned, no unreviewed promotions."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
