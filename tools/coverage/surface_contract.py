#!/usr/bin/env python3
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class SurfaceTarget:
    paths: tuple[str, ...]
    short_term: float
    mid_term: float
    final: float
    claim_risk: str
    rationale: str


@dataclass(frozen=True)
class CoverageWeights:
    divergence: float
    convergence: float


@dataclass(frozen=True)
class CoverageTargets:
    source_path: Path
    global_thresholds: dict[str, float]
    surfaces: dict[str, SurfaceTarget]
    weights: CoverageWeights | None = None


_REQUIRED_GLOBAL = ("final_aspirational_gate", "current_release_gate", "diff_coverage_gate")
_REQUIRED_SURFACE = ("paths", "short_term", "mid_term", "final", "claim_risk", "rationale")


def _as_float(name: str, value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise ValueError(f"{name} must be numeric")


def load_coverage_targets(path: Path) -> CoverageTargets:
    if not path.exists():
        raise FileNotFoundError(path)
    doc = tomllib.loads(path.read_text(encoding="utf-8"))
    if "global" not in doc:
        raise ValueError("Missing [global] section")
    if "surfaces" not in doc:
        raise ValueError("Missing [surfaces] section")

    global_thresholds: dict[str, float] = {}
    for key in _REQUIRED_GLOBAL:
        if key not in doc["global"]:
            raise ValueError(f"Missing global threshold: {key}")
        global_thresholds[key] = _as_float(key, doc["global"][key])

    surfaces: dict[str, SurfaceTarget] = {}
    for name, raw in doc["surfaces"].items():
        for field in _REQUIRED_SURFACE:
            if field not in raw:
                raise ValueError(f"Missing surface field '{field}' for '{name}'")
        raw_paths = raw["paths"]
        if (
            not isinstance(raw_paths, list)
            or not raw_paths
            or not all(isinstance(p, str) for p in raw_paths)
        ):
            raise ValueError(f"Surface '{name}' must define non-empty string paths")
        surfaces[name] = SurfaceTarget(
            paths=tuple(raw_paths),
            short_term=_as_float(f"{name}.short_term", raw["short_term"]),
            mid_term=_as_float(f"{name}.mid_term", raw["mid_term"]),
            final=_as_float(f"{name}.final", raw["final"]),
            claim_risk=str(raw["claim_risk"]),
            rationale=str(raw["rationale"]),
        )

    weights = None
    if "weights" in doc:
        raw_weights = doc["weights"]
        if "divergence" not in raw_weights or "convergence" not in raw_weights:
            raise ValueError("[weights] must define divergence and convergence")
        weights = CoverageWeights(
            divergence=_as_float("weights.divergence", raw_weights["divergence"]),
            convergence=_as_float("weights.convergence", raw_weights["convergence"]),
        )

    return CoverageTargets(
        source_path=path, global_thresholds=global_thresholds, surfaces=surfaces, weights=weights
    )


def _normalize_repo_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _prefix_matches(file_path: str, prefix: str) -> bool:
    normalized_prefix = _normalize_repo_path(prefix)
    if not normalized_prefix:
        return False
    if normalized_prefix.endswith("/"):
        return file_path.startswith(normalized_prefix)
    return file_path == normalized_prefix or file_path.startswith(f"{normalized_prefix}/")


def is_colocated_test_file(file_path: str) -> bool:
    """True for a test file that physically lives inside a production package.

    Co-located suites (e.g. ``analytics/signals/tests/test_igs_core.py``,
    ``core/neuro/tests/__init__.py``) are run as a second ``--cov-append``
    invocation so they exercise release surface. But because they sit UNDER a
    ``[run] source`` root, coverage.py records their own line execution, and the
    longest-prefix bucketing in :func:`map_file_to_surface` would otherwise
    credit those *test* bodies as covered *production* lines — self-inflating the
    measured surface. Excluding them here keeps the measured surface honest: the
    test files still EXECUTE production code (which is what we want to count),
    they just stop counting themselves.

    The match is deliberately narrow — only canonical pytest file shapes under a
    directory named exactly ``tests`` — so genuine production modules that merely
    contain the substring "test" are never excluded.
    """
    normalized = _normalize_repo_path(file_path)
    if "/tests/" not in normalized:
        return False
    basename = normalized.rsplit("/", 1)[-1]
    return (
        basename == "__init__.py"
        or basename == "conftest.py"
        or (basename.startswith("test_") and basename.endswith(".py"))
        or basename.endswith("_test.py")
    )


def map_file_to_surface(file_path: str, targets: CoverageTargets) -> str | None:
    normalized = _normalize_repo_path(file_path)

    # Co-located test files live under a source root but must NOT be counted as
    # production surface (they would credit test-code as covered prod lines).
    if is_colocated_test_file(normalized):
        return None

    best_len = -1
    best_surface: str | None = None
    for surface, cfg in targets.surfaces.items():
        for prefix in cfg.paths:
            normalized_prefix = _normalize_repo_path(prefix)
            if not _prefix_matches(normalized, normalized_prefix):
                continue
            match_len = len(normalized_prefix.rstrip("/"))
            if match_len > best_len:
                best_len = match_len
                best_surface = surface

    return best_surface


def list_unmapped_files(file_paths: Iterable[str], targets: CoverageTargets) -> list[str]:
    return sorted(p for p in file_paths if map_file_to_surface(p, targets) is None)


def validate_target_contract(targets: CoverageTargets) -> list[str]:
    errors: list[str] = []

    for key in _REQUIRED_GLOBAL:
        value = targets.global_thresholds.get(key)
        if value is None:
            errors.append(f"Missing global threshold: {key}")
            continue
        if value < 0 or value > 100:
            errors.append(f"Global threshold '{key}' out of range [0,100]: {value}")

    for name, surface in targets.surfaces.items():
        for threshold_name, value in (
            ("short_term", surface.short_term),
            ("mid_term", surface.mid_term),
            ("final", surface.final),
        ):
            if value < 0 or value > 100:
                errors.append(
                    f"Surface '{name}' threshold '{threshold_name}' out of range [0,100]: {value}"
                )

        if not (surface.short_term <= surface.mid_term <= surface.final):
            errors.append(
                f"Surface '{name}' threshold order invalid: short_term <= mid_term <= final is required"
            )

        if not surface.claim_risk.strip():
            errors.append(f"Surface '{name}' missing claim_risk")
        if not surface.rationale.strip():
            errors.append(f"Surface '{name}' missing rationale")

    if targets.weights is not None:
        if not (0.0 <= targets.weights.divergence <= 1.0):
            errors.append(f"weights.divergence out of range [0,1]: {targets.weights.divergence}")
        if not (0.0 <= targets.weights.convergence <= 1.0):
            errors.append(f"weights.convergence out of range [0,1]: {targets.weights.convergence}")
        total = targets.weights.divergence + targets.weights.convergence
        if abs(total - 1.0) > 1e-9:
            errors.append(f"weights must sum to 1.0, got {total}")

    return errors
