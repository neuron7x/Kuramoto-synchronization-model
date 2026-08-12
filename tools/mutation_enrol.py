#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Deterministic mutation-enrolment cycle — automate the loop, trace where coverage is thin.

The completeness axis of the ten-axis gate (docs/audit/TEN_AXES_COMPOSITION_2026-07-22.md) is
bound by how many runtime modules carry a *verified* logic-mutation kill-rate in
docs/MUTATION_KILL_BASELINE.json. Growing that set is a fixed loop, run by hand eight times
this month:

    pair each unenrolled module with the ONE test that directly imports it  (discover)
    probe each pair serially -- the probe rewrites the source in place, so
      concurrency corrupts the tree; each run restores the file before the next  (probe)
    classify: CLEAN (100%) / GAP (survivors) / NO_LOGIC (0 sites) / TIMEOUT / ERROR  (trace)
    enrol the CLEAN ones; refuse NO_LOGIC (kill-rate 1.0 on zero sites is not evidence)  (enrol)

This tool is that loop as a deterministic mechanism. It reads only committed state, restores
the tree after every probe, and never enrols a module whose numbers it did not just measure.

Subcommands
-----------
    discover  [--limit N] [--max-sites M] [--roots r,...]   -> emit module|test pairs (JSON)
    probe     --pairs pairs.json [--timeout S] [--json out]  -> probe each, emit a trace report
    enrol     --report report.json [--apply]                 -> add CLEAN modules to the ledger

Discovery, probing and enrolment are separate so a human reviews the trace between measuring
and writing -- the probe never mutates the ledger.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "CODE_QUALITY_MANIFEST.json"
LEDGER = ROOT / "docs" / "MUTATION_KILL_BASELINE.json"
PROBE = ROOT / "tools" / "mutation_probe.py"


# --------------------------------------------------------------------------- shared


def _runtime_roots() -> list[str]:
    return list(json.loads(MANIFEST.read_text(encoding="utf-8"))["runtime_roots"])


def _ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _enrolled() -> set[str]:
    return set(_ledger()["modules"])


def _imports(path: Path) -> set[str]:
    """Every dotted module name imported by ``path`` (import + from-import)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _directly_imports(test_rel: str, module_rel: str) -> bool:
    """True iff the test file imports the module DIRECTLY (not merely an ancestor package).

    Crediting an ancestor import (``from core import x`` vouching for every ``core.*`` module)
    is the exact false-credit the ten-axis gate's mutation probe refuses; the pairing must use
    the same rule so a probed pair is one the ledger will actually credit.
    """
    dotted = module_rel[:-3].replace("/", ".") if module_rel.endswith(".py") else module_rel
    return any(
        name == dotted or name.startswith(dotted + ".") for name in _imports(ROOT / test_rel)
    )


def _logic_sites(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return 0
    sites = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sites += len(node.ops)
        elif isinstance(node, ast.BoolOp):
            sites += len(node.values) - 1
    return sites


# --------------------------------------------------------------------------- discover


def discover(limit: int, max_sites: int, roots: list[str]) -> list[dict]:
    """Emit unenrolled runtime modules paired 1:1 with the single test that imports them.

    Only unambiguous pairs (exactly one importing test) are returned -- an ambiguous pairing is
    a judgement call the tool must not silently make. Modules with more than ``max_sites`` logic
    sites are skipped to keep a batch's wall-clock bounded (probe time grows with sites).
    """
    enrolled = _enrolled()
    modules: list[str] = []
    for root in roots:
        base = ROOT / root
        if not base.is_dir():
            continue
        modules.extend(
            p.relative_to(ROOT).as_posix()
            for p in sorted(base.rglob("*.py"))
            if "__pycache__" not in p.parts
        )
    tests = [
        p.relative_to(ROOT).as_posix()
        for p in sorted((ROOT / "tests").rglob("test_*.py"))
        if "__pycache__" not in p.parts
    ]
    test_imports = {t: _imports(ROOT / t) for t in tests}

    pairs: list[dict] = []
    for module in modules:
        if module in enrolled:
            continue
        dotted = module[:-3].replace("/", ".")
        importers = [
            t
            for t, names in test_imports.items()
            if any(n == dotted or n.startswith(dotted + ".") for n in names)
        ]
        if len(importers) != 1:
            continue
        sites = _logic_sites(ROOT / module)
        if sites < 1 or sites > max_sites:
            continue
        pairs.append({"module": module, "test": importers[0], "logic_sites": sites})
    pairs.sort(key=lambda p: p["logic_sites"])
    return pairs[:limit] if limit > 0 else pairs


# --------------------------------------------------------------------------- probe


@dataclass
class ProbeResult:
    module: str
    test: str
    killed: int = 0
    total: int = 0
    survivors: list[dict] = field(default_factory=list)
    classification: str = "ERROR"
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "module": self.module,
            "test": self.test,
            "killed": self.killed,
            "total": self.total,
            "classification": self.classification,
            "survivors": self.survivors,
            "detail": self.detail,
        }


def _tree_dirty(module: str, cwd: Path) -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--", module],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return bool(out.stdout.strip())


def _restore(module: str, cwd: Path) -> None:
    # The probe rewrites the source in place; restore it before the next pair so a crash mid-run
    # can never leave a mutated module staged into a later measurement.
    subprocess.run(["git", "checkout", "--", module], cwd=cwd, capture_output=True, text=True)


def probe_one(
    module: str, test: str, timeout: int, out_dir: Path, worktree: Path = ROOT
) -> ProbeResult:
    """Probe one pair inside ``worktree`` (defaults to the main checkout).

    Isolation: mutation_probe.py resolves its ROOT from its own __file__, so invoking the
    worktree's OWN copy operates on the worktree's files -- N worktrees each mutate a private
    checkout, which is what lets probes run in parallel without corrupting each other (the
    in-place rewrite that forbids concurrency on a single tree).
    """
    result = ProbeResult(module=module, test=test)
    if not (worktree / module).exists():
        result.detail = "module missing"
        return result
    json_out = out_dir / (module.replace("/", "_") + ".json")
    probe_script = worktree / "tools" / "mutation_probe.py"
    try:
        run = subprocess.run(
            [
                sys.executable,
                str(probe_script),
                module,
                "--tests",
                test,
                "--only-logic",
                "--json",
                str(json_out),
            ],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if _tree_dirty(module, worktree):
            _restore(module, worktree)
        result.classification = "TIMEOUT"
        result.detail = f"probe exceeded {timeout}s"
        return result
    finally:
        if _tree_dirty(module, worktree):
            _restore(module, worktree)

    if not json_out.exists():
        result.classification = "ERROR"
        result.detail = (
            (run.stderr or run.stdout or "no probe json").strip().splitlines()[-1:][0]
            if (run.stderr or run.stdout)
            else "no probe json"
        )
        return result
    data = json.loads(json_out.read_text(encoding="utf-8"))
    result.killed = int(data["killed"])
    result.total = int(data["total"])
    result.survivors = list(data.get("survivors", []))
    if result.total == 0:
        result.classification = "NO_LOGIC"
        result.detail = "zero logic sites; kill-rate 1.0 is vacuous -- do not enrol"
    elif result.killed == result.total:
        result.classification = "CLEAN"
    else:
        result.classification = "GAP"
        result.detail = f"{result.total - result.killed} survivor(s)"
    return result


def _report(results: list[ProbeResult]) -> dict:
    by_class: dict[str, int] = {}
    for r in results:
        by_class[r.classification] = by_class.get(r.classification, 0) + 1
    return {
        "schema": "mutation-enrol-trace/1",
        "summary": by_class,
        "results": [r.as_dict() for r in sorted(results, key=lambda x: x.module)],
    }


def _add_worktree(base: Path, index: int) -> Path:
    """A detached worktree at HEAD; probes there mutate a private checkout."""
    path = base / f"wt{index}"
    subprocess.run(
        ["git", "worktree", "add", "--detach", "--quiet", str(path), "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return path


def _remove_worktree(path: Path) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def probe(pairs: list[dict], timeout: int, out_dir: Path, jobs: int = 1) -> dict:
    if _dirty_worktree():
        raise SystemExit(
            "REFUSED: working tree is dirty; probe requires a clean tree to restore to"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if jobs <= 1 or len(pairs) <= 1:
        results = [probe_one(p["module"], p["test"], timeout, out_dir) for p in pairs]
        return _report(results)
    return _probe_parallel(pairs, timeout, out_dir, jobs)


def _probe_parallel(pairs: list[dict], timeout: int, out_dir: Path, jobs: int) -> dict:
    """Fan the pairs across ``jobs`` git worktrees -- each is an isolated checkout, so probes
    mutate private files and never corrupt one another. Worktrees are always torn down."""
    import concurrent.futures
    import tempfile

    jobs = min(jobs, len(pairs))
    base = Path(tempfile.mkdtemp(prefix="mut-enrol-wt-", dir=out_dir))
    worktrees: list[Path] = []
    results: list[ProbeResult] = []
    try:
        worktrees = [_add_worktree(base, i) for i in range(jobs)]

        def _run_lane(lane: int) -> list[ProbeResult]:
            wt = worktrees[lane]
            out: list[ProbeResult] = []
            for pair in pairs[lane::jobs]:  # round-robin -> even lane lengths
                out.append(probe_one(pair["module"], pair["test"], timeout, out_dir, worktree=wt))
            return out

        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            for lane_results in pool.map(_run_lane, range(jobs)):
                results.extend(lane_results)
    finally:
        for wt in worktrees:
            _remove_worktree(wt)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True, text=True)
        try:
            base.rmdir()
        except OSError:
            pass
    return _report(results)


def _dirty_worktree() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return bool(out.stdout.strip())


# --------------------------------------------------------------------------- enrol


def enrol(report: dict, apply: bool) -> dict:
    """Add every CLEAN result to the ledger at floor 1.0. NO_LOGIC/GAP are never enrolled.

    Refusing NO_LOGIC is the load-bearing rule: a module with zero logic sites probes at
    kill-rate 1.0, which is not evidence -- enrolling it would buy free completeness credit,
    the exact thing the ratchet's zero-site guard rejects.
    """
    ledger = _ledger()
    added, skipped = [], []
    for r in report["results"]:
        if r["classification"] != "CLEAN":
            skipped.append((r["module"], r["classification"]))
            continue
        if r["module"] in ledger["modules"]:
            skipped.append((r["module"], "already-enrolled"))
            continue
        ledger["modules"][r["module"]] = {
            "floor": 1.0,
            "killed": r["killed"],
            "total": r["total"],
            "tests": r["test"],
        }
        added.append(r["module"])
    if apply and added:
        ledger["modules"] = dict(sorted(ledger["modules"].items()))
        LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"added": sorted(added), "skipped": skipped, "applied": bool(apply and added)}


# --------------------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="emit 1:1 module|test pairs for unenrolled runtime modules")
    d.add_argument("--limit", type=int, default=10)
    d.add_argument("--max-sites", type=int, default=16)
    d.add_argument("--roots", default="")

    p = sub.add_parser("probe", help="probe each pair (serial, or --jobs N via worktrees)")
    p.add_argument("--pairs", required=True)
    p.add_argument("--timeout", type=int, default=480)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--json", dest="json_out", default=None)
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="parallel probes across N isolated git worktrees (1 = serial on the main tree)",
    )

    e = sub.add_parser("enrol", help="add CLEAN results to the ledger (--apply to write)")
    e.add_argument("--report", required=True)
    e.add_argument("--apply", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "discover":
        roots = [r.strip() for r in args.roots.split(",") if r.strip()] or _runtime_roots()
        pairs = discover(args.limit, args.max_sites, roots)
        sys.stdout.write(json.dumps(pairs, indent=2) + "\n")
        return 0

    if args.cmd == "probe":
        pairs = json.loads(Path(args.pairs).read_text(encoding="utf-8"))
        out_dir = Path(args.out_dir) if args.out_dir else ROOT / "artifacts" / "mutation_enrol"
        report = probe(pairs, args.timeout, out_dir, jobs=args.jobs)
        text = json.dumps(report, indent=2) + "\n"
        if args.json_out:
            Path(args.json_out).write_text(text, encoding="utf-8")
        sys.stdout.write(text)
        for r in report["results"]:
            sys.stderr.write(
                f"  {r['classification']:<9} {r['module']} {r['killed']}/{r['total']}\n"
            )
        return 0

    if args.cmd == "enrol":
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        outcome = enrol(report, args.apply)
        sys.stdout.write(json.dumps(outcome, indent=2) + "\n")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
