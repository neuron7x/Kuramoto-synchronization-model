# SPDX-License-Identifier: MIT
"""ENV-002 Python matrix gate — the 3.11 companion to ENV-001's 3.12 preflight.

ENV-001 (``scripts/ci/check_env_preflight.py``) certifies the *live* canonical
3.12 interpreter: it resolves every installed distribution and fails closed on a
sub-floor or missing dependency. That gate can only speak for the interpreter it
is *running on*. GeoSync declares a two-leg support window in ``pyproject.toml``::

    requires-python = ">=3.11,<3.13"
    classifiers = [... "Programming Language :: Python :: 3.11",
                       "Programming Language :: Python :: 3.12", ...]

so 3.11 is a first-class supported leg. This sandbox only has a 3.12 interpreter,
so we cannot honestly emit a *live* 3.11 resolution here. The honest deliverable
is therefore a **contract**, not a live run:

    artifacts/env/python311.json is the 3.11 environment CONTRACT — the target
    interpreter minor, the same 46 required dependencies, and the same floors /
    specifiers as the canonical policy — with per-dependency resolved versions
    left null and marked ``pending-matrix-ci``. The live 3.11 resolution is
    performed by ``.github/workflows/python-matrix.yml`` (which runs the full
    suite on BOTH 3.11 and 3.12), or by the hermetic image of ENV-005 — never
    faked from this 3.12 sandbox.

This gate validates that CONTRACT against the single source of dependency truth
(``requirements.txt``) and the declared support window (``pyproject.toml``),
fail-closed. It is a *policy* checker: it proves the 3.11 leg carries exactly the
same dependency policy as 3.12 and detects version-specific divergence
(a dropped dep, an added dep, a mutated floor, or a target minor outside the
declared support window). It deliberately does NOT require the contract to carry
resolved versions, precisely because the live resolution is deferred to CI.

Severity model
--------------
HARD failures (exit 1 — fail-closed contract):
    * declared target Python minor is not in the pyproject support window
      (e.g. a descriptor claiming 3.9 or 3.13)
    * a required dependency from ``requirements.txt`` is absent from the contract
    * the contract carries a dependency that is NOT a declared requirement
    * a specifier in the contract diverges from ``requirements.txt`` (floor drift)
    * the recorded ``python_floor`` / ``pandas_floor`` do not match policy
    * a non-null resolved version violates its own specifier (only checked when
      the contract has actually been resolved by a live matrix leg)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"
CONTRACT_DEFAULT = ROOT / "artifacts" / "env" / "python311.json"

SCHEMA = "geosync.env.descriptor/1"
PANDAS_MIN = "2.3.3"


# --------------------------------------------------------------------------- #
# Sources of truth
# --------------------------------------------------------------------------- #
def parse_required(requirements_path: Path = REQUIREMENTS) -> list[Requirement]:
    """Parse the direct required dependencies from ``requirements.txt``.

    Mirrors ``check_env_preflight.parse_required`` so both env gates share one
    definition of "the 46 required dependencies".
    """
    reqs: list[Requirement] = []
    for raw in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        reqs.append(Requirement(line))
    return reqs


def supported_python_minors(pyproject_path: Path = PYPROJECT) -> list[tuple[int, int]]:
    """Derive the declared supported (major, minor) legs from ``pyproject.toml``.

    Reads the ``Programming Language :: Python :: X.Y`` classifiers — the
    explicit, human-curated statement of which legs the project claims to
    support. ``requires-python`` is a *range*; the classifiers are the discrete
    matrix legs, which is exactly what a version matrix needs.
    """
    text = pyproject_path.read_text(encoding="utf-8")
    minors: list[tuple[int, int]] = []
    for m in re.finditer(
        r"Programming Language :: Python :: (\d+)\.(\d+)\b", text
    ):
        leg = (int(m.group(1)), int(m.group(2)))
        if leg not in minors:
            minors.append(leg)
    return minors


def requires_python_spec(pyproject_path: Path = PYPROJECT) -> str:
    """Return the raw ``requires-python`` specifier string from pyproject."""
    text = pyproject_path.read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- #
# Contract construction (policy -> descriptor)
# --------------------------------------------------------------------------- #
def build_contract(
    target_minor: tuple[int, int] = (3, 11),
    requirements_path: Path = REQUIREMENTS,
) -> dict[str, Any]:
    """Build the environment CONTRACT for a target Python minor.

    The contract carries the *policy* (target minor, floors, specifiers) but
    NOT live resolved versions: ``resolved`` maps every required dep to ``null``
    with ``resolution_status = "pending-matrix-ci"``. It is built directly from
    ``requirements.txt`` so it can never silently drift from the dependency
    policy — the gate re-derives the same set and asserts equality.
    """
    reqs = parse_required(requirements_path)
    specifiers = {req.name: str(req.specifier) for req in reqs}
    resolved: dict[str, str | None] = {req.name: None for req in reqs}
    major, minor = target_minor
    return {
        "schema": SCHEMA,
        "descriptor_id": f"python{major}{minor}",
        "role": "ENV-002 Python matrix leg contract (companion to ENV-001 3.12)",
        "kind": "contract",
        "resolution_status": "pending-matrix-ci",
        "resolution_note": (
            "This is a CONTRACT, not a live run. Per-dependency resolved "
            "versions are null and are filled by the live matrix leg in "
            ".github/workflows/python-matrix.yml (python "
            f"{major}.{minor}) or the ENV-005 hermetic image — never emitted "
            "from a non-matching interpreter."
        ),
        "python": {
            "target": f"{major}.{minor}.x",
            "major": major,
            "minor": minor,
            "implementation": "CPython",
        },
        "required_dependencies": {
            "count": len(reqs),
            "pandas_floor": PANDAS_MIN,
            "python_floor": f"{major}.{minor}",
            "requires_python": requires_python_spec(),
            "resolved": resolved,
            "specifiers": specifiers,
        },
    }


# --------------------------------------------------------------------------- #
# Pure evaluation (contract -> verdict)
# --------------------------------------------------------------------------- #
def evaluate_contract(
    descriptor: dict[str, Any],
    requirements: list[Requirement],
    supported_minors: list[tuple[int, int]],
) -> tuple[bool, dict[str, Any]]:
    """Pure evaluation of a matrix-leg contract against the dependency policy.

    Returns ``(ok, report)``. ``ok`` is False (fail-closed) on any HARD
    invariant violation.
    """
    hard: list[str] = []

    # --- schema -----------------------------------------------------------
    if descriptor.get("schema") != SCHEMA:
        hard.append(f"schema: expected {SCHEMA!r}, got {descriptor.get('schema')!r}")

    py = descriptor.get("python", {})
    try:
        leg = (int(py["major"]), int(py["minor"]))
    except (KeyError, TypeError, ValueError):
        leg = None
        hard.append("python: descriptor is missing a valid major/minor target")

    # --- declared target must be a supported leg --------------------------
    target_supported = leg is not None and leg in supported_minors
    if leg is not None and not target_supported:
        hard.append(
            f"python: target {leg[0]}.{leg[1]} is not a declared supported leg "
            f"{sorted(supported_minors)} (pyproject classifiers)"
        )

    dep_block = descriptor.get("required_dependencies", {})
    contract_specs: dict[str, str] = dict(dep_block.get("specifiers", {}))
    resolved: dict[str, str | None] = dict(dep_block.get("resolved", {}))

    policy_specs = {req.name: str(req.specifier) for req in requirements}

    policy_names = set(policy_specs)
    contract_names = set(contract_specs)

    missing = sorted(policy_names - contract_names)
    extra = sorted(contract_names - policy_names)
    divergent: list[dict[str, str]] = []
    for name in sorted(policy_names & contract_names):
        if contract_specs[name] != policy_specs[name]:
            divergent.append(
                {
                    "name": name,
                    "contract": contract_specs[name],
                    "policy": policy_specs[name],
                }
            )

    for name in missing:
        hard.append(f"missing required dependency in contract: {name}")
    for name in extra:
        hard.append(f"contract declares a non-required dependency: {name}")
    for d in divergent:
        hard.append(
            f"specifier divergence: {d['name']} contract {d['contract']!r} != "
            f"policy {d['policy']!r}"
        )

    # --- floors -----------------------------------------------------------
    pandas_floor = dep_block.get("pandas_floor")
    if pandas_floor != PANDAS_MIN:
        hard.append(f"pandas_floor: expected {PANDAS_MIN}, got {pandas_floor}")

    if leg is not None:
        expected_py_floor = f"{leg[0]}.{leg[1]}"
        py_floor = dep_block.get("python_floor")
        if py_floor != expected_py_floor:
            hard.append(
                f"python_floor: expected {expected_py_floor}, got {py_floor}"
            )

    # --- resolved-version consistency (only if a live leg filled them) ----
    resolved_present = {k: v for k, v in resolved.items() if v is not None}
    resolution_violations: list[dict[str, str]] = []
    if resolved_present:
        by_name = {req.name: req for req in requirements}
        for name, ver in resolved_present.items():
            req = by_name.get(name)
            if req is None:
                continue
            if req.specifier and not req.specifier.contains(ver, prereleases=True):
                resolution_violations.append(
                    {"name": name, "installed": ver, "specifier": str(req.specifier)}
                )
    for v in resolution_violations:
        hard.append(
            f"resolved version out of policy: {v['name']} {v['installed']} "
            f"!~ {v['specifier']}"
        )

    ok = not hard
    report = {
        "ok": ok,
        "descriptor_id": descriptor.get("descriptor_id"),
        "target": py.get("target"),
        "target_supported": target_supported,
        "supported_minors": [f"{a}.{b}" for a, b in sorted(supported_minors)],
        "policy_dep_count": len(policy_names),
        "contract_dep_count": len(contract_names),
        "missing": missing,
        "extra": extra,
        "divergent_specifiers": divergent,
        "resolution_status": descriptor.get("resolution_status"),
        "resolved_count": len(resolved_present),
        "resolution_violations": resolution_violations,
        "hard_failures": hard,
    }
    return ok, report


def _render(report: dict[str, Any]) -> str:
    lines: list[str] = []
    status = "PASS" if report["ok"] else "FAIL"
    lines.append(f"ENV-002 matrix contract gate: {status}")
    lines.append(
        f"  descriptor: {report['descriptor_id']} target={report['target']} "
        f"supported={report['target_supported']} "
        f"(legs {report['supported_minors']})"
    )
    lines.append(
        f"  deps: contract {report['contract_dep_count']} vs "
        f"policy {report['policy_dep_count']}"
    )
    lines.append(
        f"  resolution: {report['resolution_status']} "
        f"(resolved {report['resolved_count']} — live run is a matrix-CI leg)"
    )
    if report["missing"]:
        lines.append(f"  MISSING (hard): {', '.join(report['missing'])}")
    if report["extra"]:
        lines.append(f"  EXTRA (hard): {', '.join(report['extra'])}")
    if report["divergent_specifiers"]:
        lines.append("  SPECIFIER DIVERGENCE (hard):")
        for d in report["divergent_specifiers"]:
            lines.append(f"      - {d['name']}: {d['contract']} != {d['policy']}")
    if report["hard_failures"]:
        lines.append("  HARD FAILURES:")
        for hf in report["hard_failures"]:
            lines.append(f"      - {hf}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ENV-002 Python matrix contract gate.")
    parser.add_argument(
        "--contract",
        type=Path,
        default=CONTRACT_DEFAULT,
        metavar="PATH",
        help="path to the matrix-leg contract JSON to validate.",
    )
    parser.add_argument(
        "--emit-contract",
        type=Path,
        default=None,
        metavar="PATH",
        help="build the 3.11 contract from policy, write it to PATH, and exit 0.",
    )
    parser.add_argument(
        "--target",
        default="3.11",
        metavar="MAJOR.MINOR",
        help="target minor for --emit-contract (default 3.11).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the report as JSON instead of text.",
    )
    args = parser.parse_args(argv)

    if args.emit_contract is not None:
        major_s, minor_s = args.target.split(".")
        contract = build_contract((int(major_s), int(minor_s)))
        args.emit_contract.parent.mkdir(parents=True, exist_ok=True)
        args.emit_contract.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote contract -> {args.emit_contract}")
        return 0

    descriptor = json.loads(args.contract.read_text(encoding="utf-8"))
    ok, report = evaluate_contract(
        descriptor, parse_required(), supported_python_minors()
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render(report))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
