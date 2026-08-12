#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CI permission & untrusted-PR boundary gate (SEC-011).

A GitHub Actions workflow is a *capability surface*. The two ways a repository
gets compromised through CI are well known and both are structural, not
behavioural:

1. **Over-broad default token.** A workflow with no ``permissions:`` block (or a
   ``write-all`` default) hands every job a read-write ``GITHUB_TOKEN``. A single
   compromised action or dependency can then push commits, publish releases, or
   open its own PRs. The fix is an explicit *least-privilege* top-level block —
   ``permissions: {contents: read}`` — with write scopes granted only on the one
   job that needs them, and only for a documented reason.

2. **``pull_request_target`` running untrusted head code with secrets.**
   ``pull_request_target`` runs in the *base* repo context: the workflow token
   and every ``secrets.*`` value are in scope, and the event is triggered by a
   fork PR. If such a workflow *checks out the PR head* (``actions/checkout``
   with a ``ref`` pointing at ``github.event.pull_request.head`` /
   ``github.head_ref``) and then executes any of that code, a malicious PR
   exfiltrates the repository's secrets. This is GitHub's own
   "pwn request" advisory. The safe pattern is: never check out + run PR-head
   code in a ``pull_request_target`` job that has secrets.

This gate parses **every** ``.github/workflows/*.yml`` (real YAML, not grep — the
use/mention trap is real: a workflow that merely *names* ``pull_request_target``
in a comment or in its own policy-checker text is not *using* it) and fails
closed on:

* ``MISSING_PERMISSIONS``  — no top-level ``permissions:`` block.
* ``WRITE_ALL_DEFAULT``    — top-level ``permissions: write-all``.
* ``UNSAFE_PRT_CHECKOUT``  — ``pull_request_target`` trigger + checkout of the
  PR head (secrets are always in scope under ``pull_request_target``).
* ``UNJUSTIFIED_WRITE_SCOPE`` — any ``write`` scope (top-level or job-level) that
  is not on the documented justification allowlist. This is what keeps the
  least-privilege default honest: a new, unexplained write grant breaks CI until
  a reviewer records *why* it is needed.

Non-fatal, reported for provenance:

* ``JUSTIFIED_WRITE_SCOPE`` — an allowlisted write scope (with its reason).
* ``SECRETS_IN_SCOPE``      — explicit ``secrets.*`` references (excl.
  ``GITHUB_TOKEN``).
* ``OIDC_ID_TOKEN``         — a job requests ``id-token: write`` (OIDC).

A deterministic JSON report (per-workflow permissions + flags) is written and
printed. Exit 0 = clean, 1 = one or more fatal flags, 2 = a workflow could not be
parsed (fail-closed).

Usage::

    python scripts/ci/check_ci_permissions.py
    python scripts/ci/check_ci_permissions.py --workflows .github/workflows
    python scripts/ci/check_ci_permissions.py --report artifacts/security/workflow_security_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOWS = ROOT / ".github/workflows"
DEFAULT_REPORT = ROOT / "artifacts/security/workflow_security_report.json"

EXIT_OK = 0
EXIT_FLAGGED = 1
EXIT_ERROR = 2

FATAL = "FATAL"
INFO = "INFO"

# Any explicit ${{ secrets.NAME }} reference other than the implicit workflow
# token. GITHUB_TOKEN is scoped by the permissions block this gate audits.
_SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z0-9_]+)\s*\}?")

# Expressions that resolve to the *untrusted* PR head. A checkout `ref:` holding
# any of these is checking out fork-authored code.
_PR_HEAD_TOKENS = (
    "github.event.pull_request.head.sha",
    "github.event.pull_request.head.ref",
    "github.event.pull_request.head.repo",
    "github.head_ref",
    "refs/pull/",
)

# Documented least-privilege exceptions. Every write scope NOT listed here is a
# fatal UNJUSTIFIED_WRITE_SCOPE. Key: (workflow_basename, location, scope) where
# location is "top" for the top-level block or the job id for a job-level block.
JUSTIFIED_WRITE_SCOPES: dict[tuple[str, str, str], str] = {
    (
        "codeql.yml",
        "top",
        "security-events",
    ): "Upload CodeQL SARIF analysis to the repository Security tab (github/codeql-action).",
    (
        "pr-gate.yml",
        "dependency-review",
        "pull-requests",
    ): "Post the dependency-review summary comment on the PR "
    "(actions/dependency-review-action, comment-summary-in-pr: on-failure). "
    "Trigger is pull_request (not pull_request_target); fork tokens are read-only regardless.",
    (
        "ricci-microstructure-gate.yml",
        "supply-chain",
        "id-token",
    ): "OIDC token for keyless SLSA build-provenance attestation "
    "(actions/attest-build-provenance). No secrets in scope; runs after the lane gate.",
    (
        "ricci-microstructure-gate.yml",
        "supply-chain",
        "attestations",
    ): "Write the SLSA build-provenance attestation to the attestations store "
    "(actions/attest-build-provenance).",
}


class CiPermissionError(Exception):
    """Fail-closed error (unreadable / unparseable workflow)."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CiPermissionError(f"cannot read/parse workflow {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CiPermissionError(f"{path}: top level must be a mapping")
    return raw


def _triggers(doc: dict[str, Any]) -> list[str]:
    """Return the workflow's trigger event names.

    PyYAML parses the bare key ``on:`` as the boolean ``True`` (YAML 1.1), so we
    look under both ``on`` and ``True``.
    """
    on = doc.get("on")
    if on is None:
        on = doc.get(True)
    if isinstance(on, dict):
        return [str(k) for k in on.keys()]
    if isinstance(on, list):
        return [str(k) for k in on]
    if on is None:
        return []
    return [str(on)]


def _write_scopes(perms: Any) -> dict[str, str]:
    """Scopes granted ``write`` in a permissions mapping."""
    if not isinstance(perms, dict):
        return {}
    return {str(k): str(v) for k, v in perms.items() if str(v) == "write"}


def _job_permissions(doc: dict[str, Any]) -> dict[str, Any]:
    jobs = doc.get("jobs")
    out: dict[str, Any] = {}
    if isinstance(jobs, dict):
        for job_id, spec in jobs.items():
            if isinstance(spec, dict) and "permissions" in spec:
                out[str(job_id)] = spec["permissions"]
    return out


# ${{ env.NAME }} / ${{ needs.x.outputs.NAME }} references inside a checkout ref.
_ENV_REF_RE = re.compile(r"env\.([A-Za-z0-9_]+)")


def _tainted_env_names(doc: dict[str, Any]) -> set[str]:
    """Env var NAMES (workflow/job/step scope) whose value resolves to the PR head.

    Enables detecting the indirection evasion (DS-08): ``PRREF: ${{ github.event.
    pull_request.head.sha }}`` referenced later as ``ref: ${{ env.PRREF }}``.
    """
    tainted: set[str] = set()

    def _scan(env: Any) -> None:
        if isinstance(env, dict):
            for name, value in env.items():
                if any(tok in str(value) for tok in _PR_HEAD_TOKENS):
                    tainted.add(str(name))

    _scan(doc.get("env"))
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        for spec in jobs.values():
            if not isinstance(spec, dict):
                continue
            _scan(spec.get("env"))
            steps = spec.get("steps")
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, dict):
                        _scan(step.get("env"))
    return tainted


def _ref_is_pr_head(ref: str, tainted_env: set[str]) -> bool:
    """A checkout ``ref`` points at the untrusted PR head, directly or via env."""
    if any(tok in ref for tok in _PR_HEAD_TOKENS):
        return True
    # env indirection: ref: ${{ env.PRREF }} where env.PRREF = PR head.
    return any(name in tainted_env for name in _ENV_REF_RE.findall(ref))


def _run_fetches_pr_head(run: str) -> bool:
    """A ``run:`` step fetches the PR head via ``refs/pull/<N>/head``.

    Catches the manual-checkout evasion (DS-08): ``git fetch origin
    refs/pull/N/head && git checkout FETCH_HEAD``. Requires BOTH ``refs/pull/``
    and ``/head`` so a benign ``git fetch origin main`` never trips it, and the
    PR *merge* ref (``refs/pull/N/merge``) is not mistaken for the raw head.
    """
    return "refs/pull/" in run and "/head" in run


def _checks_out_pr_head(doc: dict[str, Any]) -> bool:
    """True if any step brings the untrusted PR head into the workspace.

    Three surfaces (DS-08 closes the last two):
      1. actions/checkout with a ``ref`` resolving to the PR head — directly or
         through an ``env`` var that holds a PR-head expression;
      2. a ``run:`` step that fetches ``refs/pull/<N>/head`` (then FETCH_HEAD).
    """
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return False
    tainted_env = _tainted_env_names(doc)
    for spec in jobs.values():
        if not isinstance(spec, dict):
            continue
        steps = spec.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = str(step.get("uses", ""))
            if uses.startswith("actions/checkout"):
                ref = (
                    str((step.get("with") or {}).get("ref", ""))
                    if isinstance(step.get("with"), dict)
                    else ""
                )
                if _ref_is_pr_head(ref, tainted_env):
                    return True
            run = step.get("run")
            if isinstance(run, str) and _run_fetches_pr_head(run):
                return True
    return False


def _uses_oidc(doc: dict[str, Any], top_perms: Any) -> bool:
    if isinstance(top_perms, dict) and str(top_perms.get("id-token")) == "write":
        return True
    for perms in _job_permissions(doc).values():
        if isinstance(perms, dict) and str(perms.get("id-token")) == "write":
            return True
    return False


def audit_workflow(path: Path, raw_text: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Audit a single parsed workflow. Deterministic per-workflow record."""
    basename = path.name
    triggers = sorted(_triggers(doc))
    has_top = "permissions" in doc
    top_perms = doc.get("permissions")
    top_writes = _write_scopes(top_perms)
    job_perms = _job_permissions(doc)
    job_writes = {job: _write_scopes(p) for job, p in job_perms.items()}
    job_writes = {job: w for job, w in job_writes.items() if w}

    uses_prt = "pull_request_target" in triggers
    checks_pr_head = _checks_out_pr_head(doc)
    secret_refs = sorted({m for m in _SECRET_RE.findall(raw_text) if m != "GITHUB_TOKEN"})
    uses_oidc = _uses_oidc(doc, top_perms)

    flags: list[dict[str, str]] = []

    # --- FATAL: missing top-level permissions block --------------------------
    if not has_top:
        flags.append(
            {
                "level": FATAL,
                "code": "MISSING_PERMISSIONS",
                "message": (
                    "no top-level `permissions:` block — every job gets the "
                    "default read-write GITHUB_TOKEN. Add `permissions: "
                    "{contents: read}`."
                ),
            }
        )

    # --- FATAL: write-all default (top-level OR job-level) -------------------
    # A permissions value of the STRING "write-all" self-grants every write
    # scope; `_write_scopes` returns {} for a string, so this MUST be detected
    # here, not via the scope-justification path. "read-all" is read-only and is
    # deliberately NOT flagged. Job-level write-all is exactly as dangerous as a
    # top-level one and was previously missed (DS-07).
    if isinstance(top_perms, str) and top_perms == "write-all":
        flags.append(
            {
                "level": FATAL,
                "code": "WRITE_ALL_DEFAULT",
                "message": "top-level `permissions: write-all` grants every scope; forbidden.",
            }
        )
    for job_id in sorted(job_perms):
        jp = job_perms[job_id]
        if isinstance(jp, str) and jp == "write-all":
            flags.append(
                {
                    "level": FATAL,
                    "code": "WRITE_ALL_DEFAULT",
                    "message": (
                        f"job `{job_id}` `permissions: write-all` grants every scope; "
                        f"forbidden (a job self-granting write-all bypasses the "
                        f"least-privilege top-level default)."
                    ),
                }
            )

    # --- FATAL: pwn-request (pull_request_target + PR-head checkout) ----------
    if uses_prt and checks_pr_head:
        detail = (
            "pull_request_target checks out the untrusted PR head; secrets and "
            "the write token are always in scope under pull_request_target."
        )
        if secret_refs:
            detail += f" Explicit secrets in scope: {', '.join(secret_refs)}."
        flags.append({"level": FATAL, "code": "UNSAFE_PRT_CHECKOUT", "message": detail})

    # --- write-scope justification (top-level + job-level) --------------------
    def _classify(location: str, scopes: dict[str, str]) -> None:
        for scope in sorted(scopes):
            key = (basename, location, scope)
            reason = JUSTIFIED_WRITE_SCOPES.get(key)
            where = "top-level" if location == "top" else f"job `{location}`"
            if reason is None:
                flags.append(
                    {
                        "level": FATAL,
                        "code": "UNJUSTIFIED_WRITE_SCOPE",
                        "message": (
                            f"{where} grants `{scope}: write` with no recorded "
                            f"justification. Add it to JUSTIFIED_WRITE_SCOPES with a reason "
                            f"or remove the grant."
                        ),
                    }
                )
            else:
                flags.append(
                    {
                        "level": INFO,
                        "code": "JUSTIFIED_WRITE_SCOPE",
                        "message": f"{where} `{scope}: write` — {reason}",
                    }
                )

    _classify("top", top_writes)
    for job_id in sorted(job_writes):
        _classify(job_id, job_writes[job_id])

    # --- INFO: OIDC / secrets provenance -------------------------------------
    if uses_oidc:
        flags.append(
            {
                "level": INFO,
                "code": "OIDC_ID_TOKEN",
                "message": "requests `id-token: write` (OIDC); confirm the audience is scoped.",
            }
        )
    if secret_refs and not (uses_prt and checks_pr_head):
        flags.append(
            {
                "level": INFO,
                "code": "SECRETS_IN_SCOPE",
                "message": f"references secrets: {', '.join(secret_refs)}.",
            }
        )

    fatal = [f for f in flags if f["level"] == FATAL]
    return {
        "workflow": str(path.relative_to(ROOT)) if _under_root(path) else str(path),
        "name": str(doc.get("name", basename)),
        "triggers": triggers,
        "has_top_level_permissions": has_top,
        "top_level_permissions": top_perms if isinstance(top_perms, (dict, str)) else None,
        "top_level_write_scopes": sorted(top_writes),
        "job_write_scopes": {j: sorted(w) for j, w in sorted(job_writes.items())},
        "uses_pull_request_target": uses_prt,
        "checks_out_pr_head": checks_pr_head,
        "explicit_secret_refs": secret_refs,
        "uses_oidc_id_token": uses_oidc,
        "status": "FLAGGED" if fatal else "PASS",
        "fatal_count": len(fatal),
        "flags": flags,
    }


def _under_root(path: Path) -> bool:
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def audit_dir(workflows_dir: Path) -> dict[str, Any]:
    """Audit every ``*.yml``/``*.yaml`` under ``workflows_dir``. Fail-closed on parse error.

    GitHub Actions executes workflows with EITHER extension, so auditing only
    ``*.yml`` left an identical ``.yaml`` twin completely unaudited (DS-06).
    """
    files = sorted(set(workflows_dir.glob("*.yml")) | set(workflows_dir.glob("*.yaml")))
    workflows: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    for path in files:
        try:
            raw_text = path.read_text(encoding="utf-8")
            doc = _load_yaml(path)
        except CiPermissionError as exc:
            parse_errors.append({"workflow": path.name, "error": str(exc)})
            continue
        workflows.append(audit_workflow(path, raw_text, doc))

    workflows.sort(key=lambda w: w["workflow"])
    fatal_workflows = [w for w in workflows if w["fatal_count"]]
    if parse_errors:
        status = "ERROR"
    elif fatal_workflows:
        status = "FLAGGED"
    else:
        status = "PASS"
    return {
        "task": "SEC-011",
        "workflows_dir": (
            str(workflows_dir.relative_to(ROOT))
            if _under_root(workflows_dir)
            else str(workflows_dir)
        ),
        "status": status,
        "workflows_audited": len(workflows),
        "workflows_flagged": len(fatal_workflows),
        "parse_errors": parse_errors,
        "workflows": workflows,
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CI permission & untrusted-PR boundary gate (SEC-011)."
    )
    parser.add_argument(
        "--workflows",
        type=str,
        default=None,
        help="Workflows directory (default: .github/workflows).",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Also write the JSON report to this path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the report to stdout (still writes --report).",
    )
    args = parser.parse_args(argv)

    workflows_dir = Path(args.workflows) if args.workflows else DEFAULT_WORKFLOWS
    if not workflows_dir.is_dir():
        _emit({"status": "ERROR", "error": f"no such workflows dir: {workflows_dir}"})
        return EXIT_ERROR

    report = audit_dir(workflows_dir)

    if args.report is not None:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if not args.quiet:
        _emit(report)

    if report["status"] == "ERROR":
        return EXIT_ERROR
    return EXIT_FLAGGED if report["status"] == "FLAGGED" else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
