"""Governance test: requirements.txt lower bounds must not undercut pyproject.

This is the load-bearing test for claim ledger entries
``SEC-DEP-TORCH-RANGE-DRIFT`` and ``SEC-DEP-STRAWBERRY-VERSION-RISK``.

It asserts that for every package declared in BOTH ``pyproject.toml`` and
``requirements.txt``, the requirements.txt lower bound is greater than or
equal to the pyproject lower bound. This catches the F01 class of bugs at
PR-time, before the bound can drift back to a vulnerable lower edge.

The test deliberately does NOT install or resolve packages; it is a
manifest-level structural check that runs in milliseconds.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS = REPO_ROOT / "requirements.txt"

# Packages on this allowlist are deliberately omitted from requirements.txt
# (e.g. optional GPU stack, dev-only). They MUST be re-checked when added.
DELIBERATELY_NOT_IN_REQUIREMENTS: frozenset[str] = frozenset()

# Pre-existing range drifts known at the time this gate was introduced.
# These are TRACKED, not BLESSED — each entry should be eliminated by a
# focused hardening PR. Adding a new entry requires a comment with rationale
# and gets review pushback.
#
# DO NOT add a new entry to escape a real F01-class regression. The
# load-bearing claim ledger entries (SEC-DEP-TORCH-RANGE-DRIFT and
# SEC-DEP-STRAWBERRY-VERSION-RISK) are guarded by the per-package strict
# tests below; this set only suppresses the broad-sweep test for already-
# known drift while the backlog is paid down.
ACCEPTED_PRE_EXISTING_DRIFTS = frozenset(
    {
        "fastapi",  # pyproject>=0.135.3 vs requirements>=0.120.0
        "prometheus-client",  # pyproject>=0.25.0  vs requirements>=0.23.1
        "pydantic",  # pyproject>=2.13.0  vs requirements>=2.12.4
        "requests",  # pyproject>=2.33.0  vs requirements>=2.32.5
        "streamlit",  # pyproject>=1.54.0  vs requirements>=1.31.0
        "uvicorn",  # pyproject>=0.44.0  vs requirements>=0.37.0
    }
)

_PEP508_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?")
_LOWER_BOUND = re.compile(r">=\s*([0-9][0-9A-Za-z.+\-_!]*)")


def _parse_version(text: str) -> tuple[int, ...]:
    """Crude PEP 440 numeric prefix parser: '2.11.0' -> (2, 11, 0)."""
    parts = []
    for chunk in text.split("."):
        match = re.match(r"^(\d+)", chunk)
        if not match:
            break
        parts.append(int(match.group(1)))
    return tuple(parts)


def _read_pyproject_lower_bounds() -> dict[str, str]:
    """Return {package_name: lower_bound_string} from pyproject's main deps."""
    text = PYPROJECT.read_text(encoding="utf-8")
    bounds: dict[str, str] = {}
    in_deps = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("dependencies"):
            in_deps = True
            continue
        if in_deps and stripped.startswith("]"):
            in_deps = False
            continue
        if not in_deps:
            continue
        # Lines look like:  "torch>=2.11.0",
        m_quote = re.match(r'^"([^"]+)"', stripped)
        if not m_quote:
            continue
        spec = m_quote.group(1)
        name_match = _PEP508_NAME.match(spec)
        if not name_match:
            continue
        name = name_match.group(1).lower()
        lower = _LOWER_BOUND.search(spec)
        if lower:
            bounds[name] = lower.group(1)
    return bounds


def _read_requirements_lower_bounds() -> dict[str, str]:
    text = REQUIREMENTS.read_text(encoding="utf-8")
    bounds: dict[str, str] = {}
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-r "):
            continue
        name_match = _PEP508_NAME.match(stripped)
        if not name_match:
            continue
        name = name_match.group(1).lower()
        lower = _LOWER_BOUND.search(stripped)
        if lower:
            bounds[name] = lower.group(1)
    return bounds


def test_pyproject_and_requirements_exist() -> None:
    assert PYPROJECT.exists(), f"pyproject.toml missing at {PYPROJECT}"
    assert REQUIREMENTS.exists(), f"requirements.txt missing at {REQUIREMENTS}"


def test_requirements_lower_bound_not_below_pyproject() -> None:
    """For every package in BOTH manifests, requirements lower bound >= pyproject."""
    pyp = _read_pyproject_lower_bounds()
    req = _read_requirements_lower_bounds()
    overlap = set(pyp) & set(req)
    assert overlap, (
        "expected at least one package present in both pyproject.toml "
        "and requirements.txt — manifest topology may have drifted"
    )

    drifts: list[str] = []
    for name in sorted(overlap):
        if name in ACCEPTED_PRE_EXISTING_DRIFTS:
            continue
        pyp_v = _parse_version(pyp[name])
        req_v = _parse_version(req[name])
        if not pyp_v or not req_v:
            # Cannot parse one of them — skip rather than false-positive.
            continue
        if req_v < pyp_v:
            drifts.append(
                f"{name}: pyproject>={pyp[name]}  vs  requirements>={req[name]} "
                f"(requirements lower bound is below pyproject)"
            )
    assert not drifts, (
        "New range-drift detected (not on the accepted backlog list).\n"
        "Either fix the requirements.txt lower bound, or — if the drift is\n"
        "deliberate — add the package to ACCEPTED_PRE_EXISTING_DRIFTS with\n"
        "a comment justifying it.\n  - " + "\n  - ".join(drifts)
    )


def test_torch_floor_is_strict() -> None:
    """Pin F01 specifically: torch lower bound must be 2.11.0+ in both files."""
    pyp = _read_pyproject_lower_bounds()
    req = _read_requirements_lower_bounds()
    assert "torch" in pyp, "torch missing from pyproject.toml dependencies"
    assert "torch" in req, "torch missing from requirements.txt"
    assert _parse_version(pyp["torch"]) >= (
        2,
        11,
        0,
    ), f"pyproject torch lower bound {pyp['torch']} regressed below 2.11.0"
    assert _parse_version(req["torch"]) >= (
        2,
        11,
        0,
    ), f"requirements torch lower bound {req['torch']} regressed below 2.11.0"


def test_strawberry_floor_is_strict() -> None:
    """Pin F03 specifically: strawberry-graphql lower bound must be 0.312.3+."""
    pyp = _read_pyproject_lower_bounds()
    req = _read_requirements_lower_bounds()
    name = "strawberry-graphql"
    assert name in pyp, f"{name} missing from pyproject.toml dependencies"
    assert name in req, f"{name} missing from requirements.txt"
    assert _parse_version(pyp[name]) >= (
        0,
        312,
        3,
    ), f"pyproject {name} lower bound {pyp[name]} regressed below 0.312.3"
    assert _parse_version(req[name]) >= (
        0,
        312,
        3,
    ), f"requirements {name} lower bound {req[name]} regressed below 0.312.3"


def test_allowlist_is_documented() -> None:
    """Sanity: if the allowlist grows, the test author saw it."""
    assert isinstance(DELIBERATELY_NOT_IN_REQUIREMENTS, frozenset)
    # If you add an entry, assert it remains documented in the source comment.
    assert all(isinstance(x, str) and x for x in DELIBERATELY_NOT_IN_REQUIREMENTS)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
