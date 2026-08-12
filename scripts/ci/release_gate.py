#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Verification-first release gate — the single machine entrypoint.

The canonical principle: a repository's value is not its complexity, its
timelines, or the beauty of its architecture — it is the *reproducible
ability to survive falsification and leave behind a verified artifact*.
This gate refuses to let that judgement be made in prose. Each A–R section
of the release contract is reduced to a probe that returns a machine
result; the overall verdict is GREEN only if every gating probe is GREEN.

A probe returns one of:

* ``GREEN``   — machine-verified pass, with the evidence command/value.
* ``RED``     — machine-verified failure (the artifact contradicts the claim).
* ``MANUAL``  — requires a human/domain artifact this gate cannot synthesise.
                Per the absolute rule ("no item closed with words"), an
                unresolved MANUAL item is *not* GREEN and forces the release
                RED until a real artifact is supplied.

Heavy probes (clean-room wheel build + install) run only under ``--deep``
so the fast lane stays under a CI minute; the provenance cold-verify is
cheap and always runs.

Usage::

    python scripts/ci/release_gate.py            # fast probes
    python scripts/ci/release_gate.py --deep      # + wheel build/install
    python scripts/ci/release_gate.py --json out.json

Exit codes::

    0  — every gating probe GREEN and no unresolved MANUAL gating item
    1  — at least one gating probe RED or MANUAL (release is RED)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]

GREEN = "GREEN"
RED = "RED"
MANUAL = "MANUAL"

# Directories that are not first-party runtime source for the import-hygiene
# probes (tests legitimately manipulate sys.path / import test fixtures).
_NON_SOURCE_PREFIXES: tuple[str, ...] = (
    "tests/",
    "test/",
    ".git/",
    "build/",
    "dist/",
    "node_modules/",
)

_SRC_IMPORT_RE = re.compile(r"^\s*(from|import)\s+src(\.|\s|$)")
_PATH_HACK_RE = re.compile(r"sys\.path\.(insert|append)\s*\(")


@dataclass
class Probe:
    pid: str
    section: str
    title: str
    gating: bool
    run: Callable[[bool], tuple[str, str]]


@dataclass
class Result:
    pid: str
    section: str
    title: str
    gating: bool
    status: str
    evidence: str


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _tracked_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _first_party_py() -> list[str]:
    out: list[str] = []
    for rel in _tracked_files():
        if not rel.endswith(".py"):
            continue
        if any(rel.startswith(p) for p in _NON_SOURCE_PREFIXES):
            continue
        out.append(rel)
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exists(*names: str) -> bool:
    return any((ROOT / n).exists() for n in names)


# --------------------------------------------------------------------------
# A. Product claim boundary
# --------------------------------------------------------------------------
def probe_a_claim_files(deep: bool) -> tuple[str, str]:
    boundary = _exists("CLAIM_BOUNDARY.md", "PRODUCT_CATEGORY.md")
    forbidden = _exists("FORBIDDEN_CLAIMS.md")
    if boundary and forbidden:
        return GREEN, "claim-boundary + FORBIDDEN_CLAIMS docs present"
    missing = []
    if not boundary:
        missing.append("CLAIM_BOUNDARY.md/PRODUCT_CATEGORY.md")
    if not forbidden:
        missing.append("FORBIDDEN_CLAIMS.md")
    return RED, "missing: " + ", ".join(missing)


def probe_a_claim_gate(deep: bool) -> tuple[str, str]:
    script = ROOT / "scripts" / "ci" / "check_claim_boundary.py"
    if not script.exists():
        return RED, "scripts/ci/check_claim_boundary.py absent (claim gate not installed)"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return GREEN, proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "exit 0"
    return RED, "check_claim_boundary.py exited nonzero"


# --------------------------------------------------------------------------
# B. Package / import architecture
# --------------------------------------------------------------------------
def probe_b_src_imports(deep: bool) -> tuple[str, str]:
    hits = [
        rel
        for rel in _first_party_py()
        if any(
            _SRC_IMPORT_RE.search(line)
            for line in (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        )
    ]
    if not hits:
        return GREEN, "no first-party `src.*` imports"
    return RED, f"{len(hits)} first-party files import `src.*` (e.g. {hits[0]})"


def probe_b_path_hacks(deep: bool) -> tuple[str, str]:
    hits = [
        rel
        for rel in _first_party_py()
        if rel.rsplit("/", 1)[-1] != "conftest.py"
        and any(
            _PATH_HACK_RE.search(line)
            for line in (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        )
    ]
    if not hits:
        return GREEN, "no runtime sys.path hacks in first-party source"
    return RED, f"{len(hits)} first-party files mutate sys.path (e.g. {hits[0]})"


def probe_b_single_package(deep: bool) -> tuple[str, str]:
    dual = (ROOT / "geosync").is_dir() and (ROOT / "src" / "geosync").is_dir()
    if dual:
        return RED, "both geosync/ and src/geosync/ exist (dual canonical package)"
    return GREEN, "single geosync package root"


def probe_b_wheel(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "skipped (run with --deep for clean-room wheel build/install)"
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        arch = tdp / "src.tar"
        with arch.open("wb") as fh:
            subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                cwd=ROOT,
                stdout=fh,
                check=True,
            )
        srcdir = tdp / "src_tree"
        srcdir.mkdir()
        subprocess.run(["tar", "-xf", str(arch), "-C", str(srcdir)], check=True)
        wheeldir = tdp / "wheel"
        build = subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheeldir), str(srcdir)],
            capture_output=True,
            text=True,
            check=False,
        )
        wheels = list(wheeldir.glob("*.whl"))
        if build.returncode != 0 or not wheels:
            return RED, "wheel build failed from clean git archive"
        import zipfile

        with zipfile.ZipFile(wheels[0]) as zf:
            tops = sorted({n.split("/")[0] for n in zf.namelist()})
        pkgs = [t for t in tops if not t.endswith(".dist-info")]
        non_geosync = [t for t in pkgs if not t.startswith("geosync")]
        if non_geosync:
            return RED, (
                f"wheel ships {len(pkgs)} top-level packages, "
                f"{len(non_geosync)} outside geosync* (e.g. {', '.join(non_geosync[:6])})"
            )
        return GREEN, f"wheel ships only geosync* ({len(pkgs)} packages)"


# --------------------------------------------------------------------------
# C. Dependency truth
# --------------------------------------------------------------------------
def probe_c_lock(deep: bool) -> tuple[str, str]:
    if _exists("requirements.lock"):
        return GREEN, "requirements.lock present"
    return RED, "no requirements.lock"


def probe_c_dep_truth(deep: bool) -> tuple[str, str]:
    val = ROOT / "tools" / "deps" / "validate_dependency_truth.py"
    if not val.exists():
        return MANUAL, "tools/deps/validate_dependency_truth.py absent"
    proc = subprocess.run(
        [sys.executable, str(val), "--exit-on-drift"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return GREEN, "dependency-truth validator: no drift"
    return RED, "dependency-truth validator reports drift"


# --------------------------------------------------------------------------
# S. Security — dependency vulnerability gate (HIGH/CRITICAL, fail-closed)
# --------------------------------------------------------------------------
def probe_s_dep_vulns(deep: bool) -> tuple[str, str]:
    """Run pip-audit over the runtime lock and feed it to the HIGH gate.

    Reuses the canonical fail-closed gate (.github/scripts/pip_audit_high_gate.py),
    not a new verifier. A clean audit is GREEN; a HIGH/CRITICAL finding is RED.
    Tooling/network failure to *run* pip-audit degrades to MANUAL (never a
    false GREEN, never a RED that blames a real vuln for a network hiccup).
    """
    if not deep:
        return MANUAL, "skipped (run with --deep for pip-audit HIGH/CRITICAL gate)"
    gate = ROOT / ".github" / "scripts" / "pip_audit_high_gate.py"
    lock = ROOT / "requirements.lock"
    if not gate.exists() or not lock.exists():
        return MANUAL, "pip_audit_high_gate.py or requirements.lock absent"
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "pip-audit-runtime.json"
        # pip-audit exit: 0 = no vulns, 1 = vulns found (still emits JSON);
        # anything else (no JSON written) is a tooling/network failure. We gate
        # on the JSON via the HIGH gate, so the return code itself is unused.
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(lock),
                "-f",
                "json",
                "-o",
                str(report),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if not report.exists():
            return MANUAL, "pip-audit could not run (tooling/network) — audit deferred"
        high = subprocess.run(
            [sys.executable, str(gate), str(report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if high.returncode == 0:
            return GREEN, "pip-audit: no HIGH/CRITICAL dependency vulnerabilities"
        tail = (high.stdout or high.stderr).strip().splitlines()
        return RED, tail[-1] if tail else "HIGH/CRITICAL dependency vulnerability"


# --------------------------------------------------------------------------
# D. Provenance / evidence bundle
# --------------------------------------------------------------------------
def _load_generate_manifest() -> object:
    """Load the canonical cold-verify implementation from the sibling module.

    release_gate.py is loaded both as ``python scripts/ci/release_gate.py`` and
    (in tests) via ``importlib.util.spec_from_file_location`` with no package
    context, so a plain ``from scripts.ci import generate_manifest`` is not
    reliable. Load it by path from this file's own directory instead.
    """
    import importlib.util

    path = Path(__file__).resolve().parent / "generate_manifest.py"
    spec = importlib.util.spec_from_file_location("geosync_generate_manifest", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_d_manifest_coldverify(deep: bool) -> tuple[str, str]:
    """Supply-chain integrity proof — delegates to the ONE canonical
    cold-verify (``generate_manifest.cold_verify``), the same implementation
    ``check_root_manifest.py`` drives via ``--check``.

    The prior in-probe loop iterated only lines PRESENT in the manifest and so
    was coverage-blind: dropping a file's line (and corrupting that file) or
    adding a tracked file absent from the manifest both read GREEN. The
    canonical implementation rebuilds the manifest from ``git ls-files`` and
    does a symmetric set comparison, so the manifest must COVER the tracked
    tree — the two surfaces can no longer diverge.
    """
    gm = _load_generate_manifest()
    ok, detail = gm.cold_verify(ROOT)  # type: ignore[attr-defined]
    return (GREEN, detail) if ok else (RED, detail)


# --------------------------------------------------------------------------
# F. Invariant grounding
# --------------------------------------------------------------------------
def probe_f_invariants(deep: bool) -> tuple[str, str]:
    script = ROOT / "scripts" / "count_invariants.py"
    if not script.exists():
        return RED, "scripts/count_invariants.py absent"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "exit 0"
        return GREEN, f"invariant registry consistent ({last})"
    return RED, "count_invariants.py exited nonzero (registry/header drift)"


# --------------------------------------------------------------------------
# P. Test maturity (presence floor)
# --------------------------------------------------------------------------
def probe_p_tests(deep: bool) -> tuple[str, str]:
    n = sum(1 for rel in _tracked_files() if "/test_" in f"/{rel}" and rel.endswith(".py"))
    if n > 0:
        return GREEN, f"{n} test files tracked"
    return RED, "no test files"


# --------------------------------------------------------------------------
# H. Falsifier-ledger registry gate (main hardening: doc/registry scanner)
# --------------------------------------------------------------------------
def probe_h_falsifier_ledger(deep: bool) -> tuple[str, str]:
    script = ROOT / "scripts" / "ci" / "check_falsifier_ledger.py"
    if not script.exists():
        return RED, "scripts/ci/check_falsifier_ledger.py absent (falsifier gate not installed)"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "exit"
    if proc.returncode == 0:
        return GREEN, last
    return RED, last


# --------------------------------------------------------------------------
# Executable proof-gate probes (E/G/H/K/M/Q). Each delegates to a generator
# under scripts/ci/ that emits a machine artifact carrying a verdict. The fast
# lane returns MANUAL ("requires --deep") — exactly like B.wheel — because the
# verdict cannot be cheaply re-derived from committed prose. Under --deep the
# generator is re-run from scratch so the verdict reflects live machine
# evidence at HEAD, never a stale or hand-edited artifact.
# --------------------------------------------------------------------------
def _regenerate(module: str, extra: tuple[str, ...] = ()) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", module, *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode


def _read_artifact(rel: str) -> dict[str, object] | None:
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def probe_e_clean_clone(deep: bool) -> tuple[str, str]:
    if not deep:
        return (
            MANUAL,
            "requires --deep (clean-room wheel build + isolated install + entrypoint smoke)",
        )
    if _regenerate("scripts.ci.probe_clean_clone") != 0:
        return RED, "regeneration failed (stale artifact refused)"
    art = _read_artifact("artifacts/release_gate/clean_clone.json")
    if art is None:
        return RED, "clean_clone.json not produced by probe_clean_clone.py"
    if art.get("status") == "PASS":
        return (
            GREEN,
            "clean archive → wheel → isolated install → import geosync → entrypoints wired",
        )
    stages = art.get("stages", [])
    bad = [s.get("stage") for s in stages if isinstance(s, dict) and not s.get("ok")]
    return RED, f"clean-clone FAILED at stages: {bad}"


def probe_g_real_data(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "requires --deep (real-data evidence manifest validation)"
    if _regenerate("scripts.ci.real_data_probe") != 0:
        return RED, "regeneration failed (stale artifact refused)"
    art = _read_artifact("artifacts/evidence/real_data_manifest.json")
    if art is None:
        return RED, "real_data_manifest.json not produced by real_data_probe.py"
    status = art.get("status")
    if status in ("MEASURED_SINGLE", "MEASURED_MULTI"):
        return (
            GREEN,
            f"real-data evidence tier {status} from {art.get('manifests_found')} manifest(s)",
        )
    return (
        RED,
        f"real-data tier {status}: {art.get('blocker') or 'insufficient real-data evidence'}",
    )


def probe_h_falsification(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "requires --deep (8-control executable falsification ledger)"
    if _regenerate("scripts.ci.falsification_ledger") != 0:
        return RED, "regeneration failed (stale artifact refused)"
    art = _read_artifact("artifacts/falsification/ledger.json")
    if art is None:
        return RED, "ledger.json not produced by falsification_ledger.py"
    controls = art.get("controls", [])
    survived = sum(1 for c in controls if isinstance(c, dict) and c.get("verdict") == "SURVIVED")
    if art.get("promotion_allowed") is True:
        return GREEN, f"falsification ledger: {survived}/{len(controls)} controls SURVIVED"
    bad = [
        c.get("name") for c in controls if isinstance(c, dict) and c.get("verdict") != "SURVIVED"
    ]
    return RED, f"falsification ledger blocks promotion; non-SURVIVED: {bad}"


def probe_k_execution(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "requires --deep (execution-scope contract + claim-boundary enforcement)"
    if _regenerate("scripts.ci.execution_contract") != 0:
        return RED, "regeneration failed (stale artifact refused)"
    art = _read_artifact("artifacts/execution/contract.json")
    if art is None:
        return RED, "contract.json not produced by execution_contract.py"
    if art.get("status") == "PASS" and art.get("claim_boundary_enforced") is True:
        return GREEN, f"execution {art.get('scope')}; claim-boundary firewall enforced"
    return (
        RED,
        "execution out-of-scope declaration contradicted by an unreviewed live-trading claim",
    )


def probe_m_benchmarks(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "requires --deep (benchmark spine: determinism + regression budget)"
    if _regenerate("scripts.ci.benchmark_spine") != 0:
        return RED, "regeneration failed (stale artifact refused)"
    art = _read_artifact("artifacts/benchmarks/last_run.json") or _read_artifact(
        "artifacts/benchmarks/baseline.json"
    )
    if art is None:
        return RED, "benchmark baseline.json not produced by benchmark_spine.py"
    if art.get("status") in ("PASS", "ESTABLISHED"):
        return GREEN, f"benchmark spine {art.get('status')} (hardware {art.get('hardware_id')})"
    return RED, "benchmark regression or non-determinism beyond budget"


def probe_q_replication(deep: bool) -> tuple[str, str]:
    if not deep:
        return MANUAL, "requires --deep (reviewer packet + hash-locked expected outputs)"
    # Verify the freshly-regenerated E/H/K/M/G artifacts (produced by the
    # probes that ran earlier this --deep pass) against the COMMITTED hash-lock.
    # The expected_hashes.json is NOT regenerated here — that would be circular;
    # drift between committed lock and fresh artifacts is the signal.
    if not (ROOT / "artifacts/replication/REVIEWER_PACKET.md").exists():
        return RED, "REVIEWER_PACKET.md absent (run scripts/ci/replication_packet.py)"
    if _read_artifact("artifacts/replication/expected_hashes.json") is None:
        return RED, "expected_hashes.json absent (run scripts/ci/replication_packet.py)"
    verify = subprocess.run(
        [sys.executable, "-m", "scripts.ci.replication_packet", "--verify"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode == 0:
        return GREEN, "reviewer packet present; all artifact projections match hash-lock"
    last = verify.stdout.strip().splitlines()[-1] if verify.stdout.strip() else "drift"
    return RED, f"replication hash-lock drift: {last}"


PROBES: list[Probe] = [
    Probe(
        "A.claim_files",
        "A",
        "Claim-boundary + forbidden-claims docs exist",
        True,
        probe_a_claim_files,
    ),
    Probe("A.claim_gate", "A", "Claim-boundary doc scanner passes", True, probe_a_claim_gate),
    Probe("B.src_imports", "B", "No first-party `src.*` imports", True, probe_b_src_imports),
    Probe("B.path_hacks", "B", "No runtime sys.path hacks", True, probe_b_path_hacks),
    Probe("B.single_pkg", "B", "Single canonical geosync package", True, probe_b_single_package),
    Probe("B.wheel", "B", "Wheel ships only geosync* (clean-room)", True, probe_b_wheel),
    Probe("C.lock", "C", "requirements.lock present", True, probe_c_lock),
    Probe("C.dep_truth", "C", "Dependency-truth validator clean", True, probe_c_dep_truth),
    Probe(
        "S.dep_vulns",
        "S",
        "No HIGH/CRITICAL dependency vulnerabilities (pip-audit)",
        True,
        probe_s_dep_vulns,
    ),
    Probe(
        "D.manifest", "D", "MANIFEST.sha256 cold-verify clean", True, probe_d_manifest_coldverify
    ),
    Probe("F.invariants", "F", "Invariant registry consistent", True, probe_f_invariants),
    Probe("P.tests", "P", "Test suite present", True, probe_p_tests),
    Probe(
        "E.clean_clone",
        "E",
        "Clean-clone wheel install + CLI entrypoints run",
        True,
        probe_e_clean_clone,
    ),
    Probe(
        "G.real_data",
        "G",
        "Multi-session/day/venue real-data evidence tracks",
        True,
        probe_g_real_data,
    ),
    Probe(
        "H.falsifier_ledger",
        "H",
        "Falsifier-ledger registry: every null/falsifier resolves to real code + witness",
        True,
        probe_h_falsifier_ledger,
    ),
    Probe(
        "H.falsification",
        "H",
        "Executable falsification ledger: 8 controls SURVIVE under --deep regeneration",
        True,
        probe_h_falsification,
    ),
    Probe(
        "K.execution",
        "K",
        "Execution contract: fills/slippage/adverse-selection/recovery",
        True,
        probe_k_execution,
    ),
    Probe(
        "M.benchmarks",
        "M",
        "Latency/throughput/memory + CPU/GPU parity with regression budget",
        True,
        probe_m_benchmarks,
    ),
    Probe(
        "Q.replication",
        "Q",
        "Reviewer packet + cold-rerun + signed verification + repro capsule",
        True,
        probe_q_replication,
    ),
]


def evaluate(deep: bool) -> list[Result]:
    results: list[Result] = []
    for p in PROBES:
        try:
            status, evidence = p.run(deep)
        except Exception as exc:
            status, evidence = RED, f"probe raised: {exc!r}"
        results.append(Result(p.pid, p.section, p.title, p.gating, status, evidence))
    return results


def render(results: list[Result]) -> str:
    icon = {GREEN: "GREEN", RED: "RED ", MANUAL: "MANL"}
    lines = ["", "GeoSync Verification-First Release Gate", "=" * 64]
    for r in results:
        gate = "gate" if r.gating else "adv "
        lines.append(f"[{icon[r.status]}] {gate} {r.pid:<16} {r.title}")
        lines.append(f"           └─ {r.evidence}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verification-first release gate.")
    parser.add_argument(
        "--deep", action="store_true", help="Run heavy clean-room probes (wheel build/install)."
    )
    parser.add_argument(
        "--json", default=None, help="Write machine-readable scorecard to this path."
    )
    args = parser.parse_args(argv)

    results = evaluate(args.deep)
    print(render(results))

    gating = [r for r in results if r.gating]
    green = [r for r in gating if r.status == GREEN]
    red = [r for r in gating if r.status == RED]
    manual = [r for r in gating if r.status == MANUAL]
    verdict = GREEN if not red and not manual else RED

    print("=" * 64)
    print(
        f"Gating: {len(green)} GREEN / {len(red)} RED / {len(manual)} MANUAL "
        f"of {len(gating)} — VERDICT: {verdict}"
    )
    if verdict == RED:
        print(
            "Per the absolute rule, any RED or unresolved MANUAL gating item "
            "makes the whole release RED. No 'almost ready'."
        )

    if args.json:
        payload = {
            "verdict": verdict,
            "counts": {
                "green": len(green),
                "red": len(red),
                "manual": len(manual),
                "gating_total": len(gating),
            },
            "results": [asdict(r) for r in results],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return 0 if verdict == GREEN else 1


if __name__ == "__main__":
    raise SystemExit(main())
