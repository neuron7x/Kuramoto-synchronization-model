#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Release-evidence-bundle gate (task REL-011).

A release is only "ready" when a single, schema-validated bundle can point, for
every mandatory evidence category, at a real receipt whose recorded sha256
matches the file on disk. This gate assembles / verifies that bundle. It NEVER
fabricates a green release: several mandatory receipts (coverage/TST-003,
mutation/TST-010, sbom, wheel/PKG-001, the canonical full-suite/TST-001 run) do
not exist yet, so the honest release-readiness verdict is NOT_READY and the gate
exits RED — the same "not ready" signal a governance RED gives, not a defect.

Design guarantees:

  * SINGLE SOURCE. ``build_bundle(root)`` deterministically constructs the whole
    bundle from on-disk artifacts + the REL-005 provenance manifest. The
    committed ``release_evidence.json`` is exactly ``canonical_json(build_bundle())``.
  * DETERMINISM. No timestamps, no live ``git`` calls (commit/tree/tag are read
    from the provenance manifest), keys sorted, fixed indentation -> byte-for-byte
    identical output on rebuild.
  * TAMPER-EVIDENCE. Every PRESENT artifact's recorded digest is recomputed from
    disk; any mismatch is RED. A tampered committed bundle (bytes != fresh regen)
    is RED.
  * FAIL-CLOSED READINESS. Any mandatory category not fully PRESENT -> NOT_READY -> RED.

CLI::
    check_release_evidence.py            # verify committed bundle (default)
    check_release_evidence.py --emit     # (re)generate bundle + SHA256SUMS

Exit codes::
    0  bundle schema-valid, all present digests match, regen deterministic, READY
    1  a check failed (digest mismatch / non-deterministic regen / NOT_READY)
    2  structural error (missing schema / bundle / provenance, unparseable)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "release_evidence.schema.json"
BUNDLE_DIR = ROOT / "artifacts" / "releases" / "1.1.0"
BUNDLE_PATH = BUNDLE_DIR / "release_evidence.json"
SHA256SUMS_PATH = BUNDLE_DIR / "SHA256SUMS"
PROVENANCE_PATH = ROOT / "manifests" / "research" / "release_provenance.v2.json"

RELEASE_VERSION = "1.1.0"

# --------------------------------------------------------------------------- #
# Receipt-content contract constants (referenced by _CATEGORY_SPEC below and    #
# by the _evaluate_content scorer further down). See the block above            #
# _evaluate_content for the full rationale.                                     #
# --------------------------------------------------------------------------- #
# Release coverage floor: the canonical RELEASE coverage authority is
# configs/quality/release_90.coveragerc (release gate 90; the 98 in pyproject is
# the ASPIRATIONAL gate). A coverage receipt below 90% is NOT release-satisfied.
COVERAGE_RELEASE_FLOOR_PCT = 90.0
# Mutation-kill floor: docs/MUTATION_KILL_BASELINE.json holds per-module,
# monotone-up floors (no aggregate release-level score is frozen). In the absence
# of a single repo-wide release mutation score we apply a documented conservative
# aggregate floor; a receipt below it is NOT release-satisfied.
MUTATION_RELEASE_FLOOR_PCT = 80.0

# Verdict/status tokens that count as PASSING (case-insensitive). INSUFFICIENT_
# EVIDENCE / FAIL / NOT_READY / ERROR etc. are deliberately absent -> not passing.
_PASSING_VERDICTS = {
    "PASS",
    "PASSED",
    "READY",
    "OK",
    "TRUE",
    "SUCCESS",
    "GREEN",
    "MATCH",
    "MATCHED",
}

_COVERAGE_METRIC_FIELDS = (
    "line_rate",
    "covered_percent",
    "coverage_percent",
    "percent_covered",
    "line_coverage",
    "percent",
    "coverage",
)
_MUTATION_METRIC_FIELDS = (
    "mutation_score",
    "mutation_kill_rate",
    "kill_rate",
    "killed_ratio",
    "score",
)

# --------------------------------------------------------------------------- #
# Category specification — the SINGLE declarative source for the bundle.        #
# Each artifact spec: (path, task, verdict_key). ``verdict_key`` (or None) is a #
# dotted key read live from the artifact's JSON to surface its recorded verdict.#
# MISSING mandatory receipts point at the canonical path the receipt WOULD take.#
# --------------------------------------------------------------------------- #
_CATEGORY_SPEC: list[dict[str, Any]] = [
    {
        "name": "version",
        "mandatory": True,
        "description": "Version SSOT (VERSION + CITATION.cff), both pinned to 1.1.0.",
        "artifacts": [
            {"path": "VERSION", "task": None, "verdict_key": None},
            {"path": "CITATION.cff", "task": None, "verdict_key": None},
        ],
    },
    {
        "name": "commit_tree_tag",
        "mandatory": True,
        "description": "Canonical release commit/tree/tag pinned by the REL-005 signed-tag provenance manifest.",
        "artifacts": [
            {
                "path": "manifests/research/release_provenance.v2.json",
                "task": "REL-005",
                "verdict_key": "status",
            },
        ],
    },
    {
        "name": "manifests",
        "mandatory": True,
        "description": "Root content manifest and its verification report.",
        "artifacts": [
            {"path": "MANIFEST.sha256", "task": None, "verdict_key": None},
            {
                "path": "artifacts/release/root_manifest_report.json",
                "task": None,
                "verdict_key": None,
            },
        ],
    },
    {
        "name": "sbom",
        "mandatory": True,
        "description": "Software bill of materials for the release artifact. Receipt not produced yet.",
        "artifacts": [
            {
                "path": "artifacts/release/sbom.spdx.json",
                "task": "SBOM",
                "verdict_key": None,
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "require_any_key": [
                        "spdxVersion",
                        "SPDXID",
                        "packages",
                        "bomFormat",
                        "components",
                    ],
                },
            },
        ],
    },
    {
        "name": "tests",
        "mandatory": True,
        "description": "Canonical full-suite test run receipt (TST-001). Not produced yet.",
        "artifacts": [
            {
                "path": "artifacts/release/full_test_suite_report.json",
                "task": "TST-001",
                "verdict_key": None,
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "passing",
                },
            },
        ],
    },
    {
        "name": "coverage",
        "mandatory": True,
        "description": "Release coverage receipt (TST-003). Not produced yet.",
        "artifacts": [
            {
                "path": "artifacts/release/coverage_report.json",
                "task": "TST-003",
                "verdict_key": None,
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "passing_if_present",
                    "floor": {
                        "fields": _COVERAGE_METRIC_FIELDS,
                        "min": COVERAGE_RELEASE_FLOOR_PCT,
                    },
                },
            },
        ],
    },
    {
        "name": "mutation",
        "mandatory": True,
        "description": "Release mutation-kill receipt (TST-010). Not produced yet.",
        "artifacts": [
            {
                "path": "artifacts/release/mutation_report.json",
                "task": "TST-010",
                "verdict_key": None,
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "passing_if_present",
                    "floor": {
                        "fields": _MUTATION_METRIC_FIELDS,
                        "min": MUTATION_RELEASE_FLOOR_PCT,
                    },
                },
            },
        ],
    },
    {
        "name": "security_scan",
        "mandatory": True,
        "description": "Hermetic image digest + trivy vulnerability scan (ENV-005).",
        "artifacts": [
            {
                "path": "artifacts/env/image_scan_report.json",
                "task": "ENV-005",
                "verdict_key": "verdict",
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "passing",
                },
            },
            {"path": "artifacts/env/image_digest.json", "task": "ENV-005", "verdict_key": None},
        ],
    },
    {
        "name": "wheel",
        "mandatory": True,
        "description": "Built wheel manifest / packaging receipt (PKG-001). Not produced yet.",
        "artifacts": [
            {
                "path": "artifacts/release/wheel_manifest.json",
                "task": "PKG-001",
                "verdict_key": None,
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "require_any_key": [
                        "wheel",
                        "filename",
                        "artifacts",
                        "files",
                        "name",
                        "dist",
                    ],
                },
            },
        ],
    },
    {
        "name": "docs",
        "mandatory": False,
        "description": "Human-facing release evidence documentation.",
        "artifacts": [
            {"path": "docs/RELEASE_EVIDENCE_BUNDLE.md", "task": "REL-011", "verdict_key": None},
        ],
    },
    {
        "name": "research_verdicts",
        "mandatory": True,
        "description": "Preregistered research verdicts shipped with the release (all INSUFFICIENT_EVIDENCE — honest).",
        "artifacts": [
            {
                "path": "benchmarks/flagship_baselines/comparison_report.json",
                "task": "FLAGSHIP-RQ-001",
                "verdict_key": "verdict",
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "present_string",
                },
            },
            {
                "path": "artifacts/research/power_uq_report.json",
                "task": None,
                "verdict_key": "verdict",
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "verdict",
                    "verdict_mode": "present_string",
                },
            },
            {
                "path": "artifacts/research/selection_bias_report.json",
                "task": None,
                "verdict_key": "final_verdict",
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "final_verdict",
                    "verdict_mode": "present_string",
                },
            },
        ],
    },
    {
        "name": "cleanroom_reproducible_build",
        "mandatory": True,
        "description": "Cleanroom byte-identical rebuild (REL-010) + pinned Python 3.12 build env.",
        "artifacts": [
            {
                "path": "artifacts/release/reproducible_build_report.json",
                "task": "REL-010",
                "verdict_key": "match",
                "contract": {
                    "require_json": True,
                    "require_object": True,
                    "verdict_field": "match",
                    "verdict_mode": "bool_true",
                },
            },
            {"path": "artifacts/env/python312.json", "task": "ENV", "verdict_key": None},
        ],
    },
    {
        "name": "approvals",
        "mandatory": True,
        "description": "Governance remediation ledger (release sign-off is contingent on all mandatory receipts).",
        "artifacts": [
            {
                "path": "governance/remediation_ledger.v1.json",
                "task": None,
                "verdict_key": None,
            },
        ],
    },
]


# --------------------------------------------------------------------------- #
# Primitives                                                                    #
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """Deterministic serialization: sorted keys, fixed indent, trailing newline."""
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _dig(obj: Any, dotted: str) -> Any:
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _read_verdict(path: Path, verdict_key: str | None) -> str | None:
    if verdict_key is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    val = _dig(data, verdict_key)
    if val is None:
        return None
    return str(val)


# --------------------------------------------------------------------------- #
# Receipt-content contract (closes the F1/F1b content-blind fail-open).         #
#                                                                               #
# Existence of a file is NOT proof of a satisfied receipt. Each gated receipt   #
# must additionally parse as JSON, carry the minimal expected shape, record a   #
# PASSING verdict/status where one applies, and clear any numeric floor. A      #
# present-but-failing receipt is scored NOT satisfied so its mandatory category #
# reports UNSATISFIED/INVALID (not PRESENT) -> release stays NOT_READY.         #
#                                                                               #
# Artifact status vocabulary:                                                   #
#   PRESENT     file on disk AND its content contract is satisfied.             #
#   MISSING     no file on disk.                                                #
#   INVALID     file on disk but empty / not parseable JSON / wrong top-type    #
#               (structurally unusable — cannot even be read as a receipt).     #
#   UNSATISFIED file on disk and parseable, but the receipt fails its contract  #
#               (missing shape key / FAIL verdict / match:false / below floor). #
# (Contract constants/tuples are defined above _CATEGORY_SPEC since the spec    #
#  literal references them at module-load time.)                                #
# --------------------------------------------------------------------------- #
def _is_passing(value: Any) -> bool:
    """A recorded verdict/status is passing iff bool-True or a PASSING token."""
    if isinstance(value, bool):
        return value
    return str(value).strip().upper() in _PASSING_VERDICTS


def _as_percent(value: Any) -> float | None:
    """Normalize a coverage/mutation metric to a 0..100 percentage.

    A value in (0, 1] is treated as a fraction (0.95 -> 95.0); a value > 1 is
    treated as an already-expressed percentage (95 -> 95.0). Non-numeric or
    negative -> None (not a usable metric).
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return None
    return f * 100.0 if f <= 1.0 else f


def _evaluate_content(fpath: Path, contract: dict[str, Any] | None) -> tuple[str, str | None]:
    """Score a present receipt against its content contract.

    Returns (status, reason). ``status`` is one of PRESENT / INVALID /
    UNSATISFIED. ``reason`` is a short human string when not satisfied.
    Caller guarantees ``fpath`` exists on disk.
    """
    try:
        raw = fpath.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - unreadable present file
        return "INVALID", f"unreadable: {exc}"
    if not raw.strip():
        return "INVALID", "empty file"
    if contract is None:
        # No structured contract: a non-empty artifact is accepted (its bytes are
        # still digest-bound + determinism-anchored elsewhere).
        return "PRESENT", None

    if contract.get("require_json", True):
        try:
            data: Any = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return "INVALID", "not valid JSON"
    else:
        return "PRESENT", None

    if contract.get("require_object") and not isinstance(data, dict):
        return "INVALID", "JSON top-level is not an object"

    req_any = contract.get("require_any_key")
    if req_any:
        if not isinstance(data, dict) or not any(k in data for k in req_any):
            return "UNSATISFIED", f"missing any of required keys {list(req_any)}"

    vfield = contract.get("verdict_field")
    vmode = contract.get("verdict_mode")
    if vfield and vmode:
        val = _dig(data, vfield) if isinstance(data, dict) else None
        if vmode == "passing":
            if val is None:
                return "UNSATISFIED", f"verdict field '{vfield}' absent"
            if not _is_passing(val):
                return "UNSATISFIED", f"verdict '{val}' not passing"
        elif vmode == "bool_true":
            if val is not True:
                return "UNSATISFIED", f"'{vfield}'={val!r} is not true"
        elif vmode == "present_string":
            if not isinstance(val, str) or not val.strip():
                return "UNSATISFIED", f"verdict field '{vfield}' absent or not a string"
        elif vmode == "passing_if_present":
            if val is not None and not _is_passing(val):
                return "UNSATISFIED", f"verdict '{val}' not passing"

    floor = contract.get("floor")
    if floor:
        fields = floor["fields"]
        min_pct = floor["min"]
        metric: float | None = None
        for fld in fields:
            v = _dig(data, fld) if isinstance(data, dict) else None
            if v is not None:
                metric = _as_percent(v)
                break
        if metric is None:
            return "UNSATISFIED", f"no numeric metric among {list(fields)}"
        if metric < min_pct:
            return "UNSATISFIED", f"metric {metric:.2f}% < floor {min_pct:.2f}%"

    return "PRESENT", None


# --------------------------------------------------------------------------- #
# Bundle construction (single source of truth)                                  #
# --------------------------------------------------------------------------- #
def _source_ref(root: Path) -> dict[str, str]:
    prov_path = root / "manifests" / "research" / "release_provenance.v2.json"
    if not prov_path.is_file():
        raise FileNotFoundError(f"provenance manifest missing: {prov_path}")
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    ref = prov.get("release_ref", {})
    commit = ref.get("canonical_commit")
    tree = ref.get("tree")
    tag = ref.get("tag_name")
    if not (commit and tree and tag):
        raise ValueError("provenance manifest missing canonical_commit/tree/tag_name")
    return {
        "commit": str(commit),
        "tree": str(tree),
        "tag": str(tag),
        "provenance_ref": "manifests/research/release_provenance.v2.json",
    }


def build_bundle(root: Path = ROOT) -> dict[str, Any]:
    """Deterministically assemble the release evidence bundle from disk."""
    categories: dict[str, Any] = {}
    for spec in _CATEGORY_SPEC:
        arts: list[dict[str, Any]] = []
        for aspec in spec["artifacts"]:
            rel = aspec["path"]
            fpath = root / rel
            if not fpath.is_file():
                status, reason, sha = "MISSING", None, None
            else:
                # File on disk -> record its digest (tamper-evidence still binds
                # failing receipts) AND score its content contract. A present but
                # empty/garbage/FAIL/below-floor receipt is NOT satisfied.
                sha = sha256_file(fpath)
                status, reason = _evaluate_content(fpath, aspec.get("contract"))
            item: dict[str, Any] = {
                "path": rel,
                "sha256": sha,
                "status": status,
            }
            if aspec.get("task"):
                item["task"] = aspec["task"]
            verdict = _read_verdict(fpath, aspec.get("verdict_key"))
            if verdict is not None:
                item["verdict"] = verdict
            if reason is not None:
                item["reason"] = reason
            arts.append(item)
        statuses = {a["status"] for a in arts}
        if statuses == {"PRESENT"}:
            cat_status = "PRESENT"
        elif statuses == {"MISSING"}:
            cat_status = "MISSING"
        elif statuses & {"INVALID", "UNSATISFIED"}:
            # Any artifact present-but-failing its content contract -> the whole
            # category is UNSATISFIED (a receipt exists but does not attest).
            cat_status = "UNSATISFIED"
        else:
            # Only PRESENT + MISSING mix left -> genuinely partial coverage.
            cat_status = "PARTIAL"
        categories[spec["name"]] = {
            "mandatory": spec["mandatory"],
            "status": cat_status,
            "description": spec["description"],
            "artifacts": arts,
        }

    mandatory = sorted(n for n, c in categories.items() if c["mandatory"])
    present_mandatory = sorted(n for n in mandatory if categories[n]["status"] == "PRESENT")
    missing_mandatory = sorted(n for n in mandatory if categories[n]["status"] != "PRESENT")
    verdict = "READY" if not missing_mandatory else "NOT_READY"

    return {
        "bundle_version": "release_evidence.v1",
        "release_version": RELEASE_VERSION,
        "source_ref": _source_ref(root),
        "categories": categories,
        "release_readiness": {
            "verdict": verdict,
            "mandatory_categories": mandatory,
            "present_mandatory": present_mandatory,
            "missing_mandatory": missing_mandatory,
        },
    }


def referenced_present_paths(bundle: dict[str, Any]) -> list[str]:
    """Sorted, de-duplicated repo-relative paths of every on-disk referenced artifact.

    On-disk == sha256 recorded (not null); this includes present-but-UNSATISFIED
    receipts so SHA256SUMS covers (and tamper-binds) every real file the bundle
    references, not only the satisfied ones.
    """
    paths: set[str] = set()
    for cat in bundle["categories"].values():
        for art in cat["artifacts"]:
            if art.get("sha256") is not None:
                paths.add(art["path"])
    return sorted(paths)


def build_sha256sums(bundle: dict[str, Any], root: Path = ROOT) -> str:
    """`<sha256>  <path>` lines over present referenced artifacts, sorted by path."""
    lines = []
    for rel in referenced_present_paths(bundle):
        lines.append(f"{sha256_file(root / rel)}  {rel}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Checks (each returns a list of human-readable problems; empty == OK)          #
# --------------------------------------------------------------------------- #
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_schema(bundle: dict[str, Any], schema: dict[str, Any] | None = None) -> list[str]:
    schema = schema or load_schema()
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"schema: {'/'.join(str(p) for p in e.path)}: {e.message}"
        for e in sorted(validator.iter_errors(bundle), key=lambda e: list(e.path))
    ]


def check_digests(bundle: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Recompute every PRESENT artifact's sha256; RED on mismatch or vanished file."""
    problems: list[str] = []
    for cname, cat in bundle["categories"].items():
        for art in cat["artifacts"]:
            # Digest-bind every artifact recorded as on-disk (sha256 != null),
            # including present-but-UNSATISFIED/INVALID receipts — tamper-evidence
            # must not be weakened just because a receipt failed its content gate.
            if art.get("sha256") is None:
                continue
            fpath = root / art["path"]
            if not fpath.is_file():
                problems.append(f"digest[{cname}]: recorded on-disk but file absent: {art['path']}")
                continue
            actual = sha256_file(fpath)
            if actual != art["sha256"]:
                problems.append(
                    f"digest[{cname}]: {art['path']} recorded {art['sha256']} != disk {actual}"
                )
    return problems


def check_deterministic(root: Path = ROOT, bundle_path: Path = BUNDLE_PATH) -> list[str]:
    """Regen must be byte-stable and match the committed bundle exactly."""
    problems: list[str] = []
    first = canonical_json(build_bundle(root))
    second = canonical_json(build_bundle(root))
    if first != second:
        problems.append("determinism: two rebuilds differ (non-deterministic regen)")
    if bundle_path.is_file():
        committed = bundle_path.read_text(encoding="utf-8")
        if committed != first:
            problems.append(
                "determinism: committed release_evidence.json != fresh regen "
                "(stale or tampered bundle)"
            )
    else:
        problems.append(f"determinism: committed bundle missing: {bundle_path}")
    return problems


def check_sha256sums(
    bundle: dict[str, Any], root: Path = ROOT, sums_path: Path = SHA256SUMS_PATH
) -> list[str]:
    if not sums_path.is_file():
        return [f"SHA256SUMS: missing: {sums_path}"]
    expected = build_sha256sums(bundle, root)
    actual = sums_path.read_text(encoding="utf-8")
    if actual != expected:
        return ["SHA256SUMS: committed content != fresh regen (stale or tampered)"]
    return []


def release_readiness(bundle: dict[str, Any]) -> tuple[str, list[str]]:
    rr = bundle["release_readiness"]
    return rr["verdict"], list(rr["missing_mandatory"])


# --------------------------------------------------------------------------- #
# Emit / verify                                                                 #
# --------------------------------------------------------------------------- #
def emit(root: Path = ROOT) -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    bundle = build_bundle(root)
    errs = validate_schema(bundle)
    if errs:
        raise SystemExit("refusing to emit schema-invalid bundle:\n" + "\n".join(errs))
    BUNDLE_PATH.write_text(canonical_json(bundle), encoding="utf-8")
    SHA256SUMS_PATH.write_text(build_sha256sums(bundle, root), encoding="utf-8")


def verify(root: Path = ROOT) -> int:
    if not SCHEMA_PATH.is_file():
        print(f"FATAL: schema missing: {SCHEMA_PATH}", file=sys.stderr)
        return 2
    if not BUNDLE_PATH.is_file():
        print(f"FATAL: bundle missing: {BUNDLE_PATH}", file=sys.stderr)
        return 2
    if not PROVENANCE_PATH.is_file():
        print(f"FATAL: provenance missing: {PROVENANCE_PATH}", file=sys.stderr)
        return 2

    # L1: unparseable committed bundle -> clean exit 2, no traceback.
    try:
        committed = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"FATAL: committed bundle is not parseable JSON: {exc}", file=sys.stderr)
        return 2
    # L1: non-dict payload (e.g. [1,2,3]) is a structural error -> exit 2.
    if not isinstance(committed, dict):
        print(
            "FATAL: committed bundle is not a JSON object (structural error)",
            file=sys.stderr,
        )
        return 2

    # L1: any structural failure while assembling/reading the reference bundle
    # (malformed/incomplete provenance in _source_ref, a committed bundle missing
    # required structure) -> clean exit 2 with a message, never an uncaught trace.
    try:
        problems: list[str] = []
        problems += validate_schema(committed)
        problems += check_digests(committed, root)
        problems += check_deterministic(root)
        problems += check_sha256sums(committed, root)
        verdict, missing = release_readiness(committed)
    except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
        print(f"FATAL: structural error while verifying bundle: {exc}", file=sys.stderr)
        return 2

    print(f"release_version : {committed['release_version']}")
    print(
        f"source_ref      : {committed['source_ref']['tag']} @ {committed['source_ref']['commit'][:12]}"
    )
    print("categories:")
    for name, cat in committed["categories"].items():
        flag = "MANDATORY" if cat["mandatory"] else "optional "
        print(f"  [{cat['status']:7}] {flag} {name}")
    print(f"release_readiness: {verdict}")
    if missing:
        print(f"  missing mandatory receipts: {', '.join(missing)}")

    integrity_red = bool(problems)
    if integrity_red:
        print("\nINTEGRITY PROBLEMS:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)

    if integrity_red:
        print("\nGATE: RED (bundle integrity failure)", file=sys.stderr)
        return 1
    if verdict != "READY":
        print(
            "\nGATE: RED (release NOT_READY — mandatory receipts missing). "
            "This is the correct honest signal, not a defect.",
            file=sys.stderr,
        )
        return 1
    print("\nGATE: GREEN (release evidence bundle complete & verified)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Release evidence bundle gate (REL-011).")
    ap.add_argument("--emit", action="store_true", help="(re)generate the bundle + SHA256SUMS")
    args = ap.parse_args(argv)
    if args.emit:
        emit()
        print(f"emitted {BUNDLE_PATH}")
        print(f"emitted {SHA256SUMS_PATH}")
        return 0
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
