#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local MFN surface checker."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

OK = "OK"
WARN = "WARN"
RED = "RED"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Row:
    name: str
    status: str
    detail: str
    path: str


def read_text(root: Path, rel_path: str) -> str | None:
    try:
        return (root / rel_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def has_all(text: str, values: Iterable[str]) -> bool:
    return all(value in text for value in values)


def makefile_cov(root: Path) -> Row:
    rel = "Makefile"
    text = read_text(root, rel)
    if text is None:
        return Row("makefile_cov", UNKNOWN, "missing file", rel)
    if not has_all(text, ["test-coverage:", "test-all:", "test-ci-full:"]):
        return Row("makefile_cov", UNKNOWN, "shortcut targets incomplete", rel)
    if "--cov=geosync" not in text:
        return Row(
            "makefile_cov",
            WARN,
            "legacy shortcut coverage omits geosync; run tools/patch_makefile_geosync_coverage.py",
            rel,
        )
    return Row("makefile_cov", OK, "geosync present in coverage surface", rel)


def release_cov(root: Path) -> Row:
    rel = "configs/quality/release_90.coveragerc"
    text = read_text(root, rel)
    if text is None:
        return Row("release_cov", UNKNOWN, "missing file", rel)
    return Row(
        "release_cov", OK if "geosync" in text else RED, "release coverage config checked", rel
    )


def workflow_import_path(root: Path) -> Row:
    rel = ".github/workflows/mfn-release-gate.yml"
    text = read_text(root, rel)
    if text is None:
        return Row("workflow_import_path", UNKNOWN, "missing file", rel)
    hidden_path_token = "PYTHON" + "PATH=."
    if hidden_path_token in text:
        return Row("workflow_import_path", RED, "workflow uses path override", rel)
    if "python -m pip install -e ." not in text:
        return Row(
            "workflow_import_path", RED, "workflow does not install package before tests", rel
        )
    return Row("workflow_import_path", OK, "workflow installs package before tests", rel)


def pipeline_markers(root: Path) -> Row:
    rel = "geosync/mfn/pipeline.py"
    text = read_text(root, rel)
    if text is None:
        return Row("pipeline_markers", UNKNOWN, "missing file", rel)
    markers = [
        "MANIFEST_SCHEMA_VERSION",
        "_finite_float",
        "validate_bundle",
        "_parse_sha256_manifest",
        "_is_sha256_hex",
    ]
    missing = [marker for marker in markers if marker not in text]
    if missing:
        return Row("pipeline_markers", RED, "missing: " + ", ".join(missing), rel)
    return Row("pipeline_markers", OK, "pipeline markers present", rel)


def cli_markers(root: Path) -> Row:
    rel = "geosync/mfn/cli.py"
    text = read_text(root, rel)
    if text is None:
        return Row("cli_markers", UNKNOWN, "missing file", rel)
    markers = [
        "_dispatch",
        "FileNotFoundError",
        "ValueError",
        "KeyError",
        "TypeError",
        'prog="mfn"',
        "mfn-validate:",
    ]
    missing = [marker for marker in markers if marker not in text]
    if missing:
        return Row("cli_markers", RED, "missing: " + ", ".join(missing), rel)
    return Row("cli_markers", OK, "cli markers present", rel)


def contract_markers(root: Path) -> Row:
    rel = "geosync/mfn/contract.py"
    text = read_text(root, rel)
    if text is None:
        return Row("contract_markers", UNKNOWN, "missing file", rel)
    markers = ["__post_init__", "schema_version", "seed", "input_window_sec", "claim_tier"]
    missing = [marker for marker in markers if marker not in text]
    if missing:
        return Row("contract_markers", RED, "missing: " + ", ".join(missing), rel)
    return Row("contract_markers", OK, "contract markers present", rel)


def roadmap_contract(root: Path) -> Row:
    rel = "docs/MFN_VERIFICATION_ROADMAP.json"
    text = read_text(root, rel)
    if text is None:
        return Row("roadmap_contract", UNKNOWN, "missing file", rel)
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return Row("roadmap_contract", RED, f"invalid JSON: {exc.msg}", rel)
    if not isinstance(document, dict):
        return Row("roadmap_contract", RED, "roadmap must be a JSON object", rel)
    if document.get("contract_type") != "repository_repair_contract":
        return Row("roadmap_contract", RED, "unexpected contract_type", rel)
    evidence = document.get("evidence_status")
    verdict = document.get("final_verdict")
    if not isinstance(evidence, dict) or not isinstance(verdict, dict):
        return Row("roadmap_contract", RED, "missing evidence_status or final_verdict object", rel)
    if evidence.get("status") != "CANDIDATE_NOT_VALIDATED":
        return Row("roadmap_contract", RED, "roadmap must remain candidate without evidence", rel)
    if verdict.get("status") != "CANDIDATE_NOT_VALIDATED":
        return Row("roadmap_contract", RED, "final verdict must remain candidate", rel)
    if evidence.get("score") is not None:
        return Row("roadmap_contract", RED, "roadmap must not self-score", rel)
    if evidence.get("confidence", 1.0) > 0.65:
        return Row("roadmap_contract", RED, "candidate confidence exceeds bound", rel)
    schema_rel = "schemas/mfn_verification_roadmap.schema.json"
    if read_text(root, schema_rel) is None:
        return Row("roadmap_contract", UNKNOWN, "missing schema", schema_rel)
    return Row("roadmap_contract", OK, "machine-readable roadmap contract present", rel)


def json_contract_markers(root: Path) -> Row:
    required = {
        "tools/validate_json_artifact_contract.py": [
            "validate_contract",
            "score_requires_external_evidence",
        ],
        "tools/check_json_contract_evidence_policy.py": ["check_policy", "status_mismatch"],
        "tools/json_contract_receipt.py": ["sha256", "receipt"],
        "tools/run_json_artifact_checks.py": ["FIXTURES", "json_artifact_checks.v1"],
        "tools/run_autonomy_cycle.py": ["autonomy_cycle.v1", "READY_FOR_NEXT_CYCLE"],
        "tools/update_autonomy_trend.py": ["autonomy_trend.v1", "summary", "decision_counts"],
        "schemas/json_artifact_contract.schema.json": ["contract_type", "evidence_status"],
        "schemas/json_artifact_evidence_policy.schema.json": [
            "blocked_contract",
            "CANDIDATE_NOT_VALIDATED",
        ],
        "schemas/autonomy_cycle.schema.json": ["autonomy_cycle.v1", "READY_FOR_NEXT_CYCLE"],
        "schemas/autonomy_trend.schema.json": ["autonomy_trend.v1", "summary", "decision_counts"],
        "examples/json_artifact_contract.candidate.json": ["CANDIDATE_NOT_VALIDATED"],
    }
    missing: list[str] = []
    for rel, markers in required.items():
        text = read_text(root, rel)
        if text is None:
            missing.append(rel)
            continue
        absent = [marker for marker in markers if marker not in text]
        if absent:
            missing.append(rel + ":" + ",".join(absent))
    if missing:
        return Row("json_contract_markers", RED, "missing: " + "; ".join(missing), "tools")
    return Row("json_contract_markers", OK, "json contract markers present", "tools")


def collect(root: Path) -> list[Row]:
    return [
        makefile_cov(root),
        release_cov(root),
        workflow_import_path(root),
        pipeline_markers(root),
        cli_markers(root),
        contract_markers(root),
        roadmap_contract(root),
        json_contract_markers(root),
    ]


def payload(rows: list[Row]) -> dict[str, object]:
    counts = {OK: 0, WARN: 0, RED: 0, UNKNOWN: 0}
    for row in rows:
        counts[row.status] += 1
    status = RED if counts[RED] else UNKNOWN if counts[UNKNOWN] else WARN if counts[WARN] else OK
    return {"status": status, "counts": counts, "rows": [asdict(row) for row in rows]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    result = payload(collect(Path(args.root).resolve()))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and result["status"] not in {OK, WARN} else 0


if __name__ == "__main__":
    raise SystemExit(main())
