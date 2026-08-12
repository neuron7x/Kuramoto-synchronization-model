#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""EBSVAP WP1 — atomic claim compiler.

Turns a claim certificate into an admissibility decision: the evidence must
ENTAIL the exact wording, under a claim-type-specific evidence contract. Forbidden
strength words (proven/calibrated/safe/independent/optimal/generalizable/
validated) are rejected when their contract is unsatisfied. Compound claims are
rejected if any conjunct is unsupported. Fail-closed: unknown type -> REJECT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

try:  # normal package import (tests, `import src.ebsvap...`)
    from ._text_normalize import normalize_for_matching
except ImportError:  # standalone file load (CI runner uses spec_from_file_location)
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "ebsvap_text_normalize", _Path(__file__).with_name("_text_normalize.py")
    )
    assert _spec is not None and _spec.loader is not None
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    normalize_for_matching = _mod.normalize_for_matching

# Compound claims recurse through evidence["conjuncts"]. Without a bound, a
# deeply nested (adversarial or accidental) conjunct chain overflows the Python
# stack -> uncaught RecursionError (a crash, i.e. fail-OPEN availability hole).
# Bound the depth and REJECT past it, fail-closed. 64 is far beyond any
# legitimate compound claim yet well under the interpreter recursion limit.
MAX_CONJUNCT_DEPTH = 64

# Forbidden strength words matched by morphological STEM, not raw substring, so
# ordinary inflection ("proves"/"proved", "generalises", "validate") cannot evade
# the guard. Word-boundary anchored to avoid false hits inside unrelated words
# ("improve", "unsafe", "provenance"). Fail-closed bias: over-matching a strength
# word only demands more evidence, it never admits an unsupported claim.
FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bprov(e|es|ed|en|ably|able)\b"), "MATHEMATICAL"),
    (re.compile(r"\bcalibrat(e|es|ed|ing|ion)\b"), "PROBABILISTIC"),
    (re.compile(r"\bsafe(ly|ty|r|st)?\b"), "SAFETY"),
    (re.compile(r"\bindependen(t|tly|ce)\b"), "INDEPENDENCE"),
    (re.compile(r"\boptimal(ity|ly)?\b"), "OPTIMALITY"),
    (re.compile(r"\bgenerali[sz](e|es|ed|ing|able|ation|ability)\b"), "GENERALIZATION"),
    (re.compile(r"\bvalidat(e|es|ed|ing|ion)\b"), "VALIDATION"),
]


@dataclass
class Claim:
    claim_id: str
    text: str
    claim_type: str
    evidence: dict = field(default_factory=dict)  # keys: data, calibration, intervention,
    # structural_test, source, independent_source, proof, holdout, unit_tests_only, conjuncts


def _contract(c: Claim) -> tuple[bool, str]:
    e = c.evidence
    t = c.claim_type
    if t == "MATHEMATICAL":
        if not e.get("proof"):
            return False, "MATHEMATICAL requires a proof/theorem, none provided"
    elif t == "EMPIRICAL":
        if not e.get("data"):
            return False, "EMPIRICAL requires observed data, none provided"
    elif t == "PROBABILISTIC":
        if not e.get("calibration"):
            return False, "PROBABILISTIC requires calibration on independent data"
    elif t == "CAUSAL":
        if not e.get("intervention"):
            return False, "CAUSAL requires interventional evidence (not correlation)"
    elif t == "GENERALIZATION":
        if not e.get("structural_test"):
            return False, "GENERALIZATION requires a structural/non-IID test"
        if e.get("data") == "iid_only":
            return False, "GENERALIZATION from IID data only is inadmissible"
    elif t == "SAFETY":
        if e.get("unit_tests_only"):
            return False, "SAFETY not established by unit tests alone"
        if not (e.get("data") or e.get("raw_log")):
            return False, "SAFETY requires an executable evidence path"
    elif t == "OPERATIONAL_AUTHORITY":
        if not e.get("holdout"):
            return False, "OPERATIONAL_AUTHORITY requires a temporal holdout"
    elif t in ("PERFORMANCE", "REPRODUCIBILITY", "SECURITY"):
        if not e.get("data") and not e.get("raw_log"):
            return False, f"{t} requires an executable evidence path"
    else:
        return False, f"unknown claim_type {t!r} (fail-closed)"
    return True, "type contract satisfied"


def _word_check(c: Claim) -> tuple[bool, str]:
    # Normalize BEFORE matching so homoglyph / zero-width / control-char evasions
    # ("prоven" with Cyrillic о, "pro​ven", "pro\x00ven") collapse to the
    # canonical ASCII token the guard is written against. Fail-closed: exposing a
    # hidden strength word only demands more evidence, it never admits.
    low = normalize_for_matching(c.text).lower()
    e = c.evidence
    for pattern, req in FORBIDDEN_PATTERNS:
        if pattern.search(low):
            if req == "INDEPENDENCE":
                if e.get("independent_source") is None or e.get("independent_source") == e.get(
                    "source"
                ):
                    return False, "'independent' but evidence shares the implementation source"
            elif req == "OPTIMALITY":
                if not e.get("proof"):
                    return False, "'optimal' without an optimality proof (myopic != optimal)"
            elif req == "PROBABILISTIC" and not e.get("calibration"):
                return False, "'calibrated' without calibration evidence"
            elif req == "SAFETY" and (
                e.get("unit_tests_only") or not (e.get("data") or e.get("raw_log"))
            ):
                return False, "'safe' without an evidence path beyond unit tests"
            elif req == "VALIDATION" and not (e.get("holdout") or e.get("data")):
                return False, "'validated' without an evidence path"
            elif req == "GENERALIZATION" and not e.get("structural_test"):
                return False, "'generalizable' without a structural/non-IID test"
            elif req == "MATHEMATICAL" and not e.get("proof"):
                return False, "'proven' without a proof"
    return True, "wording within evidence"


def compile_claim(c: Claim, _depth: int = 0) -> dict:
    # Shape guards — malformed certificates must REJECT with a reason, never
    # crash with AttributeError/TypeError (a crash is fail-OPEN: no verdict).
    if not isinstance(c, Claim):
        return {
            "claim_id": None,
            "status": "REJECT",
            "reason": "claim is not a Claim instance (fail-closed)",
        }
    if not isinstance(c.text, str):
        return {
            "claim_id": c.claim_id,
            "status": "REJECT",
            "reason": "claim text must be a string (fail-closed)",
        }
    if not isinstance(c.evidence, dict):
        return {
            "claim_id": c.claim_id,
            "status": "REJECT",
            "reason": "evidence must be a mapping (fail-closed)",
        }

    # compound: every conjunct must independently pass
    conjuncts = c.evidence.get("conjuncts")
    if conjuncts:
        if _depth >= MAX_CONJUNCT_DEPTH:
            return {
                "claim_id": c.claim_id,
                "status": "REJECT",
                "reason": "conjunct nesting exceeds max depth (fail-closed)",
            }
        if not isinstance(conjuncts, (list, tuple)):
            return {
                "claim_id": c.claim_id,
                "status": "REJECT",
                "reason": "conjuncts must be a list of Claim objects (fail-closed)",
            }
        for sub in conjuncts:
            if not isinstance(sub, Claim):
                return {
                    "claim_id": c.claim_id,
                    "status": "REJECT",
                    "reason": "conjunct is not a Claim instance (fail-closed)",
                }
            r = compile_claim(sub, _depth + 1)
            if r["status"] == "REJECT":
                return {
                    "claim_id": c.claim_id,
                    "status": "REJECT",
                    "reason": f"conjunct {sub.claim_id} unsupported: {r['reason']}",
                }
    ok_c, why_c = _contract(c)
    if not ok_c:
        return {"claim_id": c.claim_id, "status": "REJECT", "reason": why_c}
    ok_w, why_w = _word_check(c)
    if not ok_w:
        return {"claim_id": c.claim_id, "status": "REJECT", "reason": why_w}
    return {"claim_id": c.claim_id, "status": "ADMIT", "reason": "evidence entails wording"}
