"""Dependency-truth unifier.

Detects dependency drift across the parallel manifests this repository
maintains:

  - pyproject.toml                — canonical declared floor
  - requirements.txt              — runtime install path used by some Dockerfiles
  - requirements-dev.txt          — extends requirements.txt with dev tooling
  - requirements-scan.txt         — lightweight scan-only manifest
  - requirements.lock             — pinned production install
  - requirements-dev.lock         — pinned dev install
  - requirements-scan.lock        — pinned scan install
  - constraints/security.txt      — exact pins for security-critical packages

Drift classes detected:

  D1  pyproject lower bound stricter than requirements lower bound
      (the F01 trap)
  D2  lockfile pin below the manifest floor
      (the F03 trap)
  D3  scan path differs from deploy path
      (security scanner can't see what production installs)
  D4  Dockerfile installs an unscanned manifest
  D5  constraints/security.txt weaker than the matching manifest floor
  D6  package imported directly but only declared transitively
      (already covered by deptry; we surface the manifest-side facts)
  D7  constraints/security.txt pins ABOVE the manifest's strict upper
      bound (the lock-regeneration trap; pip-compile cannot satisfy
      both bounds — observable as `make lock` ResolutionImpossible)
  D8  constraints/security.txt exact-pin disagrees with a
      requirements*.lock exact-pin for the same package (the
      install-time trap; `pip install -c constraints -r lock` is
      ResolutionImpossible — the exact failure every dependabot
      /constraints bump hits until the locks are regenerated)

Output is a deterministic JSON report. Exit code is non-zero when any
drift is found that is not on the accepted backlog list.

This file is stdlib + PyYAML + tomllib (Python 3.11+) only. No project
imports.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Pre-existing drifts on the accepted backlog. New entries get review pushback.
# Mirrors tests/unit/governance/test_dependency_floor_alignment.py.
# ---------------------------------------------------------------------------
ACCEPTED_BACKLOG_D1: frozenset[str] = frozenset(
    {
        "fastapi",
        "prometheus-client",
        "pydantic",
        "requests",
        "streamlit",
        "uvicorn",
    }
)

# Regression cases the validator MUST catch. If any of these is missing from
# the discovered drift set, the test suite fails.
F01_REGRESSION_PACKAGE = "torch"
F03_REGRESSION_PACKAGE = "strawberry-graphql"


_PEP508_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?")
_LOWER_BOUND = re.compile(r">=\s*([0-9][0-9A-Za-z.+\-_!]*)")
# Match strict-less-than upper bounds. Captures the version after ``<``;
# we use a negative lookahead to exclude ``<=`` (which is a different
# semantic — strict < is the common pip-style upper-cap, e.g. <0.27).
_UPPER_BOUND = re.compile(r"<(?!=)\s*([0-9][0-9A-Za-z.+\-_!]*)")
_EXACT_PIN = re.compile(r"==\s*([0-9][0-9A-Za-z.+\-_!]*)")


def _parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in text.split("."):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def _pep508_name(spec: str) -> str | None:
    match = _PEP508_NAME.match(spec.strip())
    if not match:
        return None
    return match.group(1).lower()


@dataclass(frozen=True)
class Drift:
    package: str
    drift_class: str  # D1..D7
    detail: str
    priority: str  # CRITICAL / HIGH / MEDIUM / LOW
    fix: str
    manifests: tuple[str, ...] = ()


def _read_pyproject_floors(path: Path) -> dict[str, str]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps = project.get("dependencies") or []
    bounds: dict[str, str] = {}
    for spec in deps:
        name = _pep508_name(spec)
        if not name:
            continue
        m = _LOWER_BOUND.search(spec)
        if m:
            bounds[name] = m.group(1)
    return bounds


def _read_plain_floors(path: Path) -> dict[str, str]:
    """Read a plain `name>=ver` style requirements file."""
    bounds: dict[str, str] = {}
    if not path.exists():
        return bounds
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        name = _pep508_name(stripped)
        if not name:
            continue
        m = _LOWER_BOUND.search(stripped)
        if m:
            bounds[name] = m.group(1)
    return bounds


def _read_pyproject_uppers(path: Path) -> dict[str, str]:
    """Return {package_name: strict-less-than upper bound} from pyproject.

    Captures specs like ``"pandera>=0.20.4,<0.27"``. Packages without an
    upper bound are absent from the result.
    """
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    deps = project.get("dependencies") or []
    uppers: dict[str, str] = {}
    for spec in deps:
        name = _pep508_name(spec)
        if not name:
            continue
        m = _UPPER_BOUND.search(spec)
        if m:
            uppers[name] = m.group(1)
    return uppers


def _read_plain_uppers(path: Path) -> dict[str, str]:
    """Strict-less-than upper bounds from a plain requirements file."""
    if not path.exists():
        return {}
    uppers: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        # Drop the inline comment BEFORE scanning for an upper bound. Security
        # pins frequently document the vulnerable range in a trailing comment
        # (e.g. ``cryptography>=49.0.0  # <48.0.1 vulnerable``); without this
        # split the "<48.0.1" inside the comment is misread as a strict upper
        # bound, fabricating a D7 ResolutionImpossible drift. A real bound such
        # as ``pydantic>=2.13.0,<3.0.0`` sits before the ``#`` and is kept.
        code = stripped.split("#", 1)[0].strip()
        name = _pep508_name(code)
        if not name:
            continue
        m = _UPPER_BOUND.search(code)
        if m:
            uppers[name] = m.group(1)
    return uppers


def _read_lock_pins(path: Path) -> dict[str, str]:
    """Read a pip-compile lockfile: `name==ver` lines (plain text)."""
    pins: dict[str, str] = {}
    if not path.exists():
        return pins
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip any inline comment.
        stripped = stripped.split("#", 1)[0].strip()
        name = _pep508_name(stripped)
        if not name:
            continue
        m = _EXACT_PIN.search(stripped)
        if m:
            pins[name] = m.group(1)
    return pins


def _scan_dockerfile_install_paths(repo_root: Path) -> dict[str, list[str]]:
    """Return {dockerfile: [requirement-files-installed]}."""
    result: dict[str, list[str]] = {}
    for df in repo_root.rglob("Dockerfile*"):
        rel = df.relative_to(repo_root)
        try:
            text = df.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        installs: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line.startswith("RUN"):
                continue
            for m in re.finditer(r"-[r|c]\s+([\w./-]+\.(?:txt|lock))", line):
                installs.append(m.group(1))
        if installs:
            result[str(rel)] = installs
    return result


_SECURITY_SCAN_TOOLS = ("pip-audit", "safety ", "osv-scanner", "trivy", "snyk")


def _scan_workflow_install_paths(repo_root: Path) -> dict[str, list[str]]:
    """Return {workflow_file: [manifests run through a SECURITY SCANNER]}.

    We deliberately do NOT count `pip install -r foo.txt` as "scanned" —
    installation alone is not auditing. Only manifests passed to pip-audit /
    safety / osv-scanner / trivy etc. count.
    """
    result: dict[str, list[str]] = {}
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.exists():
        return result
    for wf in wf_dir.glob("*.yml"):
        rel = wf.relative_to(repo_root)
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        installs: list[str] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not any(tool in line for tool in _SECURITY_SCAN_TOOLS):
                continue
            for m in re.finditer(r"-[rc]\s+([\w./-]+\.(?:txt|lock))", line):
                installs.append(m.group(1))
        if installs:
            result[str(rel)] = installs
    return result


@dataclass
class TruthReport:
    drifts: list[Drift] = field(default_factory=list)
    install_paths_dockerfile: dict[str, list[str]] = field(default_factory=dict)
    install_paths_ci: dict[str, list[str]] = field(default_factory=dict)
    accepted_backlog: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "drifts": [asdict(d) for d in self.drifts],
            "install_paths_dockerfile": self.install_paths_dockerfile,
            "install_paths_ci": self.install_paths_ci,
            "accepted_backlog": self.accepted_backlog,
        }

    def is_clean_after_backlog(self) -> bool:
        for d in self.drifts:
            if d.drift_class == "D1" and d.package in ACCEPTED_BACKLOG_D1:
                continue
            return False
        return True


def collect(repo_root: Path) -> TruthReport:
    pyp = _read_pyproject_floors(repo_root / "pyproject.toml")
    req = _read_plain_floors(repo_root / "requirements.txt")
    req_scan = _read_plain_floors(repo_root / "requirements-scan.txt")
    lock = _read_lock_pins(repo_root / "requirements.lock")
    lock_dev = _read_lock_pins(repo_root / "requirements-dev.lock")
    lock_scan = _read_lock_pins(repo_root / "requirements-scan.lock")
    constraints = _read_lock_pins(repo_root / "constraints" / "security.txt")

    drifts: list[Drift] = []

    # D1 — pyproject vs requirements.txt lower-bound drift.
    for name in sorted(set(pyp) & set(req)):
        if _parse_version(req[name]) < _parse_version(pyp[name]):
            drifts.append(
                Drift(
                    package=name,
                    drift_class="D1",
                    detail=(
                        f"requirements.txt floor {req[name]} is below pyproject floor {pyp[name]}"
                    ),
                    priority="MEDIUM" if name in ACCEPTED_BACKLOG_D1 else "HIGH",
                    fix="raise requirements.txt to match pyproject lower bound",
                    manifests=("pyproject.toml", "requirements.txt"),
                )
            )

    # D2 — lockfile pin below manifest floor.
    for lock_path, lock_pins in (
        ("requirements.lock", lock),
        ("requirements-dev.lock", lock_dev),
        ("requirements-scan.lock", lock_scan),
    ):
        for name, version in sorted(lock_pins.items()):
            floor = pyp.get(name) or req.get(name) or req_scan.get(name)
            if not floor:
                continue
            if _parse_version(version) < _parse_version(floor):
                drifts.append(
                    Drift(
                        package=name,
                        drift_class="D2",
                        detail=(f"{lock_path} pins {version}, below floor {floor}"),
                        priority="HIGH",
                        fix=(f"regenerate {lock_path} or surgically bump {name} to >= {floor}"),
                        manifests=(lock_path,),
                    )
                )

    # D3 — scan path differs from deploy path. We compare requirements.lock
    # vs requirements-scan.lock for packages declared in both. A divergence
    # of 1 patch is ignored (resolver noise); anything bigger surfaces.
    for name in sorted(set(lock) & set(lock_scan)):
        if lock[name] == lock_scan[name]:
            continue
        a = _parse_version(lock[name])
        b = _parse_version(lock_scan[name])
        if a != b:
            drifts.append(
                Drift(
                    package=name,
                    drift_class="D3",
                    detail=(
                        f"requirements.lock pins {lock[name]} but "
                        f"requirements-scan.lock pins {lock_scan[name]}"
                    ),
                    priority="MEDIUM",
                    fix=(
                        "regenerate both lockfiles in lockstep so the "
                        "scanner sees the same version production runs"
                    ),
                    manifests=("requirements.lock", "requirements-scan.lock"),
                )
            )

    # D4 — Dockerfile installs an unscanned manifest. We treat
    # requirements.txt / requirements-dev.txt as "unscanned" because they
    # are looser than the lockfiles; security-deep.yml runs pip-audit on
    # the lockfiles, not the txt files.
    df_paths = _scan_dockerfile_install_paths(repo_root)
    ci_paths = _scan_workflow_install_paths(repo_root)
    scanned_ci_paths: set[str] = set()
    for files in ci_paths.values():
        for f in files:
            scanned_ci_paths.add(Path(f).name)
    for df, files in sorted(df_paths.items()):
        for f in files:
            base = Path(f).name
            if base.endswith(".lock"):
                continue
            if base not in scanned_ci_paths and base not in {
                "requirements-scan.txt",
                "requirements-scan.lock",
            }:
                drifts.append(
                    Drift(
                        package=f"<dockerfile:{df}>",
                        drift_class="D4",
                        detail=(f"{df} installs {f}, which is not scanned by any CI workflow"),
                        priority="HIGH",
                        fix=(
                            "either install the lockfile in this Dockerfile "
                            "or add a CI workflow that pip-audit's the same "
                            "manifest the Dockerfile uses"
                        ),
                        manifests=(df,),
                    )
                )

    # D5 — constraints/security.txt weaker than manifest floor.
    for name, pin in sorted(constraints.items()):
        floor = pyp.get(name) or req.get(name) or req_scan.get(name)
        if not floor:
            continue
        if _parse_version(pin) < _parse_version(floor):
            drifts.append(
                Drift(
                    package=name,
                    drift_class="D5",
                    detail=(
                        f"constraints/security.txt pins {pin}, below the manifest floor {floor}"
                    ),
                    priority="HIGH",
                    fix=f"raise {name} in constraints/security.txt to >= {floor}",
                    manifests=("constraints/security.txt",),
                )
            )

    # D7 — constraints/security.txt pins ABOVE the manifest's strict
    # upper bound. This is the inverse of D5 and the load-bearing
    # detector for the lock-regeneration class of failure: a constraint
    # pin at e.g. ``pandera==0.31.1`` while a manifest declares
    # ``pandera<0.27`` makes ``pip-compile --constraint=...`` impossible
    # (the resolver cannot satisfy both bounds simultaneously). The
    # observable symptom is ``make lock`` exiting with
    # ``ResolutionImpossible``.
    pyp_uppers = _read_pyproject_uppers(repo_root / "pyproject.toml")
    req_uppers = _read_plain_uppers(repo_root / "requirements.txt")
    req_scan_uppers = _read_plain_uppers(repo_root / "requirements-scan.txt")
    for name, pin in sorted(constraints.items()):
        # Find the strictest (lowest) declared upper bound across manifests.
        candidate_uppers = [
            (src, val)
            for src, val in (
                ("pyproject.toml", pyp_uppers.get(name)),
                ("requirements.txt", req_uppers.get(name)),
                ("requirements-scan.txt", req_scan_uppers.get(name)),
            )
            if val
        ]
        if not candidate_uppers:
            continue
        # Pick the lowest upper bound (the one most likely to clip the pin).
        strictest_src, strictest_upper = min(candidate_uppers, key=lambda kv: _parse_version(kv[1]))
        if _parse_version(pin) >= _parse_version(strictest_upper):
            drifts.append(
                Drift(
                    package=name,
                    drift_class="D7",
                    detail=(
                        f"constraints/security.txt pins {name}=={pin}, but "
                        f"{strictest_src} declares {name}<{strictest_upper}; "
                        "pip-compile --constraint cannot satisfy both"
                    ),
                    priority="HIGH",
                    fix=(
                        f"either lift the {name} upper bound in "
                        f"{strictest_src} above {pin}, or downgrade the "
                        f"constraints/security.txt pin below {strictest_upper}"
                    ),
                    manifests=("constraints/security.txt", strictest_src),
                )
            )

    # D8 — constraints/security.txt exact-pin disagrees with a
    # requirements*.lock exact-pin for the SAME package. This is the
    # install-time ResolutionImpossible trap (distinct from D7's
    # pip-compile-time trap): CI runs
    # ``pip install -c constraints/security.txt -r requirements.lock``.
    # When dependabot's /constraints ecosystem bumps a pin in
    # constraints/security.txt but the lock files (derived artifacts of
    # constraints/security.txt via ``pip-compile --constraint=...``) still
    # carry the OLD exact pin, pip sees two contradicting ``==`` pins for
    # one package and aborts with ``ResolutionImpossible`` *before any
    # gate runs*. The observable symptom is python-quality +
    # secrets-supply-chain failing at the shared setup step while
    # fast/heavy tests are SKIPPED (they ``needs: python-quality``). The
    # constraints ecosystem structurally cannot regenerate the locks, so
    # nothing detected this divergence until now — every constraints-only
    # bump silently broke setup. This makes it explicit and fail-closed.
    for lock_path, lock_pins in (
        ("requirements.lock", lock),
        ("requirements-dev.lock", lock_dev),
        ("requirements-scan.lock", lock_scan),
    ):
        for name, pin in sorted(constraints.items()):
            locked = lock_pins.get(name)
            if not locked:
                continue
            if _parse_version(locked) != _parse_version(pin):
                drifts.append(
                    Drift(
                        package=name,
                        drift_class="D8",
                        detail=(
                            f"constraints/security.txt pins {name}=={pin} but "
                            f"{lock_path} pins {name}=={locked}; "
                            f"`pip install -c constraints/security.txt -r "
                            f"{lock_path}` resolves to ResolutionImpossible "
                            f"(two contradicting == pins)"
                        ),
                        priority="HIGH",
                        fix=(
                            f"regenerate the lock files against the new "
                            f"constraint: `make deps-update` (pip-compile "
                            f"--constraint=constraints/security.txt), then "
                            f"commit the updated {lock_path}"
                        ),
                        manifests=("constraints/security.txt", lock_path),
                    )
                )

    # D6 is left as a placeholder: deptry already covers it. We surface a
    # synthetic finding that points the user at deptry rather than
    # duplicating its logic.
    deptry_pointer = Drift(
        package="<see deptry>",
        drift_class="D6",
        detail=(
            "Direct-imports-of-transitive-deps detection is delegated to "
            "deptry. Run `deptry .` and treat DEP001/DEP003 findings as "
            "drift in this category."
        ),
        priority="LOW",
        fix="run deptry; declare imported packages explicitly in pyproject",
        manifests=("pyproject.toml",),
    )
    # Add the pointer only when we successfully scanned at least one
    # source — i.e. this is a working repo. We surface it so the report is
    # complete; the test suite distinguishes synthetic from real drifts.
    drifts.append(deptry_pointer)

    return TruthReport(
        drifts=drifts,
        install_paths_dockerfile=df_paths,
        install_paths_ci=ci_paths,
        accepted_backlog=sorted(ACCEPTED_BACKLOG_D1),
    )


def _is_actionable(d: Drift) -> bool:
    """Real drift the validator should fail on (after the backlog filter)."""
    if d.drift_class == "D6":
        return False
    if d.drift_class == "D1" and d.package in ACCEPTED_BACKLOG_D1:
        return False
    return True


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect dependency-truth drift across GeoSync manifests",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: project root inferred from this file)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write JSON report to this path; default stdout",
    )
    parser.add_argument(
        "--exit-on-drift",
        action="store_true",
        help="exit non-zero when actionable drift exists (default: report only)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = collect(args.repo_root)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)

    actionable = [d for d in report.drifts if _is_actionable(d)]
    if actionable and args.exit_on_drift:
        print(
            f"FAIL: {len(actionable)} actionable drift(s) detected",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
