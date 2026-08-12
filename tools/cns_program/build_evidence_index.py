#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

OUT = Path("results/cns_evidence_index.json")


def generated_json_files(results_dir: Path) -> list[str]:
    files = []
    for path in sorted(results_dir.glob("cns_*.json")):
        if path.name == OUT.name:
            continue
        files.append(path.as_posix())
    return files


def build_index(
    *,
    python_version: str,
    artifact_name: str,
    artifact_digest: str,
    results_dir: Path,
) -> dict[str, object]:
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "run_id": os.getenv("GITHUB_RUN_ID", "local"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", "local"),
        "head_sha": os.getenv("GITHUB_SHA", "local"),
        "workflow": os.getenv("GITHUB_WORKFLOW", "local"),
        "python_version": python_version,
        "artifact_name": artifact_name,
        "artifact_digest": artifact_digest,
        "generated_json_files": generated_json_files(results_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-version", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--artifact-digest", required=True)
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()

    payload = build_index(
        python_version=args.python_version,
        artifact_name=args.artifact_name,
        artifact_digest=args.artifact_digest,
        results_dir=Path(args.results_dir),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
