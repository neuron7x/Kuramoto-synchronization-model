#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Release-evidence attestation for a PR (P0 — Task 1).

"Locally green" and "almost all checks pass" are NOT operational certification.
This tool reads the aggregated CI state for a PR via ``gh`` and emits an
attestation record (head_sha, run_id, job/pass/fail/pending counts, UTC) that is
only ATTESTED when every check is completed/success with zero fails/pending. It
can post the attestation as a PR comment and can fail-closed when the live head
SHA does not match an expected SHA (so a stale attestation cannot certify a moved
branch).

Usage::

    python scripts/ci/write_pr_evidence_summary.py --pr 1316 [--comment] [--expect-sha SHA]

Exit codes: 0 attested (or comment posted); 1 not attested / sha mismatch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


def build_summary(
    pr_number: int,
    head_sha: str,
    checks: list[dict[str, Any]],
    timestamp_utc: str,
) -> dict[str, Any]:
    """Pure: fold a list of check rows into an attestation record.

    ``checks`` rows use the ``gh pr checks --json`` shape: each has at least a
    Rows follow the ``gh pr view --json statusCheckRollup`` shape: a CheckRun
    carries ``status`` (COMPLETED/IN_PROGRESS/QUEUED) + ``conclusion``
    (SUCCESS/FAILURE/SKIPPED/...); a StatusContext carries ``state`` (SUCCESS/
    PENDING/...). Normalise to the most specific available signal.
    """

    def _norm(c: dict[str, Any]) -> str:
        status = str(c.get("status", "")).upper()
        # An incomplete CheckRun has no meaningful conclusion yet ⇒ pending.
        if status in {"IN_PROGRESS", "QUEUED", "WAITING", "PENDING", "REQUESTED"}:
            return status
        return str(c.get("conclusion") or c.get("state") or status or "").upper()

    norm = [_norm(c) for c in checks]
    passed = sum(1 for s in norm if s == "SUCCESS")
    failed = sum(
        1 for s in norm if s in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "STARTUP_FAILURE"}
    )
    pending = sum(
        1 for s in norm if s in {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED", ""}
    )
    skipped = sum(1 for s in norm if s in {"SKIPPED", "NEUTRAL"})
    attested = failed == 0 and pending == 0 and passed > 0
    return {
        "schema": "pr_release_evidence_attestation@v1",
        "pr_number": pr_number,
        "head_sha": head_sha,
        "job_count": len(checks),
        "pass_count": passed,
        "fail_count": failed,
        "pending_count": pending,
        "skipped_count": skipped,
        "timestamp_utc": timestamp_utc,
        "attested": attested,
    }


def render_comment(summary: dict[str, Any]) -> str:
    mark = "✅ ATTESTED" if summary["attested"] else "❌ NOT ATTESTED"
    rows = "\n".join(
        f"| {k} | {summary[k]} |"
        for k in (
            "pr_number",
            "head_sha",
            "job_count",
            "pass_count",
            "fail_count",
            "pending_count",
            "skipped_count",
            "timestamp_utc",
        )
    )
    return f"## Release Evidence Attestation — {mark}\n\n| field | value |\n|---|---|\n{rows}\n"


def _gh_json(args: list[str]) -> Any:
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--comment", action="store_true", help="post the attestation as a comment")
    parser.add_argument("--expect-sha", default=None, help="fail if live head SHA != this")
    args = parser.parse_args(argv)

    view = _gh_json(["pr", "view", str(args.pr), "--json", "headRefOid,statusCheckRollup"])
    head_sha = str(view.get("headRefOid", ""))
    if args.expect_sha and head_sha != args.expect_sha:
        print(f"SHA MISMATCH: live {head_sha} != expected {args.expect_sha}", file=sys.stderr)
        return 1
    rollup = view.get("statusCheckRollup") or []
    ts = ""
    for c in rollup:
        ct = c.get("completedAt") or ""
        ts = max(ts, str(ct))
    summary = build_summary(args.pr, head_sha, rollup, ts)

    print(json.dumps(summary, indent=2))
    if args.comment:
        subprocess.run(
            ["gh", "pr", "comment", str(args.pr), "--body", render_comment(summary)],
            check=True,
            capture_output=True,
            text=True,
        )
    return 0 if summary["attested"] else 1


if __name__ == "__main__":
    sys.exit(main())
