#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed neuroscience claim-boundary gate (runtime surface).

GeoSync's neuro subsystems are **engineering analogs** — a tanh "dopamine"
adapter, a logistic "serotonin" brake, a "GABA" position gate. They are named
after neuroscience for intuition, not because the runtime simulates biology
(see ``.claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml``, which classifies
every mechanism and quarantines DECORATIVE/OVERCLAIM labels).

This gate is the orthogonal complement to ``check_claim_boundary.py`` (which
firewalls *product-category* drift). It firewalls *biological-equivalence*
drift: a future edit that quietly re-sells an engineering analog as a
validated brain model. A forbidden phrase in runtime source either must be
reworded, carry an inline non-claim pragma (``# no-bio-claim`` /
``# engineering-analog``), or have a reasoned entry in
``.github/neuro_claim_boundary_allow.json``.

Mechanism is not a claim — identifiers (``dopamine_rpe``, ``gaba_gate``) never
match the prose patterns below; only assertive sentences ("biologically
validated", "basal ganglia simulation") do.

Run locally before push::

    python scripts/ci/check_neuro_claim_boundary.py

Exit codes::

    0  — no unreviewed biological-equivalence claims in runtime source
    1  — at least one unreviewed forbidden phrase, OR a stale allowlist entry
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH = ROOT / ".github" / "neuro_claim_boundary_allow.json"

# Runtime code surfaces where decorative neuro labels live. Docs/tests/ledger
# are excluded: the ledger enumerates the forbidden terms by design, tests
# assert on them, and archived docs quote them as evidence.
SCAN_GLOBS: tuple[str, ...] = (
    "core/**/*.py",
    "src/**/*.py",
    "geosync/**/*.py",
    "coherence_bridge/**/*.py",
)
EXCLUDE_DIR_PREFIXES: tuple[str, ...] = (
    "tests/",
    "docs/archive/",
)

# Inline escape: a line carrying one of these pragmas declares the non-claim
# explicitly and is exempt (mirrors the repo's detect-secrets pragma idiom).
NONCLAIM_PRAGMAS: tuple[str, ...] = ("# no-bio-claim", "# engineering-analog", "# nonclaim")

# Forbidden biological-equivalence phrases (WP9). Matched on a normalised,
# case-folded, dash-unified line so wrapping/typography cannot smuggle them.
FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"neuroscience[ -]verified", "neuroscience-verified equivalence claim"),
    (r"biologically validated", "biological-validation claim"),
    (r"brain[ -]like proof", "brain-like-proof claim"),
    (r"basal ganglia simulation", "basal-ganglia-simulation claim"),
    (r"active inference validated", "active-inference-validated claim"),
    (r"neuro[ -]derived optimality", "neuro-derived-optimality claim"),
    (r"validated neuroscience", "validated-neuroscience claim"),
    (r"biological equivalence", "biological-equivalence claim"),
)
_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p), why) for p, why in FORBIDDEN_PATTERNS
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
    why: str
    text: str


def _load_allowlist() -> list[AllowEntry]:
    if not ALLOWLIST_PATH.exists():
        return []
    payload = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return [
        AllowEntry(
            file=item["file"], match=_normalise(item["match"]), reason=item.get("reason", "")
        )
        for item in payload.get("allow", [])
    ]


def _iter_surface() -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for glob in SCAN_GLOBS:
        for path in sorted(ROOT.glob(glob)):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if any(rel.startswith(prefix) for prefix in EXCLUDE_DIR_PREFIXES):
                continue
            if path not in seen:
                seen.add(path)
                files.append(path)
    return files


def _scan() -> list[Violation]:
    violations: list[Violation] = []
    for path in _iter_surface():
        rel = path.relative_to(ROOT).as_posix()
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(pragma in raw for pragma in NONCLAIM_PRAGMAS):
                continue
            norm = _normalise(raw)
            for pattern, why in _COMPILED:
                if pattern.search(norm):
                    violations.append(Violation(file=rel, lineno=lineno, why=why, text=norm))
                    break
    return violations


def main() -> int:
    allow = _load_allowlist()
    violations = _scan()

    used_allow: set[AllowEntry] = set()
    unreviewed: list[Violation] = []
    for v in violations:
        matched = next((e for e in allow if e.file == v.file and e.match in v.text), None)
        if matched is None:
            unreviewed.append(v)
        else:
            used_allow.add(matched)

    stale = [e for e in allow if e not in used_allow]

    if unreviewed:
        print("ERROR: unreviewed biological-equivalence claims in runtime source.")
        print("GeoSync neuro mechanisms are engineering analogs, not brain models")
        print("(see .claude/neuro/NEURO_OPERATIONALIZATION_LEDGER.yaml). Reword,")
        print("add a '# no-bio-claim' pragma, or a reasoned allowlist entry:\n")
        for v in unreviewed:
            print(f"  {v.file}:{v.lineno}: [{v.why}] {v.text[:120]}")
        print(f"\n{len(unreviewed)} unreviewed neuro-claim(s).")
        return 1

    if stale:
        print("ERROR: stale neuro-claim-boundary allowlist entries (no longer match).")
        for e in stale:
            print(f"  {e.file}: {e.match[:90]!r}")
        return 1

    print(
        f"NEURO CLAIM BOUNDARY: PASS — {len(_iter_surface())} runtime source files scanned, "
        f"0 unreviewed biological-equivalence claims, {len(used_allow)} reviewed reference(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
