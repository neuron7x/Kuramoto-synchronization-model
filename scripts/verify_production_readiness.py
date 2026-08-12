#!/usr/bin/env python3
"""Generate GeoSync repository readiness artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "results" / "production_readiness"
SUMMARY_PATH = RESULT_DIR / "READINESS_SUMMARY.json"
MATRIX_PATH = RESULT_DIR / "GATE_MATRIX.csv"
VERDICT_PATH = RESULT_DIR / "RELEASE_VERDICT.md"
PASS = "PASS"
BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ReadinessClaim:
    claim_id: str
    scope: str
    check_command: str
    expected_artifact: str
    command_backed: bool = True


@dataclass(frozen=True)
class ReadinessRow:
    claim_id: str
    scope: str
    check_command: str
    expected_artifact: str
    artifact_hash: str
    commit_sha: str
    verdict: str
    detail: str


CLAIMS: tuple[ReadinessClaim, ...] = (
    ReadinessClaim(
        claim_id="production-readiness-doc",
        scope="docs",
        check_command="file exists",
        expected_artifact="docs/PRODUCTION_READINESS_STACK.md",
        command_backed=False,
    ),
    ReadinessClaim(
        claim_id="release-verdict-protocol",
        scope="docs",
        check_command="file exists",
        expected_artifact="docs/RELEASE_VERDICT_PROTOCOL.md",
        command_backed=False,
    ),
    ReadinessClaim(
        claim_id="readiness-verifier",
        scope="repository",
        check_command="script exists",
        expected_artifact="scripts/verify_production_readiness.py",
        command_backed=False,
    ),
    ReadinessClaim(
        claim_id="commit-acceptor",
        scope="repository",
        check_command="file exists",
        expected_artifact=".claude/commit_acceptors/production-readiness-stack.yaml",
        command_backed=False,
    ),
    ReadinessClaim(
        claim_id="test-suite-command",
        scope="repository",
        check_command="external CI evidence required",
        expected_artifact="results/production_readiness/READINESS_SUMMARY.json",
    ),
    ReadinessClaim(
        claim_id="lint-command",
        scope="repository",
        check_command="external CI evidence required",
        expected_artifact="results/production_readiness/READINESS_SUMMARY.json",
    ),
    ReadinessClaim(
        claim_id="type-check-command",
        scope="repository",
        check_command="external CI evidence required",
        expected_artifact="results/production_readiness/READINESS_SUMMARY.json",
    ),
    ReadinessClaim(
        claim_id="release-verdict-artifact",
        scope="artifact",
        check_command="file exists",
        expected_artifact="results/production_readiness/RELEASE_VERDICT.md",
        command_backed=False,
    ),
)


def current_commit() -> str:
    return os.environ.get("GITHUB_SHA", "UNKNOWN")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def evaluate_claim(
    claim: ReadinessClaim,
    *,
    commit_sha: str,
) -> ReadinessRow:
    artifact = ROOT / claim.expected_artifact
    if not artifact.exists():
        return ReadinessRow(
            claim_id=claim.claim_id,
            scope=claim.scope,
            check_command=claim.check_command,
            expected_artifact=claim.expected_artifact,
            artifact_hash="",
            commit_sha=commit_sha,
            verdict=BLOCKED,
            detail="expected artifact is absent",
        )

    artifact_hash = sha256_file(artifact)
    if claim.command_backed:
        return ReadinessRow(
            claim_id=claim.claim_id,
            scope=claim.scope,
            check_command=claim.check_command,
            expected_artifact=claim.expected_artifact,
            artifact_hash=artifact_hash,
            commit_sha=commit_sha,
            verdict=BLOCKED,
            detail="external CI evidence required",
        )

    return ReadinessRow(
        claim_id=claim.claim_id,
        scope=claim.scope,
        check_command=claim.check_command,
        expected_artifact=claim.expected_artifact,
        artifact_hash=artifact_hash,
        commit_sha=commit_sha,
        verdict=PASS,
        detail="artifact present",
    )


def build_summary(
    rows: list[ReadinessRow],
    *,
    commit_sha: str,
) -> dict[str, object]:
    counts = {PASS: 0, BLOCKED: 0}
    for row in rows:
        counts[row.verdict] += 1
    release_ready = counts[BLOCKED] == 0
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit_sha": commit_sha,
        "release_ready": release_ready,
        "verdict": PASS if release_ready else BLOCKED,
        "counts": counts,
        "rows": [asdict(row) for row in rows],
    }


def write_outputs(summary: dict[str, object], rows: list[ReadinessRow]) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    summary_text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    SUMMARY_PATH.write_text(summary_text, encoding="utf-8")

    with MATRIX_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))

    lines = [
        "# Release Verdict",
        "",
        f"Commit: `{summary['commit_sha']}`",
        f"Verdict: **{summary['verdict']}**",
        "",
    ]
    lines.extend(f"- `{row.claim_id}`: `{row.verdict}`" for row in rows)
    VERDICT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate GeoSync readiness verdict.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Accepted for compatibility; commands are not run.",
    )
    parser.add_argument(
        "--write-results",
        action="store_true",
        help="Write JSON/CSV/Markdown outputs.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Return non-zero unless every row is PASS.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    commit_sha = current_commit()
    rows = [evaluate_claim(claim, commit_sha=commit_sha) for claim in CLAIMS]
    summary = build_summary(rows, commit_sha=commit_sha)

    if args.write_results:
        write_outputs(summary, rows)

    console = {
        "counts": summary["counts"],
        "verdict": summary["verdict"],
    }
    print(json.dumps(console, sort_keys=True))
    return 1 if args.enforce and summary["verdict"] != PASS else 0


if __name__ == "__main__":
    raise SystemExit(main())
