#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""RES-005 physics-score de-hyping gate.

Fail-closed guard that keeps the GeoSync "physics score" (and its ``88-92``
target band) honest: it is an INTERNAL READINESS RUBRIC over invariant/test/CI
coverage, NOT scientific validation, and ``88-92`` is a self-set readiness
threshold, not a scientific criterion (see ``docs/physics_score_methodology.md``
and ``artifacts/research/physics_score_calibration.json``).

The gate enforces three things, fail-closed:

1. ``--validate-artifacts`` (default): the methodology doc carries the relabel
   markers, and the calibration artifact carries component traceability, a
   weight-sensitivity block, and the ``INTERNAL_READINESS_RUBRIC_NOT_VALIDATION``
   verdict. Missing relabel or missing sensitivity -> RED.

2. ``--scan-file PATH`` / ``--scan-text TEXT``: fail-closed if a surface presents
   the physics score / ``88-92`` band AS SCIENTIFIC VALIDATION -- i.e. a
   physics-score token co-occurring on a line with a claim-firewall *validation*
   word (drawn from ``governance/project_state.yaml`` forbidden_claims, the words
   requiring MEASURED/FACT) with no negation cue. A ``--evidence-class`` may be
   declared; a validation word clears only if the declared class is one the
   firewall permits for it (i.e. MEASURED or FACT). SIMULATION/HYPOTHESIS/none
   never clear a validation word.

Exit codes:  0 clean  |  1 flagged (contradiction / contract unmet)  |  2 error.
All modes print a deterministic JSON report to stdout.

Usage::

    python scripts/ci/check_physics_score.py --validate-artifacts
    python scripts/ci/check_physics_score.py --scan-file VERDICT.md
    python scripts/ci/check_physics_score.py --scan-text "physics score 90 = scientifically validated"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError as exc:  # DS-18: fail cleanly, never raw traceback
    print(json.dumps({"status": "ERROR", "error": f"missing dependency: {exc.name}"}))
    sys.exit(2)

# Confusable/zero-width normalization so ASCII claim patterns cannot be evaded
# by homoglyphs, ZWSP or NUL. Run as a script, scripts/ci is on sys.path[0].
try:
    from _text_normalize import normalize_for_matching
except ImportError:  # pragma: no cover - import path fallback
    import importlib.util as _ilu

    _sp = _ilu.spec_from_file_location(
        "_text_normalize", Path(__file__).resolve().parent / "_text_normalize.py"
    )
    _tn = _ilu.module_from_spec(_sp)
    _sp.loader.exec_module(_tn)
    normalize_for_matching = _tn.normalize_for_matching

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "governance/project_state.yaml"
DEFAULT_METHODOLOGY = ROOT / "docs/physics_score_methodology.md"
DEFAULT_CALIBRATION = ROOT / "artifacts/research/physics_score_calibration.json"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2

# A token that names the physics score / its target band.
PHYSICS_SCORE_TOKEN = re.compile(
    r"physics[\s_\-]?score|physical\s+rank|\bS[_\s]?total\b|88[\s\-–]?92|target[\s_\-]?interval",
    re.IGNORECASE,
)
# Negation cue that turns a validation word into a DISCLAIMER rather than a
# claim. DS-03: the cue only disarms when it DIRECTLY negates the validation
# token -- i.e. it sits immediately before the word (allowing a couple of light
# fillers such as "is"/"scientifically"), NOT merely anywhere on the line. This
# regex is anchored to the END of the text preceding a validation match, so
# "physics score 90 is not validated" clears while "... is validated, not
# overfit" / "... validated for non-linear regimes" / "... validated; no
# caveats" stay FLAGGED (the negation there does not attach to "validated").
# DS-03 (round 2): the disarming window must reject AFFIRMING intensifiers.
# "not merely/only/just/simply/solely validated" is a validation CLAIM, not a
# disclaimer — an intensifier flips the negation back to affirmation, so it must
# NOT disarm. Each filler word is guarded by a negative lookahead; a genuine
# multi-word negation ("has not been fully validated") still disarms because its
# fillers are not intensifiers.
_AFFIRMING_INTENSIFIER = r"(?:only|merely|just|simply|solely|alone|purely)"
NEGATION_BEFORE = re.compile(
    r"\b(?:not|never|no|without|isn'?t|aren'?t|non)\b"
    r"(?:[\s\-]+(?!" + _AFFIRMING_INTENSIFIER + r"\b)\w+)*"
    r"[\s\-]*$",
    re.IGNORECASE,
)
# Relabel markers the methodology doc MUST carry.
RELABEL_MARKERS = (
    re.compile(r"internal\s+readiness\s+rubric", re.IGNORECASE),
    re.compile(r"not\s+scientific\s+validation|not\s+validation", re.IGNORECASE),
    re.compile(r"external\s+criterion", re.IGNORECASE),
    re.compile(r"self-?set\s+readiness\s+threshold", re.IGNORECASE),
)


class GateError(Exception):
    """Fail-closed structural error (exit 2)."""


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:  # pragma: no cover - IO edge
        raise GateError(f"cannot read/parse {path}: {exc}") from exc
    if not isinstance(raw, dict) or "forbidden_claims" not in raw:
        raise GateError(f"{path}: not a valid project-state ontology")
    return raw


# DS-04: the SSOT ships the validation claim as past-tense only
# (``\bvalidated\b``), so a present-tense hype phrasing -- "the physics score
# validates the market model" -- slipped through as GREEN. Broaden the
# *validation* stem to the full set of CLAIM verb inflections
# (validate/validates/validating/validated) while reusing every other
# forbidden-claim pattern verbatim. The bare noun "validation" is deliberately
# NOT included: it is the term the relabel doc must be free to *mention* when
# describing the forbidden pattern (use/mention), so folding it in would break a
# benign positive control without catching a distinct hype claim.
_VALIDATED_STEM = r"\bvalidat(?:e|es|ed|ing)\b"


def _stem_pattern(entry: dict[str, Any]) -> str:
    pattern = entry["pattern"]
    if entry.get("claim") == "validated" or pattern == r"\bvalidated\b":
        return _VALIDATED_STEM
    return pattern


def validation_words(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Forbidden-claim entries that require MEASURED or FACT.

    These are the *validation-tier* words: applying them to the SIMULATION-class
    physics score is exactly the contradiction this gate exists to catch. The
    vocabulary and its ``requires`` bindings are reused verbatim from the SSOT.
    """
    out: list[dict[str, Any]] = []
    for entry in state.get("forbidden_claims", []):
        requires = set(entry.get("requires", []))
        if requires & {"MEASURED", "FACT"}:
            out.append(
                {
                    "claim": entry["claim"],
                    "regex": re.compile(_stem_pattern(entry), re.IGNORECASE),
                    "requires": requires,
                }
            )
    if not out:
        raise GateError("no validation-tier forbidden claims found in SSOT")
    return out


def scan_text(
    text: str,
    words: list[dict[str, Any]],
    declared_class: str | None,
    source: str,
) -> dict[str, Any]:
    """Flag lines that present a physics-score token AS validation."""
    violations: list[dict[str, Any]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        # Fold homoglyphs / strip zero-width+control chars before matching so an
        # evasive surface cannot dodge the ASCII patterns (parallels DS-02).
        line = normalize_for_matching(raw_line)
        if not PHYSICS_SCORE_TOKEN.search(line):
            continue
        for w in words:
            match = w["regex"].search(line)
            if match is None:
                continue
            # DS-03: a negation disarms this word ONLY when it directly precedes
            # the validation token (a genuine "... is not validated"), not when a
            # negation word merely co-occurs elsewhere on the line.
            if NEGATION_BEFORE.search(line[: match.start()]):
                continue  # a disclaimer, not a claim
            # declared class clears the word only if the firewall permits it
            if declared_class and declared_class in w["requires"]:
                continue
            violations.append(
                {
                    "source": source,
                    "line": lineno,
                    "claim_word": w["claim"],
                    "text": raw_line.strip()[:200],
                }
            )
    return {
        "mode": "scan",
        "source": source,
        "declared_evidence_class": declared_class,
        "status": "FLAGGED" if violations else "PASS",
        "violations": violations,
    }


def verify_methodology(path: Path) -> list[str]:
    if not path.exists():
        return [f"methodology doc missing: {path}"]
    body = path.read_text(encoding="utf-8", errors="replace")
    missing = [m.pattern for m in RELABEL_MARKERS if not m.search(body)]
    return [f"methodology missing relabel marker: {p}" for p in missing]


def verify_calibration(path: Path) -> list[str]:
    problems: list[str] = []
    if not path.exists():
        return [f"calibration artifact missing: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"calibration artifact is not valid JSON: {exc}"]

    comps = data.get("components")
    if not isinstance(comps, list) or not comps:
        problems.append("calibration.components missing or empty (no traceability)")
    else:
        for c in comps:
            for field in ("id", "weight", "score", "measurement_fn", "kind"):
                if field not in c:
                    problems.append(f"component {c.get('id', '?')} missing field {field!r}")

    sens = data.get("weight_sensitivity")
    if not isinstance(sens, dict) or not sens:
        problems.append("calibration.weight_sensitivity missing (sensitivity not reported)")
    else:
        required_numeric = (
            "equal_weights_score",
            "monte_carlo_stdev",
            "fraction_of_random_weightings_landing_in_target_band_88_92",
        )
        for field in required_numeric:
            if not isinstance(sens.get(field), (int, float)):
                problems.append(f"weight_sensitivity.{field} missing/non-numeric")

    verdict = data.get("verdict")
    if verdict != "INTERNAL_READINESS_RUBRIC_NOT_VALIDATION":
        problems.append(
            f"calibration.verdict is {verdict!r}; expected "
            "'INTERNAL_READINESS_RUBRIC_NOT_VALIDATION'"
        )
    if "external_criterion" not in data:
        problems.append("calibration.external_criterion key absent (must state the gap)")
    return problems


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def validate_artifacts(methodology: Path, calibration: Path) -> dict[str, Any]:
    problems = verify_methodology(methodology) + verify_calibration(calibration)
    return {
        "mode": "validate-artifacts",
        "methodology": _rel(methodology),
        "calibration": _rel(calibration),
        "status": "FLAGGED" if problems else "PASS",
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RES-005 physics-score de-hyping gate.")
    parser.add_argument("--validate-artifacts", action="store_true")
    parser.add_argument("--scan-file", type=Path, default=None)
    parser.add_argument("--scan-text", type=str, default=None)
    parser.add_argument("--evidence-class", type=str, default=None)
    parser.add_argument("--methodology", type=Path, default=DEFAULT_METHODOLOGY)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    args = parser.parse_args(argv)

    try:
        state = load_state()
        vocab = {c["name"] for c in state.get("evidence_classes", [])}
        if args.evidence_class and args.evidence_class not in vocab:
            raise GateError(
                f"--evidence-class {args.evidence_class!r} not in ontology vocabulary {sorted(vocab)}"
            )
        words = validation_words(state)

        if args.scan_text is not None:
            report = scan_text(args.scan_text, words, args.evidence_class, "<text>")
        elif args.scan_file is not None:
            path = args.scan_file if args.scan_file.is_absolute() else ROOT / args.scan_file
            if not path.exists():
                raise GateError(f"--scan-file not found: {path}")
            report = scan_text(
                path.read_text(encoding="utf-8", errors="replace"),
                words,
                args.evidence_class,
                str(args.scan_file),
            )
        else:
            # default mode
            report = validate_artifacts(args.methodology, args.calibration)
    except GateError as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, indent=2))
        return EXIT_ERROR

    print(json.dumps(report, indent=2, sort_keys=True))
    return EXIT_FLAGGED if report["status"] == "FLAGGED" else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
