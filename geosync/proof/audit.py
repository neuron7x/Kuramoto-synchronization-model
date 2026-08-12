# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""External-auditor claims gate: verdict EVERY claim in ``docs/CLAIMS.yaml`` without
trusting the author.

``python -m geosync.proof.audit`` re-derives every input from repository bytes — it
parses ``docs/CLAIMS.yaml``, parses the banned-phrase firewall LIVE from
``FORBIDDEN_CLAIMS.md`` (never hardcoded), and itself COLLECTS then RUNS each
``falsifier.test_id``. It never reads an author-produced verdict for outcomes: the
auditor executes the falsifier and cross-checks the subprocess return code against a
``--junitxml`` outcome (NEVER rc alone), so a green exit can never launder a
skipped/errored/empty run into support.

First principles:
  * A falsifier that FIRES (test fails) becomes ``REFUTED`` — the loudest signal,
    never hidden.
  * A falsifier that is NAMED but cannot be collected/run becomes ``DANGLING`` — a test
    that cannot fail is the worst silent hole (mirrors ``scripts/ci/check_falsifier_nodes.py``
    and honors its optional-dependency allowlist).

Per-claim verdict is a deterministic first-match function over five enum values::

    FORBIDDEN_LANGUAGE  banned status phrase in the claim description (static firewall)
    REFUTED             the falsifier FIRED (test failed / rc==1)
    DANGLING            the falsifier cannot fire (missing / collect error / non-allowlisted
                        skip / timeout / rc>=2 / rc0-without-junit-pass)
    NOT_TESTED          admissible-by-design absence: no falsifier on a non-ANCHORED claim,
                        an allowlisted optional-dependency skip, a heavy-marked node parked
                        in default mode, or a resolved-but-unexecuted node in --resolve-only
    SUPPORTED           the falsifier HELD (rc==0 AND junit outcome == 'passed')

Aggregate is weakest-link over all claims: any REJECT-class claim => REJECT; else any
PARTIAL-class (NOT_TESTED) => PARTIAL; else ACCEPT. Process exit is fail-closed: 1 iff
REJECT; ``--strict`` also fails PARTIAL for release signoff.

Modes:
  default        execute every RESOLVED, non-heavy falsifier (can earn SUPPORTED/REFUTED);
                 heavy-marked nodes (slow/heavy_math/nightly) are parked NOT_TESTED.
  --deep         execute everything, heavy nodes included.
  --resolve-only fast static pass: collect every falsifier (catches DANGLING +
                 FORBIDDEN_LANGUAGE in seconds), resolved nodes are NOT_TESTED-not-executed.

The report at ``artifacts/geosync_proof/audit.json`` is provenance-bound and
tamper-evident by REUSING ``geosync/proof/run.py`` helpers verbatim (``_code_version``,
``_sha256_file``, ``_canonical``, ``_content_digest``, ``DIGEST_KEY``). ``--verify
<report.json>`` recomputes the content digest and re-hashes the pinned policy/claims
files — an external party trusts the bytes on disk, not the author.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

# REUSE the provenance helpers from the proof demonstrator verbatim — the audit report is
# the same species of tamper-evident, provenance-bound artifact and must hash identically.
from geosync.proof.run import (  # noqa: F401
    DIGEST_KEY,
    _canonical,
    _code_version,
    _content_digest,
    _relpath,
    _sha256_file,
    _utc_timestamp,
)

ROOT = Path(__file__).resolve().parents[2]
CLAIMS = ROOT / "docs" / "CLAIMS.yaml"
FORBIDDEN = ROOT / "FORBIDDEN_CLAIMS.md"
ALLOWLIST = ROOT / ".github" / "falsifier_node_allowlist.json"
ARTIFACT = ROOT / "artifacts" / "geosync_proof" / "audit.json"

AUDIT_VERSION = "1"
REPRO_COMMAND = "python -m geosync.proof.audit"
DEFAULT_TIMEOUT = 120  # per-node subprocess cap; a future hang must not wedge the auditor.

# Hermetic pytest flags shared with scripts/ci/check_falsifier_nodes.py. ``-o addopts=``
# is load-bearing: it neutralizes pytest.ini addopts (--maxfail, -W error, --cov injection)
# so the verdict is deterministic regardless of repo defaults.
_HERMETIC = ["-p", "no:cacheprovider", "--no-header", "-o", "addopts=", "-q"]
# Only markers registered in pytest.ini — an unknown marker in ``-m`` would silently match
# nothing and mislabel every node as non-heavy.
_HEAVY_MARKERS = "slow or heavy_math or nightly"

# --- mode enum --------------------------------------------------------------
MODE_RESOLVE = "resolve"  # collect only, never execute
MODE_DEFAULT = "default"  # execute resolved non-heavy nodes
MODE_DEEP = "deep"  # execute everything

# --- verdict enum -----------------------------------------------------------
SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED"
DANGLING = "DANGLING"
NOT_TESTED = "NOT_TESTED"
FORBIDDEN_LANGUAGE = "FORBIDDEN_LANGUAGE"

# --- aggregate class enum ---------------------------------------------------
ACCEPT = "ACCEPT"
PARTIAL = "PARTIAL"
REJECT = "REJECT"

_VERDICT_CLASS = {
    SUPPORTED: ACCEPT,
    NOT_TESTED: PARTIAL,
    REFUTED: REJECT,
    DANGLING: REJECT,
    FORBIDDEN_LANGUAGE: REJECT,
}

# Severity for the weakest-link sort and the human report (most severe first). A cheap
# static-firewall breach dominates before any compute is spent; DANGLING (named-but-
# cannot-fire) ranks above NOT_TESTED (honestly-declared absence); SUPPORTED is greenest.
_SEVERITY = {
    FORBIDDEN_LANGUAGE: 0,
    REFUTED: 1,
    DANGLING: 2,
    NOT_TESTED: 3,
    SUPPORTED: 4,
}


def verdict_class(verdict: str) -> str:
    return _VERDICT_CLASS[verdict]


# ---------------------------------------------------------------------------
# Policy / claims parsing — the auditor derives every input from repo bytes.
# ---------------------------------------------------------------------------
def load_claims(path: Path = CLAIMS) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    claims = data if isinstance(data, list) else data.get("claims", [])
    return [c for c in claims if isinstance(c, dict)]


def load_allowlist(path: Path = ALLOWLIST) -> dict[str, str]:
    if not path.exists():
        return {}
    obj = json.loads(path.read_text(encoding="utf-8"))
    allow = obj.get("allow", {})
    return {str(k): str(v) for k, v in allow.items()} if isinstance(allow, dict) else {}


def parse_banned_phrases(text: str) -> list[str]:
    """Parse the ``Banned Status Language`` section of FORBIDDEN_CLAIMS.md, live.

    Never hardcode the list — the policy version is pinned by ``forbidden_sha256`` in the
    report, so the auditor honors whatever the committed firewall currently forbids. Only
    leading ``- `phrase``` list items inside the section are taken (the ``Allowed Status
    Language`` table and prose are excluded by the ``## `` section boundary).
    """
    phrases: list[str] = []
    in_section = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = "banned status language" in stripped.lower()
            continue
        if in_section:
            m = re.match(r"^-\s*`([^`]+)`", stripped)
            if m:
                phrases.append(m.group(1).strip().lower())
    # dedup, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def banned_hits(description: str, phrases: list[str]) -> list[str]:
    low = (description or "").lower()
    return [p for p in phrases if p and p in low]


# ---------------------------------------------------------------------------
# Two-phase falsifier execution (collect -> run), hermetic subprocess.
# ---------------------------------------------------------------------------
def _resolves(test_id: str, timeout: int = 90) -> tuple[bool, str]:
    """PHASE 1: does the node COLLECT? (mirror of check_falsifier_nodes._resolves).

    A node that cannot be collected cannot fire — a test that cannot fail.
    """
    path = test_id.split("::", 1)[0]
    if not (ROOT / path).exists():
        return False, "file missing"
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", *_HERMETIC, test_id],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # a collect that hangs is a falsifier that cannot fire -> fail-closed to DANGLING.
        return False, f"collect timeout after {timeout}s"
    except subprocess.SubprocessError as exc:
        return False, f"collect error: {type(exc).__name__}"
    if r.returncode == 0:
        return True, "collected"
    last = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()][-1:] or [""]
    return False, f"rc={r.returncode} {last[0][:80]}"


def _is_heavy(test_id: str, timeout: int = 90) -> bool:
    """Is the (already-resolved) node marked slow/heavy_math/nightly?

    Collect it under a ``not (<heavy markers>)`` filter: pytest rc==5 (no tests collected)
    means the node was DESELECTED, i.e. it carries a heavy marker. Conservative: any other
    rc/error is treated as NOT heavy so the real node still runs and surfaces a genuine
    result, never a silent park.
    """
    try:
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                *_HERMETIC,
                "-m",
                f"not ({_HEAVY_MARKERS})",
                test_id,
            ],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=timeout,
        )
    except subprocess.SubprocessError:
        return False
    return r.returncode == 5


def parse_junit_outcome(xml_text: str) -> str:
    """Reduce a junitxml report to one outcome. Precedence: failure > error > skipped >
    passed; ``empty`` when the report is absent/unparseable/testcase-less (the auditor then
    fails closed rather than trusting rc alone)."""
    if not xml_text.strip():
        return "empty"
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return "empty"
    cases = root.findall(".//testcase")
    if not cases:
        return "empty"
    seen: set[str] = set()
    for case in cases:
        tags = {child.tag for child in case}
        if "failure" in tags:
            seen.add("failure")
        elif "error" in tags:
            seen.add("error")
        elif "skipped" in tags:
            seen.add("skipped")
        else:
            seen.add("passed")
    for outcome in ("failure", "error", "skipped", "passed"):
        if outcome in seen:
            return outcome
    return "empty"


def _execute_node(test_id: str, timeout: int) -> tuple[object, str]:
    """PHASE 2: RUN the resolved node hermetically, cross-checking rc with junit outcome.

    Returns ``(rc, junit_outcome)``. On timeout: ``(None, 'timeout')``. No wall-clock timing
    is recorded — a provenance-bound, tamper-evident audit artifact must be bit-reproducible,
    and ambient time is banned in runtime roots (DETERMINISM_POLICY.md); the auditor can time
    the reproduction command themselves.
    """
    with tempfile.TemporaryDirectory() as td:
        junit = Path(td) / "j.xml"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", *_HERMETIC, "--junitxml", str(junit), test_id],
                capture_output=True,
                text=True,
                cwd=ROOT,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, "timeout"
        outcome = parse_junit_outcome(junit.read_text(encoding="utf-8") if junit.exists() else "")
    return r.returncode, outcome


def classify_execution(rc: object, junit_outcome: str, allowlisted: bool) -> tuple[str, str]:
    """Verdict for a RESOLVED, EXECUTED node — rc CROSS-CHECKED with junit, never rc alone.

    First match wins. SUPPORTED demands BOTH rc==0 AND junit=='passed'; every other
    combination is fail-closed to a non-green verdict so a green rc can never launder a
    skipped/errored/empty run into support.
    """
    if junit_outcome == "timeout" or rc in (2, 3):
        return DANGLING, f"fail-closed (rc={rc}, junit={junit_outcome})"
    if rc == 1 or junit_outcome == "failure":
        return REFUTED, "falsifier FIRED (test failed)"
    if rc == 0 and junit_outcome == "passed":
        return SUPPORTED, "falsifier held (test passed)"
    if junit_outcome == "skipped":
        if allowlisted:
            return NOT_TESTED, "ALLOWLISTED optional-dependency skip"
        return DANGLING, "non-allowlisted skip (falsifier did not run)"
    if junit_outcome == "error" or rc in (4, 5):
        if allowlisted:
            return NOT_TESTED, "ALLOWLISTED optional-dependency collect/skip"
        return DANGLING, f"collect/usage error (rc={rc}, junit={junit_outcome})"
    # rc0-without-junit-passed (e.g. 'empty'): never launder into SUPPORTED.
    return DANGLING, f"indeterminate (rc={rc}, junit={junit_outcome})"


# ---------------------------------------------------------------------------
# Per-claim decision table (first match wins) — deterministic, DI for teeth.
# ---------------------------------------------------------------------------
def audit_claim(
    claim: dict,
    banned: list[str],
    allow: dict[str, str],
    mode: str,
    per_test_timeout: int,
    resolve_fn: Callable[[str], tuple[bool, str]] = _resolves,
    execute_fn: Callable[[str, int], tuple[object, str]] = _execute_node,
    heavy_fn: Callable[[str], bool] = _is_heavy,
) -> dict:
    cid = str(claim.get("id", "<unknown>"))
    priority = str(claim.get("priority", ""))
    tier = str(claim.get("tier", ""))
    description = str(claim.get("description", ""))
    fobj = claim.get("falsifier")
    tid = str(fobj["test_id"]) if isinstance(fobj, dict) and fobj.get("test_id") else None
    allowlisted = tid is not None and tid in allow

    row: dict[str, object] = {
        "id": cid,
        "priority": priority,
        "tier": tier,
        "has_falsifier": tid is not None,
        "test_id": tid,
        "allowlisted": allowlisted,
        "collect_status": None,
        "run_rc": None,
        "junit_outcome": None,
        "verdict": None,
        "class": None,
        "detail": None,
    }

    def finish(verdict: str, detail: str) -> dict:
        row["verdict"] = verdict
        row["class"] = verdict_class(verdict)
        row["detail"] = detail
        return row

    # [1] static firewall — cheapest, dominates before any compute is spent.
    hits = banned_hits(description, banned)
    if hits:
        return finish(FORBIDDEN_LANGUAGE, "banned status language: " + ", ".join(hits))

    # [2]/[3] no falsifier: ANCHORED without a test is a BROKEN CONTRACT (Promotion-Invariant
    # #2 in FORBIDDEN_CLAIMS.md); non-ANCHORED without a test is admissible-by-design.
    if tid is None:
        if tier == "ANCHORED":
            return finish(DANGLING, "ANCHORED claim names no falsifier (Promotion-Invariant #2)")
        return finish(
            NOT_TESTED, f"{tier or 'non-ANCHORED'} claim declares no falsifier (by design)"
        )

    # PHASE 1: resolve (collect).
    resolved, why = resolve_fn(tid)
    row["collect_status"] = why
    if not resolved:
        if allowlisted:
            return finish(NOT_TESTED, f"ALLOWLISTED optional-dependency ({why})")
        return finish(DANGLING, f"falsifier does not collect ({why})")

    # resolve-only mode: never execute. Strongest honest verdict without running is
    # NOT_TESTED (PARTIAL) — a collectible-but-unrun node is NEVER upgraded to SUPPORTED.
    if mode == MODE_RESOLVE:
        return finish(NOT_TESTED, "resolved; not executed (--resolve-only)")

    # Heavy nodes are only RESOLVED in default mode; --deep executes everything.
    if mode != MODE_DEEP and heavy_fn(tid):
        return finish(NOT_TESTED, "heavy-marked node not executed in default mode (use --deep)")

    # PHASE 2: execute.
    rc, junit_outcome = execute_fn(tid, per_test_timeout)
    row["run_rc"] = rc
    row["junit_outcome"] = junit_outcome
    verdict, detail = classify_execution(rc, junit_outcome, allowlisted)
    return finish(verdict, detail)


def aggregate_verdict(rows: list[dict]) -> str:
    classes = {verdict_class(str(r["verdict"])) for r in rows}
    if REJECT in classes:
        return REJECT
    if PARTIAL in classes:
        return PARTIAL
    return ACCEPT


def process_exit_code(aggregate: str, strict: bool) -> int:
    """Fail-closed gate: nonzero iff aggregate == REJECT; --strict also fails PARTIAL."""
    if aggregate == REJECT:
        return 1
    if strict and aggregate == PARTIAL:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Report assembly — provenance-bound + tamper-evident.
# ---------------------------------------------------------------------------
def build_report(
    mode: str = MODE_DEFAULT,
    per_test_timeout: int = DEFAULT_TIMEOUT,
    claims_path: Path = CLAIMS,
    forbidden_path: Path = FORBIDDEN,
    allowlist_path: Path = ALLOWLIST,
    resolve_fn: Callable[[str], tuple[bool, str]] = _resolves,
    execute_fn: Callable[[str, int], tuple[object, str]] = _execute_node,
    heavy_fn: Callable[[str], bool] = _is_heavy,
) -> dict:
    """Produce the provenance-bound, tamper-evident audit report over every claim."""
    claims = load_claims(claims_path)
    banned = parse_banned_phrases(forbidden_path.read_text(encoding="utf-8"))
    allow = load_allowlist(allowlist_path)

    rows = [
        audit_claim(c, banned, allow, mode, per_test_timeout, resolve_fn, execute_fn, heavy_fn)
        for c in claims
    ]

    counts: dict[str, int] = {v: 0 for v in _SEVERITY}
    class_counts = {ACCEPT: 0, PARTIAL: 0, REJECT: 0}
    for r in rows:
        counts[str(r["verdict"])] = counts.get(str(r["verdict"]), 0) + 1
        class_counts[str(r["class"])] += 1
    aggregate = aggregate_verdict(rows)

    report: dict[str, object] = {
        "audit_version": AUDIT_VERSION,
        "repro_command": REPRO_COMMAND + ("" if mode == MODE_DEFAULT else f" --{mode}"),
        "mode": mode,
        "code_version": _code_version(),
        "timestamp_utc": _utc_timestamp(),
        "claims_source": _relpath(claims_path),
        "claims_sha256": _sha256_file(claims_path),
        "forbidden_source": _relpath(forbidden_path),
        "forbidden_sha256": _sha256_file(forbidden_path),
        "banned_phrases": banned,
        "claim_count": len(rows),
        "aggregate": aggregate,
        "counts": counts,
        "class_counts": class_counts,
        # source order preserved for stable diffs; render_table sorts by severity.
        "claims": rows,
    }
    # tamper-evident self-hash MUST be added last (covers every field above).
    report[DIGEST_KEY] = _content_digest(report)
    return report


def verify_report(path: Path) -> tuple[bool, list[str]]:
    """Independent auditor check on a produced report: recompute the content digest and
    re-hash the pinned policy/claims files. Trusts nothing but the bytes on disk."""
    problems: list[str] = []
    report = json.loads(path.read_text(encoding="utf-8"))

    claimed = report.get(DIGEST_KEY)
    recomputed = _content_digest(report)
    if claimed != recomputed:
        problems.append(
            f"content_digest mismatch: claimed {claimed!r} != recomputed {recomputed!r}"
        )

    for src_key, sha_key, fallback in (
        ("claims_source", "claims_sha256", CLAIMS),
        ("forbidden_source", "forbidden_sha256", FORBIDDEN),
    ):
        rel = str(report.get(src_key, ""))
        fpath = ROOT / rel if rel else fallback
        if fpath.exists():
            actual = _sha256_file(fpath)
            if actual != report.get(sha_key):
                problems.append(f"{sha_key} mismatch for {rel}: {actual} != {report.get(sha_key)}")
        else:
            problems.append(f"pinned file not found for re-hash: {rel}")

    return (not problems), problems


def write_report(report: dict, path: Path = ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Auditor-facing rendering.
# ---------------------------------------------------------------------------
def _sorted_rows(report: dict) -> list[dict]:
    # Most-severe first for the human eye; JSON keeps source order for stable diffs.
    return sorted(report["claims"], key=lambda r: (_SEVERITY[str(r["verdict"])], str(r["id"])))


def render_table(report: dict) -> str:
    rows = _sorted_rows(report)
    if not rows:
        return "  (no claims)"
    idw = max([len(str(r["id"])) for r in rows] + [len("CLAIM")])
    header = (
        f"  {'CLAIM'.ljust(idw)}  {'PRI'.ljust(3)}  {'TIER'.ljust(12)}  "
        f"{'VERDICT'.ljust(18)}  DETAIL"
    )
    lines = [header, "  " + "-" * (len(header) - 2)]
    for r in rows:
        lines.append(
            f"  {str(r['id']).ljust(idw)}  {str(r['priority']).ljust(3)}  "
            f"{str(r['tier']).ljust(12)}  {str(r['verdict']).ljust(18)}  {r['detail']}"
        )
    return "\n".join(lines)


def summary_line(report: dict, exit_code: int) -> str:
    c = report["counts"]
    cc = report["class_counts"]
    return (
        "GEOSYNC_AUDIT "
        f"aggregate={report['aggregate']} "
        f"mode={report['mode']} "
        f"claims={report['claim_count']} "
        f"supported={c[SUPPORTED]} "
        f"refuted={c[REFUTED]} "
        f"dangling={c[DANGLING]} "
        f"not_tested={c[NOT_TESTED]} "
        f"forbidden={c[FORBIDDEN_LANGUAGE]} "
        f"accept={cc[ACCEPT]} partial={cc[PARTIAL]} reject={cc[REJECT]} "
        f"code_version={report['code_version']} "
        f"exit={exit_code} "
        f"artifact={_relpath(ARTIFACT)}"
    )


def _resolve_mode(args: argparse.Namespace) -> str:
    if args.deep:
        return MODE_DEEP
    if args.resolve_only:
        return MODE_RESOLVE
    return MODE_DEFAULT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=REPRO_COMMAND,
        description="External-auditor gate over every claim in docs/CLAIMS.yaml. Runs each "
        "falsifier itself and folds tier + banned-language into one weakest-link verdict. "
        "Fail-closed: exit 1 on any REJECT-class finding. Emits a provenance-bound, "
        "tamper-evident report re-verifiable via --verify without trusting the author.",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="execute heavy-marked falsifiers too (default parks them NOT_TESTED).",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        dest="resolve_only",
        help="fast static pass: collect every falsifier (catch DANGLING + "
        "FORBIDDEN_LANGUAGE) without executing any node.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="release signoff: exit nonzero on PARTIAL too, not only REJECT.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"per-node subprocess timeout in seconds (default {DEFAULT_TIMEOUT}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ARTIFACT,
        help="report output path (default artifacts/geosync_proof/audit.json).",
    )
    parser.add_argument(
        "--verify",
        metavar="REPORT_JSON",
        type=Path,
        help="auditor mode: recompute the digest + re-hash pinned files of an "
        "existing report and report OK/TAMPERED.",
    )
    args = parser.parse_args(argv)

    if args.verify is not None:
        ok, problems = verify_report(args.verify)
        if ok:
            sys.stdout.write(f"GEOSYNC_AUDIT_VERIFY ok report={_relpath(args.verify)}\n")
            return 0
        sys.stderr.write(f"GEOSYNC_AUDIT_VERIFY TAMPERED report={_relpath(args.verify)}\n")
        for p in problems:
            sys.stderr.write(f"    {p}\n")
        return 1

    if args.deep and args.resolve_only:
        parser.error("--deep and --resolve-only are mutually exclusive")

    mode = _resolve_mode(args)
    report = build_report(mode=mode, per_test_timeout=args.timeout)
    write_report(report, args.out)

    exit_code = process_exit_code(str(report["aggregate"]), args.strict)
    sys.stdout.write(render_table(report) + "\n")
    sys.stdout.write(summary_line(report, exit_code) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
