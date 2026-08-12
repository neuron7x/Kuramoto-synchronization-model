# SPDX-License-Identifier: MIT
"""Bounded, mutation-excluding runner for the canonical Python 3.12 test suite.

This script runs the GeoSync test suite *honestly and safely* and captures a
commit-bound evidence receipt (JUnit XML + summary.json + environment
fingerprint) under ``artifacts/tests/full_py312/``.

SAFETY CONTRACT (non-negotiable)
--------------------------------
This repository contains SOURCE-REWRITING test lanes (mutation / ratchet
probes) that edit source files IN PLACE while they run. They MUST NOT be
collected or executed by this runner. See ``CLAUDE.md`` and
``.gitlab-ci.yml`` (the pipeline header explicitly warns that anything named
``*mutation*`` / ``*ratchet*`` rewrites source and must never run unattended).

This runner enforces the exclusion three ways, belt-and-braces:

1. ``--ignore`` for every known source-rewriting directory / file, so the
   dangerous modules are never even imported at collection time.
2. A ``-k`` de-selection expression (``not mutation and not ratchet ...``).
3. A ``-m`` marker de-selection (``not nightly and not flaky ...``).

Every pytest invocation is bounded by BOTH a per-test timeout
(``--timeout``, pytest-timeout) and an overall wall-clock timeout enforced by
this script (``subprocess`` ``timeout=``), so nothing can hang.

HONESTY CONTRACT
----------------
This sandbox is known to be below security floors for several dependencies
(ENV-001) and may lack GPU / network / market-data fixtures. A signed
0-failure receipt is therefore expected to require the ENV-005 hermetic
canonical container, NOT this sandbox. This runner records the REAL counts
(collected / passed / failed / errored / skipped) and emits an honest verdict
(``ENV_LIMITED`` / ``PARTIAL_SANDBOX`` / ``CLEAN``). It never fabricates a
0-failure result.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

# --------------------------------------------------------------------------- #
# Safety configuration                                                        #
# --------------------------------------------------------------------------- #

# Directories that contain source-rewriting probes (mutation / ratchet) or
# otherwise unsafe-to-run-unattended lanes. NEVER collected.
UNSAFE_IGNORE_DIRS: tuple[str, ...] = (
    "tests/mutation",
)

# Individual source-rewriting / ratchet files that live inside otherwise-mixed
# directories. Ignored explicitly so the safe siblings can still be collected.
UNSAFE_IGNORE_FILES: tuple[str, ...] = (
    "tests/ci/test_mutation_kill_ratchet.py",
    "tests/ci/test_ratchets_enforced.py",
    "tests/governance/test_truth_gate_mutation.py",
    "tests/physics/test_cognitive_core_mutation_tribunal.py",
    "tests/tools/test_verifier_mutation_kill.py",
    "tests/tools/test_coverage_intelligence_ratchet_edges.py",
)

# Keyword de-selection: second line of defence against any *mutation* / *ratchet*
# / nightly / gpu named test that a future refactor might add.
DESELECT_KEYWORDS = "not mutation and not ratchet and not nightly and not gpu"

# Marker de-selection: only markers that actually exist in pytest.ini.
# Excludes the slow / flaky / nightly / live / heavy lanes.
DESELECT_MARKERS = (
    "not nightly and not flaky and not slow and not canary "
    "and not live_balance and not heavy_math and not UNSTABLE"
)

# Default safe target: the large pure-logic unit surface. Deliberately NOT the
# whole `tests` tree, to keep the run bounded and away from the source-rewriting
# lanes by construction.
DEFAULT_TARGETS: tuple[str, ...] = ("tests/unit",)

# Dependencies whose versions are worth fingerprinting into the receipt.
FINGERPRINT_DEPS: tuple[str, ...] = (
    "numpy",
    "scipy",
    "pandas",
    "torch",
    "networkx",
    "numba",
    "hypothesis",
    "cryptography",
    "pytest",
    "pytest-timeout",
    "pytest-asyncio",
)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str | None:
    """Return trimmed ``git`` output, or ``None`` on any failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() or None


def _dep_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for dep in FINGERPRINT_DEPS:
        try:
            versions[dep] = metadata.version(dep)
        except metadata.PackageNotFoundError:
            versions[dep] = "MISSING"
    return versions


def environment_fingerprint(repo: Path) -> dict[str, object]:
    """Capture python / dependency / VCS identity for the receipt."""
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "commit": _git(repo, "rev-parse", "HEAD"),
        "tree_sha": _git(repo, "rev-parse", "HEAD^{tree}"),
        "branch": _git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "worktree_dirty": bool(_git(repo, "status", "--porcelain")),
        "dependency_versions": _dep_versions(),
    }


def build_pytest_args(
    targets: list[str],
    junit_path: Path,
    per_test_timeout: int,
    *,
    collect_only: bool,
) -> list[str]:
    """Construct a fully-bounded, mutation-excluding pytest argv."""
    # We intentionally do NOT neutralise the repo's pytest.ini ``addopts``:
    # the suite is DEFINED by that config (notably ``--import-mode=importlib``,
    # which the tree relies on to disambiguate duplicate test basenames such as
    # two ``test_schema_contracts.py`` files, and ``-W error::DeprecationWarning``
    # / ``--continue-on-collection-errors``). We only ADD safety exclusions,
    # bounding, and evidence capture on top of the canonical config, and raise
    # the fail-fast cap so the receipt sees ALL failures, not the first 50.
    args = [
        sys.executable,
        "-m",
        "pytest",
        *targets,
        "-p",
        "no:cacheprovider",  # never write/read stale collection cache
        "-p",
        "no:randomly",  # deterministic order if pytest-randomly is present
        "--import-mode=importlib",  # explicit; mirrors repo addopts, avoids clashes
        "-k",
        DESELECT_KEYWORDS,
        "-m",
        DESELECT_MARKERS,
        "--timeout",
        str(per_test_timeout),
        "--timeout-method=thread",
        "--continue-on-collection-errors",
        "-ra",
    ]
    for d in UNSAFE_IGNORE_DIRS:
        args.append(f"--ignore={d}")
    for f in UNSAFE_IGNORE_FILES:
        args.append(f"--ignore={f}")
    if collect_only:
        args.extend(["--collect-only", "-q"])
    else:
        args.extend(
            [
                f"--junit-xml={junit_path}",
                "--durations=25",
                "--maxfail=10000",  # override repo --maxfail=50: capture ALL
                "-q",
            ]
        )
    return args


def run_pytest(
    argv: list[str],
    repo: Path,
    job_timeout: int,
    log_path: Path,
) -> dict[str, object]:
    """Run pytest bounded by an overall wall-clock timeout; capture output."""
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=job_timeout,
            check=False,
        )
        returncode: int | None = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
    elapsed = time.monotonic() - started
    log_path.write_text(
        f"$ {' '.join(argv)}\n\n"
        f"--- STDOUT ---\n{stdout}\n"
        f"--- STDERR ---\n{stderr}\n",
        encoding="utf-8",
    )
    return {
        "returncode": returncode,
        "timed_out": timed_out,
        "wall_seconds": round(elapsed, 2),
    }


def parse_junit(junit_path: Path) -> dict[str, int]:
    """Extract real counts from the JUnit XML the run produced."""
    counts = {
        "collected": 0,
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
    }
    if not junit_path.exists():
        return counts
    root = ET.parse(junit_path).getroot()
    suites = root.iter("testsuite")
    total = failed = errors = skipped = 0
    for suite in suites:
        total += int(suite.get("tests", 0))
        failed += int(suite.get("failures", 0))
        errors += int(suite.get("errors", 0))
        skipped += int(suite.get("skipped", 0))
    counts["collected"] = total
    counts["failed"] = failed
    counts["errored"] = errors
    counts["skipped"] = skipped
    counts["passed"] = max(0, total - failed - errors - skipped)
    return counts


def derive_verdict(
    counts: dict[str, int],
    collection_errors: int,
    run_meta: dict[str, object],
    fingerprint: dict[str, object],
) -> str:
    """Honest verdict. Never fabricate CLEAN when the sandbox is limited."""
    if run_meta.get("timed_out"):
        return "ENV_LIMITED_TIMEOUT"
    below_floor = [
        d
        for d, v in fingerprint["dependency_versions"].items()  # type: ignore[index]
        if v == "MISSING"
    ]
    problems = (
        counts["failed"]
        + counts["errored"]
        + collection_errors
        + len(below_floor)
    )
    if problems == 0 and counts["collected"] > 0:
        # A truly clean sandbox result. The SIGNED canonical 0-failure receipt
        # still requires the ENV-005 hermetic container; this is the sandbox
        # mirror of that, honestly labelled.
        return "CLEAN_SANDBOX"
    if counts["collected"] == 0:
        return "NO_TESTS_COLLECTED"
    return "ENV_LIMITED"


# --------------------------------------------------------------------------- #
# Main                                                                         #
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Repository root (default: two levels up from this script).",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=list(DEFAULT_TARGETS),
        help="Test paths to run (default: the safe tests/unit surface).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=None,
        help="Receipt output dir (default: <repo>/artifacts/tests/full_py312).",
    )
    parser.add_argument("--per-test-timeout", type=int, default=45)
    parser.add_argument("--job-timeout", type=int, default=1500)
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only measure collection (no test bodies executed).",
    )
    args = parser.parse_args(argv)

    repo: Path = args.repo.resolve()
    outdir: Path = (args.outdir or (repo / "artifacts/tests/full_py312")).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    junit_path = outdir / "junit.xml"
    summary_path = outdir / "summary.json"

    fingerprint = environment_fingerprint(repo)

    # --- Phase 1: bounded collection probe (measures collection errors) ---
    collect_argv = build_pytest_args(
        args.targets, junit_path, args.per_test_timeout, collect_only=True
    )
    collect_meta = run_pytest(
        collect_argv, repo, min(args.job_timeout, 600), outdir / "collect.log"
    )
    collect_text = (outdir / "collect.log").read_text(encoding="utf-8")
    # pytest prints "errors during collection" / "ERROR <path>" on failure.
    collection_errors = collect_text.lower().count("error during collection")
    if "errors during collection" in collect_text.lower():
        collection_errors = max(collection_errors, 1)

    if args.collect_only:
        summary = {
            "task": "TST-001",
            "phase": "collect-only",
            "verdict": (
                "COLLECTION_CLEAN"
                if collection_errors == 0 and collect_meta["returncode"] == 0
                else "COLLECTION_ERRORS"
            ),
            "collection_errors": collection_errors,
            "collect_meta": collect_meta,
            "environment": fingerprint,
            "excluded_lanes": {
                "ignored_dirs": list(UNSAFE_IGNORE_DIRS),
                "ignored_files": list(UNSAFE_IGNORE_FILES),
                "deselect_keywords": DESELECT_KEYWORDS,
                "deselect_markers": DESELECT_MARKERS,
            },
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    # --- Phase 2: bounded run with JUnit receipt ---
    run_argv = build_pytest_args(
        args.targets, junit_path, args.per_test_timeout, collect_only=False
    )
    run_meta = run_pytest(run_argv, repo, args.job_timeout, outdir / "run.log")
    counts = parse_junit(junit_path)
    verdict = derive_verdict(counts, collection_errors, run_meta, fingerprint)

    below_floor = [
        d for d, v in fingerprint["dependency_versions"].items() if v == "MISSING"
    ]

    summary = {
        "task": "TST-001",
        "suite": "canonical_python_3.12",
        "verdict": verdict,
        "counts": counts,
        "collection_errors": collection_errors,
        "run_meta": run_meta,
        "targets": args.targets,
        "excluded_lanes": {
            "ignored_dirs": list(UNSAFE_IGNORE_DIRS),
            "ignored_files": list(UNSAFE_IGNORE_FILES),
            "deselect_keywords": DESELECT_KEYWORDS,
            "deselect_markers": DESELECT_MARKERS,
            "rationale": (
                "Source-rewriting mutation/ratchet lanes edit source in place "
                "(CLAUDE.md, .gitlab-ci.yml) and MUST NOT run. nightly/flaky/"
                "slow/canary/live/heavy lanes need infra/time this sandbox lacks."
            ),
        },
        "missing_dependencies": below_floor,
        "environment": fingerprint,
        "honesty_note": (
            "This is the SANDBOX receipt. The signed 0-failure canonical receipt "
            "is a task for the ENV-005 hermetic container run: this sandbox is "
            "below security floors for several deps (ENV-001) and may lack GPU/"
            "network/market-data fixtures. Counts above are the REAL observed "
            "numbers, not an asserted clean pass."
        ),
        "receipt_binding": {
            "commit": fingerprint["commit"],
            "tree_sha": fingerprint["tree_sha"],
            "junit_xml": str(junit_path.relative_to(repo)),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    # Exit 0: this runner's job is to PRODUCE an honest receipt, not to gate.
    # A non-clean sandbox verdict is expected and is reported, not raised.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
