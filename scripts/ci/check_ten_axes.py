#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Composition gate: score the repository on the ten quality axes, fail closed on regression.

First principle (a doctrine that is not measured is not held): GeoSync enforces dozens of
independent ratchets, but nothing composed them into a single statement of *how the whole
artifact stands*. This gate does exactly that -- and only that. It runs no new analysis and
invents no numbers.

Ten axes: elegance, aesthetics, beauty, simplicity, precision, adaptability, resistance,
coherence, completeness, reproducibility.

RULES OF CONSTRUCTION (these are what make the profile admissible, not decorative):

1. Every probe is ``score = 1 - debt / population``. ``debt`` comes from a FROZEN ratchet
   ledger already enforced by its own gate; ``population`` is MEASURED here from repository
   bytes (AST walk / file walk). No probe accepts a hand-assigned rating.
2. A probe whose population cannot be measured reports state ``UNMEASURED`` and contributes
   NOTHING to its axis -- it is never floored to 1.0. An axis with zero measured probes is
   reported ``UNMEASURED``, not scored. (See geosync/proof/weighting.py for the same rule
   applied to falsification power.)
3. Aggregation is WEAKEST-LINK at both levels: an axis scores as its worst measured probe,
   and the repository verdict is its worst axis. A mean would let a cheap high-scoring probe
   dilute a real hole, and would reward adding easy probes -- so the mean is reported only as
   ``mean_informational`` and is never the verdict.
4. **A score may only rise because the debt fell.** This is the load-bearing rule. A ratio is
   far too easy to move without improving anything -- add documents, add files, widen a scan
   and the denominator grows for free -- so what is frozen is the whole probe (score, debt,
   axis, stated procedure), and ``compare()`` fails closed on ten classes including
   ``DEBT INCREASE`` and ``POPULATION INFLATION``.
5. Populations are never hand-picked. Ledger discovery is repo-wide over tracked PATHS (the
   canonical waiver store is a directory named ``waivers/`` whose filenames carry no marker at
   all), the ledger/not-ledger classification -- including the prefix map -- is
   complete-by-construction AND frozen in the baseline, and whether a ledger grants an exception
   is decided generically over its contents rather than by a hand-named key. Whoever chooses the
   sample, or the key, chooses the answer.
6. Nothing is credited that does not VERIFY HERE. A mutation-ratchet enrolment earns credit only
   if its named tests exist, contain test functions and DIRECTLY import the module they claim to
   cover; an invariant counts as witnessed only if its witness contains a test function that
   directly imports the invariant's own declared ``source``. Ancestor-package imports are not
   credit: one ``from core import x`` once vouched for every module under ``core/``.

DECLARED BOUNDARY (this gate cannot close it, so it says so): no static check can prove that a
mutation run actually happened. ``docs/MUTATION_KILL_BASELINE.json`` states killed/total, and
``check_mutation_kill_ratchet.py`` re-probes a module only when that module or its tests CHANGE,
so a newly added entry for an untouched module is never probed. The control here is visibility,
not proof: the enrolment SET is frozen in the baseline, so fabricating enrolments appears as
that many lines in the diff and requires a deliberate re-freeze. Treat ``mutation_calibration``
as measuring ENROLMENT, not measured strength.

The gate deliberately does NOT invent a passing threshold. There is no defensible absolute
line at which ``aesthetics >= 0.7`` becomes "good"; there IS a defensible statement that a
measured axis must never move down. Monotonicity is the contract, enforced against the working
baseline and -- with ``--against-ref``, which CI points at the default branch -- against the
baseline as COMMITTED there, so the bar cannot be lowered by deleting the baseline and
re-freezing, nor by choosing a favourable comparison point.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "TEN_AXES_BASELINE.json"

AXES = (
    "elegance",
    "aesthetics",
    "beauty",
    "simplicity",
    "precision",
    "adaptability",
    "resistance",
    "coherence",
    "completeness",
    "reproducibility",
)

# Ratchet ledgers surveyed by the `beauty` axis (special-case density). Each is a frozen
# waiver/debt file enforced by its own gate; an EMPTY one means that gate needs no exceptions.
#
# The classification below is COMPLETE BY CONSTRUCTION, in the same spirit as
# docs/CODE_QUALITY_MANIFEST.json's runtime/excluded split: `_survey_ledgers()` walks every
# candidate file and raises if one is in neither map. A hand-picked sample would let the
# beauty score be set by *which* ledgers were listed -- an adversary (or an optimist) could
# omit the waiver-free ones and depress the axis, or omit the loaded ones and inflate it.
LEDGERS: tuple[str, ...] = (
    ".claude/audit/false_confidence_exemptions.yaml",
    ".github/assertion_free_tests_baseline.json",
    ".github/bwheel_baseline.json",
    ".github/claim_boundary_allow.json",
    ".github/descriptor_promotion_allow.json",
    ".github/detect-secrets.baseline",
    ".github/doc_commands_baseline.json",
    ".github/docs_consistency_allow.json",
    ".github/falsifier_node_allowlist.json",
    ".github/gate_run_baseline.json",
    ".github/golden_path_allowlist.json",
    ".github/golden_path_baseline.json",
    ".github/import_architecture_baseline.json",
    ".github/neuro_claim_boundary_allow.json",
    ".github/package_boundary_baseline.json",
    ".github/rtm_traceability_allowlist.json",
    ".github/security_regression_allowlist.json",
    ".github/silent_procedures_baseline.json",
    "configs/quality/brand_allowlist.toml",
    "configs/security/allowlist.yaml",
    "docs/SKIP_RATCHET_BASELINE.json",
    "docs/link_allowlist.json",
    "governance/waivers/EXAMPLE-P1-flaky-latency-probe.yaml",
    "research/flagship/quarantine.yaml",
    "tests/ci/fast_quarantine.txt",
    "tests/fixtures/coverage_surface_allowlist.json",
    "tools/debt_budget.json",
    "tools/security/forbidden_torch_jit_allowlist.json",
)

# Candidate files that are NOT standing waiver ledgers. Each needs a reason; the survey fails
# on any candidate in neither map, and the whole classification is frozen in the baseline, so
# quietly reclassifying a loaded ledger out of the denominator is itself a regression.
NOT_LEDGERS: dict[str, str] = {
    ".github/invariant_teeth_baseline.json": "a frozen floor (a number to beat), not a waiver set",
    "benchmarks/flagship_baselines/comparison_report.json": "generated benchmark report",
    "benchmarks/flagship_baselines/hierarchy.yaml": "benchmark reference hierarchy, not permissions",
    "configs/nightly/baselines.json": "performance reference values, not permissions",
    "configs/quality/coverage_baseline.json": "a coverage floor to beat, not a waiver set",
    "docs/CODE_DEBT_BASELINE.json": "debt ledger measured directly by the elegance/simplicity/"
    "resistance/reproducibility probes; counting it here too would double-count",
    "docs/MUTATION_KILL_BASELINE.json": "a kill-rate floor to beat, and the completeness probe's "
    "own debt source",
    "docs/TEN_AXES_BASELINE.json": "this gate's own frozen profile",
    "tests/performance/benchmark_baselines.json": "performance reference values, not permissions",
}

# Whole trees that cannot contain a standing waiver ledger. A prefix rule rather than dozens of
# per-file entries, but still a REVIEWED exclusion: each carries a reason, and the prefix map
# itself is frozen in the baseline (it is applied BEFORE classification, so an added prefix
# would otherwise remove a whole tree from discovery with nothing recording it).
NOT_LEDGER_PREFIXES: dict[str, str] = {
    ".claude/commit_acceptors/": "per-commit acceptance records (id/status/promise/falsifier), "
    "not standing permissions -- they are consumed once and never paid down",
    ".github/workflows/": "workflow definitions, not ledgers",
    "artifacts/": "generated run outputs",
    "data/": "dataset artifacts and lineage records",
    "reports/": "generated run outputs",
    "schemas/": "schema definitions, not instances",
}

# Keys that DESCRIBE a ledger rather than granting an exception -- but only when they carry a
# scalar. A `reason:` holding a nested object is structure, not prose, and counting it as
# metadata scored a live waiver ledger (tests/fixtures/coverage_surface_allowlist.json, which
# excludes a whole package from the release-coverage denominator) as waiver-free.
_LEDGER_METADATA_KEYS = frozenset(
    {
        "_comment",
        "_doc",
        "$schema-note",
        "comment",
        "documented_at",
        "generated_at",
        "generated_by",
        "measured_by",
        "note",
        "notes",
        "rationale",
        "reason",
        "scan_root",
        "schema_version",
        "target",
        "task",
        "tool",
        "version",
    }
)

# Filename markers and suffixes that make a tracked file a ledger CANDIDATE. Widened after a
# review found four enforced waiver ledgers invisible to a narrower filter, including a plain
# `.txt` quarantine list consumed by the fast-shard workflow.
_LEDGER_MARKERS = (
    "allow",
    "grandfather",
    "known",
    "override",
    "permit",
    "suppress",
    "whitelist",
    "baseline",
    "debt",
    "exception",
    "exclude",
    "exclusion",
    "exempt",
    "ignorelist",
    "quarantine",
    "waiver",
)
_LEDGER_SUFFIXES = (".json", ".yaml", ".yml", ".toml", ".baseline", ".txt")


class ProbeError(RuntimeError):
    """Raised by a probe that cannot measure its population -- yields UNMEASURED, not 1.0."""


@dataclass
class Probe:
    id: str
    axis: str
    procedure: str
    fn: Callable[[], tuple[int, int]]
    debt: int | None = None
    population: int | None = None
    state: str = "UNMEASURED"
    reason: str = ""

    def run(self) -> None:
        # Reset FIRST. Probes are module-level singletons; without this a probe that measured
        # once and then went blind would keep reporting its stale MEASURED numbers, and the
        # MEASURED -> UNMEASURED regression class would silently fail open.
        self.debt = self.population = None
        self.state, self.reason = "UNMEASURED", ""
        try:
            debt, population = self.fn()
        except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
            self.reason = f"{type(exc).__name__}: {exc}"
            return
        if population <= 0:
            self.reason = "population is zero -- ratio undefined"
            return
        if debt < 0 or debt > population:
            self.reason = f"debt {debt} outside population {population}"
            return
        self.debt, self.population, self.state = debt, population, "MEASURED"

    @property
    def score(self) -> float | None:
        if self.state != "MEASURED":
            return None
        assert self.debt is not None and self.population is not None
        return round(1.0 - self.debt / self.population, 6)


# --------------------------------------------------------------------------- sources


def _json(rel: str) -> dict:
    path = ROOT / rel
    if not path.exists():
        raise ProbeError(f"ledger missing: {rel}")
    return json.loads(path.read_text(encoding="utf-8"))


def _ledger_count(rel: str, keys: str) -> int:
    """Sum the sized entries named by ``keys`` (``a+b``) in a frozen ledger."""
    data = _json(rel)
    total = 0
    for key in keys.split("+"):
        if key not in data:
            raise ProbeError(f"{rel}: key {key!r} absent")
        value = data[key]
        total += len(value) if isinstance(value, (list, dict, set)) else int(value)
    return total


def _runtime_roots() -> list[str]:
    roots = _json("docs/CODE_QUALITY_MANIFEST.json").get("runtime_roots")
    if not isinstance(roots, list) or not roots:
        raise ProbeError("CODE_QUALITY_MANIFEST.json: runtime_roots absent or empty")
    return [str(r) for r in roots]


def _runtime_files() -> list[Path]:
    files: list[Path] = []
    for root in _runtime_roots():
        base = ROOT / root
        if not base.is_dir():
            raise ProbeError(f"runtime root missing on disk: {root}")
        files.extend(p for p in sorted(base.rglob("*.py")) if "__pycache__" not in p.parts)
    if not files:
        raise ProbeError("no runtime .py files found")
    return files


def _trees(files: list[Path]) -> list[tuple[Path, ast.Module]]:
    out: list[tuple[Path, ast.Module]] = []
    for path in files:
        try:
            out.append((path, ast.parse(path.read_text(encoding="utf-8"))))
        except (SyntaxError, UnicodeDecodeError):
            continue  # unparseable files are their own tracked debt class
    if not out:
        raise ProbeError("no runtime file parsed")
    return out


def _test_files() -> list[Path]:
    base = ROOT / "tests"
    if not base.is_dir():
        raise ProbeError("tests/ absent")
    return [p for p in sorted(base.rglob("test_*.py")) if "__pycache__" not in p.parts]


def _symbol_debt_union() -> int:
    debt = _json("docs/CODE_DEBT_BASELINE.json").get("symbol_debt")
    if not isinstance(debt, dict):
        raise ProbeError("CODE_DEBT_BASELINE.json: symbol_debt absent")
    union: set[str] = set()
    for key in ("god_function", "god_class", "complexity"):
        entries = debt.get(key)
        if not isinstance(entries, list):
            raise ProbeError(f"symbol_debt.{key} absent")
        union.update(str(e) for e in entries)
    return len(union)


def _file_count_debt(key: str) -> int:
    debt = _json("docs/CODE_DEBT_BASELINE.json").get("file_count_debt")
    if not isinstance(debt, dict) or key not in debt:
        raise ProbeError(f"file_count_debt.{key} absent")
    value = debt[key]
    return len(value) if isinstance(value, (list, dict)) else int(value)


# ---------------------------------------------------------------------------- probes


def _test_functions(rel: str) -> int:
    """Count ``def test_*`` in a declared witness file. A file with none is not a test."""
    path = ROOT / rel
    if not path.exists():
        return 0
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _imported_modules(rel: str) -> set[str]:
    path = ROOT / rel
    if not path.exists():
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def _test_exercises_module(test_rel: str, module_rel: str) -> bool:
    """True iff ``test_rel`` imports ``module_rel``. Naming a test is not binding to it."""
    # DIRECT imports only. Crediting an ancestor package (``dotted.startswith(name + ".")``)
    # meant one ``from core import x`` vouched for every module under core/ -- 379 of 583
    # spurious credits came from that single clause.
    dotted = module_rel[:-3].replace("/", ".") if module_rel.endswith(".py") else module_rel
    return any(
        name == dotted or name.startswith(dotted + ".") for name in _imported_modules(test_rel)
    )


def _p_symbol_budget() -> tuple[int, int]:
    symbols = sum(
        1
        for _, tree in _trees(_runtime_files())
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    return _symbol_debt_union(), symbols


def _p_docstrings() -> tuple[int, int]:
    """Public runtime symbols (module/class/def not starting with ``_``) lacking a docstring."""
    total = missing = 0
    for path, tree in _trees(_runtime_files()):
        if not path.name.startswith("_"):
            total += 1
            missing += ast.get_docstring(tree) is None
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_"):
                continue
            total += 1
            missing += ast.get_docstring(node) is None
    return missing, total


def _ledger_candidates() -> set[str]:
    """Every TRACKED file whose name marks it as a waiver/allow/baseline ledger, repo-wide.

    Discovery is by NAME across all tracked files, not by a hard-coded directory glob. A glob
    over ``.github/*.json`` + ``docs/*BASELINE*.json`` missed real waiver ledgers living in
    ``.claude/commit_acceptors/``, ``configs/quality/`` and ``.github/detect-secrets.baseline``,
    and a new one could be introduced simply by choosing a different directory or extension.
    """
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, text=True, cwd=ROOT, timeout=60
    )
    if result.returncode != 0:
        raise ProbeError("git ls-files failed -- cannot enumerate ledger candidates")
    candidates: set[str] = set()
    for rel in result.stdout.split("\0"):
        if not rel or any(rel.startswith(prefix) for prefix in NOT_LEDGER_PREFIXES):
            continue
        lowered = rel.lower()
        if not lowered.endswith(_LEDGER_SUFFIXES):
            continue
        # Markers are matched against the WHOLE path, not the basename: the repository's
        # canonical waiver store is `governance/waivers/*.yaml`, whose filenames carry no
        # marker at all -- the word is in the directory.
        if any(marker in lowered for marker in _LEDGER_MARKERS):
            candidates.add(rel)
    if not candidates:
        raise ProbeError("no ledger candidates found -- discovery is broken, not the repo clean")
    return candidates


def _survey_ledgers() -> tuple[tuple[str, str], ...]:
    """Assert the ledger classification is complete, then return the surveyed set.

    Every candidate waiver/baseline file must be in LEDGERS or NOT_LEDGERS. An unclassified
    candidate raises -- so the beauty score can never be set by *choosing* which ledgers to
    look at, which is the one way a density metric like this is trivially gamed.
    """
    candidates = _ledger_candidates()
    known = set(LEDGERS) | set(NOT_LEDGERS)
    unclassified = sorted(candidates - known)
    if unclassified:
        raise ProbeError(
            "unclassified waiver-ledger candidates (add to LEDGERS or NOT_LEDGERS): "
            + ", ".join(unclassified)
        )
    stale = sorted(rel for rel in known if rel not in candidates)
    if stale:
        raise ProbeError(f"classified ledger no longer discovered: {', '.join(stale)}")
    return LEDGERS


def _ledger_is_loaded(rel: str) -> bool:
    """True iff the ledger grants at least one exception.

    Entry detection is GENERIC -- every non-metadata value is counted -- rather than reading a
    hand-named debt key per file. Naming the key per ledger reintroduced cherry-picking one
    level down: whoever chose the key chose the answer.
    """
    path = ROOT / rel
    if not path.exists():
        raise ProbeError(f"ledger missing: {rel}")
    text = path.read_text(encoding="utf-8")
    data: object
    if path.suffix in (".json", ".baseline"):
        data = json.loads(text)
    elif path.suffix in (".yaml", ".yml"):
        import yaml

        data = yaml.safe_load(text)
    elif path.suffix == ".toml":
        import tomllib

        data = tomllib.loads(text)
    elif path.suffix == ".txt":
        return any(line.strip() and not line.lstrip().startswith("#") for line in text.splitlines())
    else:
        raise ProbeError(f"{rel}: unsupported ledger format {path.suffix!r}")

    def entries(obj: object) -> int:
        if isinstance(obj, dict):
            total = 0
            for key, value in obj.items():
                if key in _LEDGER_METADATA_KEYS and not isinstance(value, (dict, list)):
                    continue
                nested = entries(value)
                # A key whose value is a non-empty container of nothing but metadata is still
                # ONE granted exception -- `{"geosync_research": {"reason": ..., "note": ...}}`
                # excludes a package, and counting only the leaves scored it waiver-free.
                total += nested if nested else int(bool(value))
            return total
        if isinstance(obj, list):
            return len(obj)
        if isinstance(obj, bool):
            return int(obj)
        if isinstance(obj, (int, float)):
            return int(obj > 0)
        if isinstance(obj, str):
            return int(bool(obj.strip()))
        return 0

    return entries(data) > 0


def _p_waiver_free_gates() -> tuple[int, int]:
    """Waiver ledgers that still grant at least one exception."""
    ledgers = _survey_ledgers()
    return sum(_ledger_is_loaded(rel) for rel in ledgers), len(ledgers)


def _p_file_budget() -> tuple[int, int]:
    debt = _json("docs/CODE_DEBT_BASELINE.json").get("symbol_debt", {})
    god = debt.get("god_file")
    if not isinstance(god, list):
        raise ProbeError("symbol_debt.god_file absent")
    return len(god), len(_runtime_files())


def _p_package_boundary() -> tuple[int, int]:
    """Packages shipped outside the canonical ``geosync`` namespace, vs all shipped packages.

    The two sets OVERLAP (``core``, ``execution``, ``application`` are both declared runtime
    roots and non-geosync wheel packages), so the population is their union -- adding them
    would double-count the overlap and flatter the score.
    """
    data = _json(".github/package_boundary_baseline.json")
    non_geosync = data.get("non_geosync_packages")
    if not isinstance(non_geosync, list):
        raise ProbeError("package_boundary_baseline.json: non_geosync_packages is not a list")
    population = {str(p) for p in non_geosync} | set(_runtime_roots())
    return len(non_geosync), len(population)


def _p_type_escapes() -> tuple[int, int]:
    """Annotations that decline to be precise (``Any``, ``type: ignore``) vs all annotations."""
    total = escapes = 0
    for path, tree in _trees(_runtime_files()):
        for node in ast.walk(tree):
            annotations: list[ast.expr] = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.returns is not None:
                    annotations.append(node.returns)
                args = node.args
                for arg in [
                    *args.posonlyargs,
                    *args.args,
                    *args.kwonlyargs,
                    args.vararg,
                    args.kwarg,
                ]:
                    if arg is not None and arg.annotation is not None:
                        annotations.append(arg.annotation)
            elif isinstance(node, ast.AnnAssign):
                annotations.append(node.annotation)
            for ann in annotations:
                total += 1
                escapes += any(
                    isinstance(sub, ast.Name)
                    and sub.id == "Any"
                    or isinstance(sub, ast.Attribute)
                    and sub.attr == "Any"
                    for sub in ast.walk(ann)
                )
        for line in path.read_text(encoding="utf-8").splitlines():
            if "type: ignore" in line:
                total += 1
                escapes += 1
    return escapes, total


def _p_import_architecture() -> tuple[int, int]:
    violators = _ledger_count(".github/import_architecture_baseline.json", "src_imports+path_hacks")
    return violators, len(_runtime_files())


def _p_broad_except() -> tuple[int, int]:
    return _file_count_debt("broad_except"), len(_runtime_files())


def _p_silent_procedures() -> tuple[int, int]:
    """Silent ``-> None`` procedures vs every ``-> None`` procedure in the runtime roots."""
    procedures = 0
    for _, tree in _trees(_runtime_files()):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            returns = node.returns
            if isinstance(returns, ast.Constant) and returns.value is None:
                procedures += 1
    return _ledger_count(".github/silent_procedures_baseline.json", "silent"), procedures


def _p_rtm_direct() -> tuple[int, int]:
    """RTM requirements traced only indirectly (allowlisted) vs all RTM requirements.

    The row filter is the generic ``XXX-nnn`` requirement-id shape, not a hard-coded list of
    prefixes: the matrix carries SEC- rows alongside REQ-/NFR-, and naming three prefixes by
    hand silently truncated the population to 8 of 13.
    """
    import re

    rtm = ROOT / "docs" / "requirements" / "traceability_matrix.md"
    if not rtm.exists():
        raise ProbeError("docs/requirements/traceability_matrix.md absent")
    row = re.compile(r"^\|\s*`?([A-Z]{2,5}-\d{2,4})`?\s*\|")
    requirements = {
        match.group(1)
        for line in rtm.read_text(encoding="utf-8").splitlines()
        if (match := row.match(line.strip()))
    }
    return _ledger_count(".github/rtm_traceability_allowlist.json", "allow"), len(requirements)


def _p_golden_paths() -> tuple[int, int]:
    """Documented make targets that do not exist, vs every make target cited in docs/.

    The citation population is taken from check_golden_paths.py's own extractor, which counts
    only CODE contexts (inline backticks or fenced blocks). Re-implementing it here with a bare
    ``\\bmake\\s+`` regex counted English prose ("make targets", "make the"), so any document
    that merely used the word inflated the denominator and raised the score for free.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_golden_paths", ROOT / "scripts" / "ci" / "check_golden_paths.py"
    )
    if spec is None or spec.loader is None:
        raise ProbeError("cannot load scripts/ci/check_golden_paths.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, _, checked = module._dangling()
    return _ledger_count(".github/golden_path_baseline.json", "known_dangling"), checked


def _p_gate_health() -> tuple[int, int]:
    """Known-red gates vs every gate script in scripts/ci/."""
    gates = [
        p
        for p in sorted((ROOT / "scripts" / "ci").glob("check_*.py"))
        if "__pycache__" not in p.parts
    ]
    return _ledger_count(".github/gate_run_baseline.json", "known_red"), len(gates)


def _p_invariant_witnesses() -> tuple[int, int]:
    """Declared invariants with NO witness test bound to them, vs all declared invariants.

    Deliberately NOT ``(total - bound_green_floor) / total``: that floor is a frozen integer,
    so declaring a new invariant would LOWER the score and redden the gate, while deleting
    invariants would raise it -- exactly backwards. Whether a bound witness currently passes is
    the business of ``scripts/ci/audit_invariant_teeth.py``, which runs them; this probe reads
    only what the registry itself states, which is cheap and cannot be inverted.
    """
    registry = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
    if not registry.exists():
        raise ProbeError(".claude/physics/INVARIANTS.yaml absent -- invariant population unknown")
    import yaml

    total = unbound = 0

    def walk(obj: object) -> None:
        nonlocal total, unbound
        if isinstance(obj, dict):
            if str(obj.get("id", "")).startswith("INV"):
                total += 1
                tests = obj.get("tests")
                if isinstance(tests, str):
                    tests = [tests] if tests.strip() else []
                if not isinstance(tests, list):
                    tests = []
                # A witness must be a TEST *of this invariant's own subject*. Three successively
                # weaker versions of this check were each defeated by a text edit: requiring
                # only that the path exist (`tests/does_not_exist.py`), then that the file hold
                # a test function (`tests/conftest.py` blocked, any unrelated test file fine).
                # So the witness must directly import the invariant's declared ``source``
                # module -- 53 of the 54 real bindings satisfy this unchanged, and pointing all
                # 132 invariants at an arbitrary test now binds none of them.
                sources = obj.get("source")
                sources = [sources] if isinstance(sources, str) else (sources or [])
                sources = [
                    str(x).split("::", 1)[0].strip()
                    for x in sources
                    if str(x).split("::", 1)[0].strip().endswith(".py")
                ]
                bound = [
                    t
                    for t in tests
                    if t
                    and _test_functions(str(t).split("::", 1)[0].strip()) > 0
                    and any(
                        _test_exercises_module(str(t).split("::", 1)[0].strip(), src)
                        for src in sources
                    )
                ]
                unbound += not bound
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(yaml.safe_load(registry.read_text(encoding="utf-8")))
    return unbound, total


def _p_mutation_calibration() -> tuple[int, int]:
    """Runtime modules NOT enrolled in the enforced mutation-kill ratchet, vs ALL of them.

    The debt source is ``docs/MUTATION_KILL_BASELINE.json`` -- the ledger that
    ``scripts/ci/check_mutation_kill_ratchet.py`` RE-PROBES whenever an enrolled module or its
    tests change. It is deliberately NOT ``artifacts/test_strength/mutation.modules.json``,
    which no gate enforces: that file is a free-form measurement record, so writing 637 entries
    into it moved this verdict from 0.014 to 0.219 with the gate green. A number that anyone can
    write is not evidence, and this probe binds the whole repository verdict.

    Both sides are restricted to the declared runtime roots. Two traps live here and both were
    live in earlier drafts: scoring against the ledger's own membership yields 1.0 by
    construction, and crediting enrolled modules that lie OUTSIDE the runtime roots inflates the
    score with measurements of files the denominator never contained.
    """
    modules = _json("docs/MUTATION_KILL_BASELINE.json").get("modules")
    if not isinstance(modules, dict) or not modules:
        raise ProbeError("MUTATION_KILL_BASELINE.json: modules absent or empty")
    population = {p.relative_to(ROOT).as_posix() for p in _runtime_files()}
    calibrated: set[str] = set()
    for name, record in modules.items():
        if not isinstance(record, dict):
            raise ProbeError("MUTATION_KILL_BASELINE.json: module entry is not an object")
        key = str(name).lstrip("./")
        if key not in population or int(record.get("total", 0)) <= 0:
            continue
        # Enrolment is only credited when it VERIFIES here. The ratchet re-probes a module
        # only when that module or its tests change, so a newly added entry for an untouched
        # module is never probed -- writing {"total": 99, "killed": 99, "tests": "conftest.py"}
        # for every runtime file moved this verdict 30x with every gate in the repo green.
        tests = [t for t in str(record.get("tests", "")).split() if t]
        if not tests:
            continue
        if not all(_test_functions(t.split("::", 1)[0]) > 0 for t in tests):
            continue
        if not any(_test_exercises_module(t.split("::", 1)[0], key) for t in tests):
            continue
        calibrated.add(key)
    return len(population - calibrated), len(population)


def _p_assertion_bearing() -> tuple[int, int]:
    """Test functions with no recognised check, vs every test function under tests/."""
    total = 0
    for path in _test_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                total += 1
    return _ledger_count(".github/assertion_free_tests_baseline.json", "tests"), total


def _p_skip_free() -> tuple[int, int]:
    total = 0
    for path in _test_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test_"
            ):
                total += 1
    return _ledger_count("docs/SKIP_RATCHET_BASELINE.json", "skips"), total


def _p_ambient_nondeterminism() -> tuple[int, int]:
    return _file_count_debt("ambient_nondeterminism"), len(_runtime_files())


def _p_runtime_print() -> tuple[int, int]:
    return _file_count_debt("runtime_print"), len(_runtime_files())


PROBES: tuple[Probe, ...] = (
    Probe(
        "symbol_complexity_budget",
        "elegance",
        "1 - |god_function u god_class u complexity| / (runtime functions+classes, AST-counted)",
        _p_symbol_budget,
    ),
    Probe(
        "public_docstrings",
        "aesthetics",
        "1 - (public runtime modules/classes/defs without a docstring) / (all public runtime symbols)",
        _p_docstrings,
    ),
    Probe(
        "waiver_free_gates",
        "beauty",
        "1 - (waiver ledgers granting >=1 exception) / (ALL tracked waiver ledgers; discovery "
        "is repo-wide by filename, the classification is complete-by-construction and frozen)",
        _p_waiver_free_gates,
    ),
    Probe(
        "file_size_budget",
        "simplicity",
        "1 - |god_file| / (runtime .py files)",
        _p_file_budget,
    ),
    Probe(
        "namespace_singularity",
        "simplicity",
        "1 - (non-geosync packages in the wheel) / (UNION of those and the declared runtime "
        "roots -- the sets overlap)",
        _p_package_boundary,
    ),
    Probe(
        "type_escape_density",
        "precision",
        "1 - (annotations resolving to Any + `type: ignore` lines) / (all runtime annotations + those lines)",
        _p_type_escapes,
    ),
    Probe(
        "import_architecture",
        "adaptability",
        "1 - (src_imports + path_hacks violators) / (runtime .py files)",
        _p_import_architecture,
    ),
    Probe(
        "broad_except_density",
        "resistance",
        "1 - (files with a broad except) / (runtime .py files)",
        _p_broad_except,
    ),
    Probe(
        "silent_procedure_density",
        "resistance",
        "1 - (frozen silent procedures) / (all `-> None` procedures in runtime roots, AST-counted)",
        _p_silent_procedures,
    ),
    Probe(
        "rtm_direct_traceability",
        "coherence",
        "1 - (RTM requirements traced only indirectly) / (distinct XXX-nnn requirement ids in "
        "docs/requirements/traceability_matrix.md)",
        _p_rtm_direct,
    ),
    Probe(
        "golden_path_integrity",
        "coherence",
        "1 - (documented make targets that do not exist) / (make targets cited in a CODE "
        "context in docs/, counted by check_golden_paths.py's own extractor)",
        _p_golden_paths,
    ),
    Probe(
        "gate_health",
        "coherence",
        "1 - (known-red gates) / (check_*.py gate scripts)",
        _p_gate_health,
    ),
    Probe(
        "invariant_witness_binding",
        "completeness",
        "1 - (declared invariants with no witness file that CONTAINS a test function) / "
        "(invariants in .claude/physics/INVARIANTS.yaml)",
        _p_invariant_witnesses,
    ),
    Probe(
        "mutation_calibration",
        "completeness",
        "1 - (runtime-root modules whose mutation-ratchet enrolment in "
        "docs/MUTATION_KILL_BASELINE.json does not verify here) / (all runtime .py files)",
        _p_mutation_calibration,
    ),
    Probe(
        "assertion_bearing_tests",
        "completeness",
        "1 - (assertion-free test functions) / (all test functions under tests/)",
        _p_assertion_bearing,
    ),
    Probe(
        "skip_free_tests",
        "completeness",
        "1 - (skip/skipif/xfail markers) / (all test functions under tests/) -- markers are a LOWER bound on disabled tests",
        _p_skip_free,
    ),
    Probe(
        "ambient_determinism",
        "reproducibility",
        "1 - (files with ambient nondeterminism) / (runtime .py files)",
        _p_ambient_nondeterminism,
    ),
    Probe(
        "runtime_print_free",
        "reproducibility",
        "1 - (files printing at runtime) / (runtime .py files)",
        _p_runtime_print,
    ),
)


# --------------------------------------------------------------------------- report


def build_report() -> dict:
    probes: list[dict] = []
    for probe in PROBES:
        probe.run()
        entry = {
            "id": probe.id,
            "axis": probe.axis,
            "procedure": probe.procedure,
            "state": probe.state,
        }
        if probe.state == "MEASURED":
            entry.update({"debt": probe.debt, "population": probe.population, "score": probe.score})
        else:
            entry["reason"] = probe.reason
        probes.append(entry)

    axes: dict[str, dict] = {}
    for axis in AXES:
        mine = [p for p in probes if p["axis"] == axis]
        measured = [p for p in mine if p["state"] == "MEASURED"]
        if not measured:
            axes[axis] = {
                "state": "UNMEASURED",
                "probes": len(mine),
                "measured": 0,
                "note": "no probe measured -- axis is NOT scored (never floored to 1.0)",
            }
            continue
        axes[axis] = {
            "state": "MEASURED" if len(measured) == len(mine) else "PARTIAL",
            "probes": len(mine),
            "measured": len(measured),
            "score": min(p["score"] for p in measured),
            "binding_probe": min(measured, key=lambda p: p["score"])["id"],
            "mean_informational": round(sum(p["score"] for p in measured) / len(measured), 6),
        }

    scored = {a: v["score"] for a, v in axes.items() if "score" in v}
    unmeasured = sorted(a for a, v in axes.items() if "score" not in v)
    weakest = min(scored, key=lambda a: scored[a]) if scored else None
    return {
        "schema_version": "1.0",
        "_doc": (
            "Ten-axis composition profile. Every score is 1 - frozen_debt/measured_population; "
            "no rating is hand-assigned. Unmeasured probes contribute nothing and are never "
            "floored to 1.0. Aggregation is weakest-link at both levels: an axis scores as its "
            "worst measured probe, the repository as its worst axis."
        ),
        # Frozen so that reclassifying a loaded ledger as "not a ledger" -- which shrinks the
        # beauty denominator AND its debt, so neither the score nor the debt check objects --
        # is itself a fail-closed regression.
        # The enrolment SET is frozen so growth is never silent. Its numbers (killed/total)
        # are docs/MUTATION_KILL_BASELINE.json's own business -- no static gate can prove a
        # mutation run happened -- but adding 578 enrolments now shows up in this diff.
        "mutation_enrolments": sorted(
            (_json("docs/MUTATION_KILL_BASELINE.json").get("modules") or {}).keys()
        ),
        "ledger_classification": {
            "ledgers": sorted(LEDGERS),
            "not_ledgers": sorted(NOT_LEDGERS),
            # The prefix map is frozen too: it is applied BEFORE classification, so a new
            # prefix would silently remove a whole tree from discovery and nothing else would
            # record it. It was unfrozen once, and the comment claiming otherwise was false.
            "not_ledger_prefixes": sorted(NOT_LEDGER_PREFIXES),
        },
        "axes_unmeasured": unmeasured,
        "weakest_axis": weakest,
        "weakest_score": scored[weakest] if weakest else None,
        "axes": axes,
        "probes": probes,
    }


def compare(report: dict, baseline: dict) -> list[str]:
    """Fail-closed diff against a frozen profile.

    Ten regression classes, not one. A ratio alone is too easy to move without improving
    anything, so the frozen debt, the probe's axis, its stated procedure, the ledger
    classification and the baseline's own arithmetic are all pinned:

    * ``AXIS REGRESSION``  -- the score fell
    * ``DEBT INCREASE``    -- the numerator grew even though the ratio held or improved,
      which is how a probe is gamed by inflating its population instead of paying the debt
    * ``PROBE REMOVED``    -- the ruler was deleted
    * ``UNMEASURED REGRESSION`` -- the ruler went blind
    * ``AXIS MOVED``       -- the probe was reassigned to another axis, which rewrites *which*
      axis the report names as the hole while leaving the repository number intact
    * ``PROCEDURE CHANGED``-- the stated measurement procedure was edited; the number may be
      unchanged while meaning something else entirely
    * ``POPULATION INFLATION`` -- the score rose while the debt did NOT fall, i.e. the
      denominator grew; a score may only rise because the debt fell
    * ``LEDGER RECLASSIFIED`` -- a ledger moved between the surveyed and excluded sets, which
      shrinks both a denominator and its debt so neither of the above would object
    * ``BASELINE INCONSISTENT`` -- the frozen numbers do not satisfy their own arithmetic, or
      the frozen axis block disagrees with the frozen probes; a hand-edited baseline buys
      unlimited future headroom and every later comparison would be against the forgery
    * ``UNFROZEN PROBE`` -- a probe exists that the baseline never saw
    """
    problems: list[str] = []
    base_probes = {p["id"]: p for p in baseline.get("probes", [])}
    now_probes = {p["id"]: p for p in report.get("probes", [])}

    for pid, base in sorted(base_probes.items()):
        now = now_probes.get(pid)
        if now is None:
            problems.append(
                f"PROBE REMOVED {pid}: a frozen probe vanished -- the ruler was deleted"
            )
            continue
        if base.get("state") == "MEASURED" and now.get("state") != "MEASURED":
            problems.append(
                f"UNMEASURED REGRESSION {pid}: was MEASURED, now {now.get('state')} "
                f"({now.get('reason', 'no reason given')})"
            )
            continue
        if now.get("axis") != base.get("axis"):
            problems.append(
                f"AXIS MOVED {pid}: {base.get('axis')} -> {now.get('axis')} "
                "(the report would name a different axis as the hole)"
            )
        if now.get("procedure") != base.get("procedure"):
            problems.append(
                f"PROCEDURE CHANGED {pid}: the stated measurement was edited\n"
                f"      was: {base.get('procedure')}\n"
                f"      now: {now.get('procedure')}"
            )
        if base.get("state") != "MEASURED":
            continue
        if now["score"] < base["score"]:
            problems.append(
                f"AXIS REGRESSION {pid} ({now['axis']}): {base['score']:.6f} -> {now['score']:.6f} "
                f"(debt {base['debt']}/{base['population']} -> {now['debt']}/{now['population']})"
            )
        elif now["debt"] > base["debt"]:
            # The score held or improved while the debt itself grew: the population was
            # inflated. Paying debt is the only admissible way to move a number here.
            problems.append(
                f"DEBT INCREASE {pid} ({now['axis']}): {base['debt']} -> {now['debt']} entries "
                f"while the population moved {base['population']} -> {now['population']}; "
                "the ratio was improved by growing the denominator, not by paying the debt"
            )
        elif now["score"] > base["score"] and now["debt"] >= base["debt"]:
            # The one rule that makes every ratio honest: a score may only rise because the
            # DEBT fell. Rising while the debt is unchanged means the denominator grew -- adding
            # documents, adding files, widening a scan -- which improves nothing whatsoever.
            problems.append(
                f"POPULATION INFLATION {pid} ({now['axis']}): score rose "
                f"{base['score']:.6f} -> {now['score']:.6f} with debt unchanged at "
                f"{now['debt']} while the population moved {base['population']} -> "
                f"{now['population']}; a score may only rise because the debt fell. "
                "If the population genuinely grew, re-freeze with --write-baseline so the "
                "movement appears in the diff"
            )

    for pid in sorted(set(now_probes) - set(base_probes)):
        problems.append(f"UNFROZEN PROBE {pid}: present in the report but absent from the baseline")

    base_enrolments = baseline.get("mutation_enrolments")
    if base_enrolments is not None:
        added = sorted(set(report.get("mutation_enrolments", [])) - set(base_enrolments))
        removed = sorted(set(base_enrolments) - set(report.get("mutation_enrolments", [])))
        for rel in removed:
            problems.append(f"ENROLMENT REMOVED {rel}: a module left the mutation-kill ratchet")
        if added:
            # NOT a failure -- enrolling a module is the improvement this probe asks for. But
            # it is frozen so that it can never be SILENT: no static gate can prove a mutation
            # run happened, so the control is that 578 fabricated enrolments appear as 578
            # lines in this diff rather than as a quietly better number.
            problems.append(
                f"ENROLMENT ADDED ({len(added)}): {', '.join(added[:5])}"
                + (" ..." if len(added) > 5 else "")
                + " -- re-freeze with --write-baseline so the enrolment appears in the diff"
            )

    base_class = baseline.get("ledger_classification")
    now_class = report.get("ledger_classification")
    if base_class is not None and now_class != base_class:
        for field in ("ledgers", "not_ledgers", "not_ledger_prefixes"):
            was, now_set = set(base_class.get(field, [])), set(now_class.get(field, []))
            for rel in sorted(was - now_set):
                problems.append(f"LEDGER RECLASSIFIED {rel}: removed from {field}")
            for rel in sorted(now_set - was):
                problems.append(f"LEDGER RECLASSIFIED {rel}: added to {field}")

    # A hand-edited baseline is the ratchet's last soft spot: setting `debt` high and `score`
    # low buys unlimited future headroom, and nothing downstream would object because every
    # later comparison is against those numbers. So the frozen arithmetic is re-derived here.
    for frozen in baseline.get("probes", []):
        if frozen.get("state") != "MEASURED":
            problems.append(
                f"BASELINE INCONSISTENT ({frozen.get('id')}): a probe was frozen "
                f"{frozen.get('state')} -- a blind probe must never enter the baseline"
            )
            continue
        debt, population = frozen.get("debt"), frozen.get("population")
        if not isinstance(debt, int) or not isinstance(population, int) or population <= 0:
            problems.append(
                f"BASELINE INCONSISTENT ({frozen.get('id')}): debt/population are not "
                f"positive integers ({debt!r}/{population!r})"
            )
            continue
        if not 0 <= debt <= population:
            problems.append(
                f"BASELINE INCONSISTENT ({frozen.get('id')}): debt {debt} outside "
                f"population {population}"
            )
            continue
        expected = round(1.0 - debt / population, 6)
        if frozen.get("score") != expected:
            problems.append(
                f"BASELINE INCONSISTENT ({frozen.get('id')}): frozen score "
                f"{frozen.get('score')} != 1 - {debt}/{population} = {expected}"
            )

    # A baseline whose axis block disagrees with its own probes is either hand-edited or stale;
    # either way its numbers are not what the probes say and must not be trusted silently.
    for axis, info in (baseline.get("axes") or {}).items():
        mine = [p for p in baseline.get("probes", []) if p.get("axis") == axis]
        measured = [p["score"] for p in mine if p.get("state") == "MEASURED"]
        expected = min(measured) if measured else None
        if info.get("score") != expected:
            problems.append(
                f"BASELINE INCONSISTENT ({axis}): frozen axis score {info.get('score')} "
                f"does not equal the minimum of its frozen probes ({expected})"
            )
    return problems


class BaselineNotYetFrozen(RuntimeError):
    """``ref`` predates the baseline: this is its introducing change, not a tampering attempt."""


def _baseline_at(ref: str) -> dict:
    """Read the frozen profile as COMMITTED at ``ref``. Fails closed -- never returns {}.

    An unreadable *ref* is a hard failure. A readable ref that simply does not carry the
    baseline yet is the bootstrap case (the change that introduces it) and raises
    ``BaselineNotYetFrozen`` instead, so the gate reports it rather than reddening forever.
    """
    import subprocess

    rel = BASELINE.relative_to(ROOT).as_posix()
    known_ref = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )
    if known_ref.returncode != 0:
        raise ProbeError(f"unknown git ref {ref!r}")
    result = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=30,
    )
    if result.returncode != 0:
        # "Not yet frozen" must mean exactly that -- no profile existed at ``ref`` under ANY
        # name. Renaming the BASELINE constant is a one-line diff that would otherwise disable
        # the entire historical arm by making a live baseline look like an introducing change.
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )
        if listing.returncode != 0:
            raise ProbeError(f"cannot list the tree at {ref}")
        previous = sorted(
            line
            for line in listing.stdout.splitlines()
            if "TEN_AXES" in line and line.endswith(".json")
        )
        if previous:
            raise ProbeError(
                f"{rel} does not exist at {ref}, but a ten-axis profile does "
                f"({', '.join(previous)}) -- the baseline was RENAMED, not introduced"
            )
        raise BaselineNotYetFrozen(f"{rel} does not exist at {ref}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"baseline at {ref} is not valid JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the full report as JSON on stdout; the verdict goes to stderr",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="re-freeze the profile; REFUSES to lower any frozen score (monotone up only)",
    )
    parser.add_argument(
        "--against-ref",
        metavar="REF",
        help=(
            "also enforce monotonicity against the baseline committed at REF (e.g. the merge-"
            "request base). This is what closes the delete-then-refreeze bypass: without it, "
            "removing docs/TEN_AXES_BASELINE.json and re-freezing lowers the bar with a green "
            "pipeline. Fails closed if REF or its baseline cannot be read."
        ),
    )
    args = parser.parse_args(argv)

    report = build_report()
    out = sys.stderr if args.json else sys.stdout

    if args.write_baseline:
        # The ratchet's own weak point: a hand-edited baseline can lower the bar and the diff
        # gate would then pass. Re-freezing is therefore monotone-up ONLY. Deleting the file
        # first still bypasses this locally -- which is why CI passes --against-ref, comparing
        # the working profile with the baseline COMMITTED at the merge base. Laundering then
        # requires rewriting history, not deleting a file.
        # A blind probe must never enter the baseline: once frozen UNMEASURED it would be
        # exempt from every check below and could stay blind forever without anything saying so.
        blind = [p["id"] for p in report["probes"] if p["state"] != "MEASURED"]
        if blind:
            out.write(
                "REFUSED: will not freeze a profile containing blind probes "
                f"({', '.join(blind)}) -- fix the measurement first\n"
            )
            return 1
        if BASELINE.exists():
            # Re-freezing may RECORD a population that moved (tests and documents are added
            # constantly, and the diff shows it). It may never record a lower score, a higher
            # debt, a blinded probe or a reclassified ledger -- those are the ratchet itself.
            hard = ("AXIS REGRESSION", "DEBT INCREASE", "UNMEASURED REGRESSION", "PROBE REMOVED")
            hard += ("LEDGER RECLASSIFIED", "BASELINE INCONSISTENT", "ENROLMENT REMOVED")
            refusals = [
                r
                for r in compare(report, json.loads(BASELINE.read_text(encoding="utf-8")))
                if r.startswith(hard)
            ]
            if refusals:
                out.write("REFUSED: re-freezing would lower or blind a frozen probe\n")
                for refusal in refusals:
                    out.write(f"  - {refusal}\n")
                out.write(
                    "  Pay the debt, or delete docs/TEN_AXES_BASELINE.json deliberately in the "
                    "same commit if the population itself was redefined.\n"
                )
                return 1
        BASELINE.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        try:
            shown = BASELINE.relative_to(ROOT)
        except ValueError:
            shown = BASELINE
        out.write(f"wrote baseline: {shown}\n")
        return 0

    if args.json:
        sys.stdout.write(json.dumps(report, indent=2) + "\n")
    else:
        for axis in AXES:
            info = report["axes"][axis]
            if "score" in info:
                mark = " <- WEAKEST" if axis == report["weakest_axis"] else ""
                out.write(
                    f"  {axis:<16} {info['score']:.4f}  "
                    f"[{info['measured']}/{info['probes']} {info['state']}] "
                    f"bound by {info['binding_probe']}{mark}\n"
                )
            else:
                out.write(f"  {axis:<16} UNMEASURED  [{info['probes']} probes, 0 measured]\n")
        for probe in report["probes"]:
            if probe["state"] != "MEASURED":
                out.write(f"  ! {probe['id']}: {probe['state']} -- {probe['reason']}\n")

    if not BASELINE.exists():
        out.write(
            f"\nFAIL: {BASELINE.relative_to(ROOT)} absent. "
            "Freeze the profile with --write-baseline before enforcing.\n"
        )
        return 1

    working = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = compare(report, working)
    if args.against_ref:
        try:
            historical_baseline = _baseline_at(args.against_ref)
        except BaselineNotYetFrozen as exc:
            historical = []
            out.write(f"\nno historical baseline to compare: {exc} (introducing change)\n")
        except ProbeError as exc:
            historical = []
            problems.append(f"HISTORICAL BASELINE UNREADABLE at {args.against_ref}: {exc}")
        else:
            # TWO comparisons, not one. Comparing only the live report against history misses
            # the forgery that matters: a hand-edited baseline whose numbers are internally
            # CONSISTENT (debt 600, score = 1 - 600/637) passes every arithmetic check and every
            # report comparison, then becomes the reference after merge and buys unlimited
            # headroom. So the working BASELINE FILE is itself ratcheted against the committed
            # one -- the frozen record may improve, never worsen.
            historical = compare(report, historical_baseline)
            # Same exemptions as the report comparison below. Omitting ENROLMENT ADDED here
            # made every enrolment MR unmergeable -- i.e. the gate blocked the exact
            # improvement its own weakest axis demands. Caught on the first real paydown.
            baseline_exempt = ("POPULATION INFLATION", "UNFROZEN PROBE", "ENROLMENT ADDED")
            problems += [
                f"baseline vs {args.against_ref}: {p}"
                for p in compare(working, historical_baseline)
                if not p.startswith(baseline_exempt)
            ]
        # Everything is enforced against history EXCEPT the two classes that can only mark
        # genuine progress: POPULATION INFLATION (a denominator that grew, re-frozen on
        # purpose) and UNFROZEN PROBE (a ruler that was ADDED). Narrowing this list is how the
        # delete-then-refreeze bypass came back: with PROBE REMOVED and LEDGER RECLASSIFIED
        # merely "reported", deleting the baseline and re-freezing laundered both.
        exempt = ("POPULATION INFLATION", "UNFROZEN PROBE", "ENROLMENT ADDED")
        problems += [f"vs {args.against_ref}: {p}" for p in historical if not p.startswith(exempt)]
        noted = [p for p in historical if p.startswith(exempt)]
        if noted:
            out.write(f"\nnoted vs {args.against_ref} (progress, not enforced):\n")
            for note in noted:
                out.write(f"  ~ {note.splitlines()[0]}\n")

    if problems:
        out.write("\nFAIL: ten-axis composition regressed\n")
        for problem in problems:
            out.write(f"  - {problem}\n")
        return 1

    out.write(
        f"\nOK: no axis regressed. Weakest axis: {report['weakest_axis']} "
        f"= {report['weakest_score']:.4f}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
