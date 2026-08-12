# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Physical-law catalog loader, registry, and ``@law`` witness decorator.

Philosophy
----------
A test is not a line-coverage artefact; it is a *mathematical witness* that a
specific physical law of GeoSync holds in code. Every witness binds itself to
a law by dotted id (e.g. ``kuramoto.subcritical_finite_size``) via the ``@law``
decorator. The binding is checked at collection time by ``tools/validate_tests``
which:

1. rejects witnesses that reference a non-existent ``law_id``;
2. rejects magic-literal asserts that cannot be traced back to the law's
   ``tolerance`` / ``variables`` fields;
3. reports *physical-law-coverage* — the fraction of laws in the catalog that
   have at least one registered witness of sufficient statistical power.

This module is deliberately dependency-light: only ``pyyaml`` (already in
``requirements`` via ``pytest-cov`` config) and the Python stdlib.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

try:
    import yaml  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover - plumbed by env, not tests
    raise RuntimeError(
        "physics_contracts requires PyYAML. Install via `pip install pyyaml`."
    ) from exc


_CATALOG_PATH = Path(__file__).with_name("catalog.yaml")


@dataclass(frozen=True, slots=True)
class Law:
    """A single physical law drawn from ``catalog.yaml``.

    Fields mirror the YAML schema one-to-one so downstream tools can render,
    diff, and validate laws without re-parsing YAML.
    """

    id: str
    module: str
    statement: str
    formula: str
    variables: dict[str, str]
    tolerance: str
    validity: str
    source: str
    severity: str  # "block" | "warn"

    def is_blocking(self) -> bool:
        return self.severity == "block"


@dataclass
class _WitnessRecord:
    """Metadata captured by the ``@law`` decorator at import time."""

    law_id: str
    qualname: str
    module: str
    kwargs: dict[str, Any] = field(default_factory=dict)


# Module-global registry. Populated by ``@law``; consumed by validate_tests and
# the CI gate. We intentionally keep it as a plain dict to avoid import-order
# surprises when tests are collected under different rootdirs.
WITNESS_REGISTRY: dict[str, list[_WitnessRecord]] = {}


class LawViolationError(AssertionError):
    """Raised when a witness helper detects a violation of its bound law.

    Subclasses ``AssertionError`` so pytest reports it as a normal test
    failure while still being distinguishable by type for downstream tooling.
    """

    def __init__(self, law_id: str, message: str) -> None:
        super().__init__(f"[{law_id}] {message}")
        self.law_id = law_id


def load_catalog(path: Path | None = None) -> dict[str, Law]:
    """Parse ``catalog.yaml`` into a ``{law_id: Law}`` mapping.

    Kept as a free function (not cached) so tools can point at alternative
    catalogs during validation (e.g. the tool's unit tests use a fixture
    catalog). Production callers should memoise the result themselves.
    """

    target = path or _CATALOG_PATH
    with target.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict) or "laws" not in raw:
        raise ValueError(f"{target}: missing top-level 'laws' list")

    catalog: dict[str, Law] = {}
    for entry in raw["laws"]:
        law_obj = Law(
            id=entry["id"],
            module=entry["module"],
            statement=entry["statement"],
            formula=entry["formula"],
            variables=dict(entry.get("variables", {})),
            tolerance=entry["tolerance"],
            validity=entry["validity"],
            source=entry["source"],
            severity=entry.get("severity", "block"),
        )
        if law_obj.id in catalog:
            raise ValueError(f"duplicate law id in catalog: {law_obj.id}")
        catalog[law_obj.id] = law_obj
    return catalog


# Lazily-initialised singleton. Only touched when someone calls ``get_law``.
_CATALOG_CACHE: dict[str, Law] | None = None


def get_law(law_id: str) -> Law:
    """Return the ``Law`` with the given id, loading the catalog on first use."""

    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        _CATALOG_CACHE = load_catalog()
    try:
        return _CATALOG_CACHE[law_id]
    except KeyError as exc:
        known = ", ".join(sorted(_CATALOG_CACHE))
        raise KeyError(f"unknown law_id={law_id!r}. Known: {known}") from exc


def law(law_id: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: bind a pytest function to a physical law.

    Usage::

        @law("kuramoto.subcritical_finite_size", N=1024, trials=200)
        def test_subcritical_order_parameter():
            ...

    Behaviour:
    - Resolves the law eagerly at import time and raises ``KeyError`` if the
      id is unknown. This turns typos into import errors, caught by collection.
    - Records a ``_WitnessRecord`` in ``WITNESS_REGISTRY[law_id]`` for the CI
      gate to audit. The record includes the test qualname, its defining
      module, and any keyword arguments the author chose to declare (e.g. the
      N / trials used for the scaling witness — these arguments are exposed
      to ``tools/validate_tests`` so it can check that the declared statistics
      actually match what the test runs).
    - Attaches the resolved ``Law`` to the wrapped function as ``__law__`` so
      tests that want to read tolerances off the law can do so without a
      second catalog lookup.
    """

    resolved = get_law(law_id)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        record = _WitnessRecord(
            law_id=law_id,
            qualname=fn.__qualname__,
            module=fn.__module__,
            kwargs=dict(kwargs),
        )
        WITNESS_REGISTRY.setdefault(law_id, []).append(record)

        @functools.wraps(fn)
        def wrapper(*args: Any, **fkwargs: Any) -> Any:
            return fn(*args, **fkwargs)

        wrapper.__law__ = resolved  # type: ignore[attr-defined]
        wrapper.__law_kwargs__ = dict(kwargs)  # type: ignore[attr-defined]
        return wrapper

    return decorator


def iter_witnesses() -> Iterable[_WitnessRecord]:
    """Flatten ``WITNESS_REGISTRY`` into a stable iteration order."""

    for law_id in sorted(WITNESS_REGISTRY):
        for record in WITNESS_REGISTRY[law_id]:
            yield record


def coverage_report(catalog: dict[str, Law] | None = None) -> dict[str, Any]:
    """Compute physical-law-coverage metrics for the CI gate.

    Returns a dict with:
        laws_total:         number of laws in the catalog
        laws_witnessed:     number with ≥ 1 registered witness
        laws_unwitnessed:   sorted list of law ids with no witness
        blocking_missing:   sorted list of blocking laws without a witness
        coverage_fraction:  laws_witnessed / laws_total
    """

    cat = catalog or load_catalog()
    witnessed = {lid for lid in WITNESS_REGISTRY if WITNESS_REGISTRY[lid]}
    unwitnessed = sorted(set(cat) - witnessed)
    blocking_missing = sorted(lid for lid in unwitnessed if cat[lid].is_blocking())
    return {
        "laws_total": len(cat),
        "laws_witnessed": len(witnessed & set(cat)),
        "laws_unwitnessed": unwitnessed,
        "blocking_missing": blocking_missing,
        "coverage_fraction": (len(witnessed & set(cat)) / len(cat)) if cat else 0.0,
    }
