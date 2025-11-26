"""API registry contract validation tests.

These tests ensure the declarative API registry, documentation exports, and
referenced schemas remain in sync. They help detect accidental contract drift
between the source of truth YAML registry and the generated documentation files
that integrators rely on.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_RESOLVED_REPO_ROOT = REPO_ROOT.resolve()
_REPO_ROOT_PARTS = _RESOLVED_REPO_ROOT.parts
REGISTRY_PATH = REPO_ROOT / "configs/api/registry.yaml"
ROUTES_DOC_PATH = REPO_ROOT / "docs/api/routes.json"
SMOKE_DOC_PATH = REPO_ROOT / "docs/api/smoke_tests.json"


@pytest.fixture(scope="module")
def api_registry() -> dict[str, Any]:
    """Load and cache the canonical API registry configuration."""

    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):  # pragma: no cover - defensive safeguard
        raise TypeError("registry.yaml must deserialize to a mapping")
    return payload


@pytest.fixture(scope="module")
def documented_routes() -> list[dict[str, Any]]:
    """Load the rendered route documentation payload."""

    payload = json.loads(ROUTES_DOC_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):  # pragma: no cover - defensive safeguard
        raise TypeError("routes.json must deserialize to a list")
    return payload


@pytest.fixture(scope="module")
def documented_smoke_tests() -> list[dict[str, Any]]:
    """Load the rendered smoke test documentation payload."""

    payload = json.loads(SMOKE_DOC_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):  # pragma: no cover - defensive safeguard
        raise TypeError("smoke_tests.json must deserialize to a list")
    return payload


def _canonical_schema_reference(value: str | None) -> Path | None:
    """Normalise schema references to a canonical, repository-relative path."""

    if value in (None, ""):
        return None
    raw = str(value).strip()
    if raw in ("", "."):
        return None

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (_RESOLVED_REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()
    normalised = _normalise_repo_relative(candidate)
    return normalised


def _normalise_repo_relative(candidate: Path) -> Path:
    """Return a repository-relative version of ``candidate`` when possible."""

    try:
        return candidate.relative_to(_RESOLVED_REPO_ROOT)
    except ValueError:  # pragma: no cover - indicates reference outside repo
        candidate_parts = candidate.parts
        repo_length = len(_REPO_ROOT_PARTS)
        # Some build systems materialise absolute paths with differing prefixes
        # (for example, /workspace/<project> vs /__w/<project>/<project>). When
        # that happens we search for the repository root suffix within the
        # absolute path and return the remaining tail so that comparisons remain
        # stable across environments. We progressively drop leading components of
        # the resolved repository root so paths like /__w/<repo>/<repo>/docs map
        # back to docs/....
        for drop in range(repo_length):
            repo_suffix = _REPO_ROOT_PARTS[drop:]
            if not repo_suffix:
                continue
            suffix_length = len(repo_suffix)
            for start in range(len(candidate_parts) - suffix_length + 1):
                if candidate_parts[start : start + suffix_length] == repo_suffix:
                    remainder = candidate_parts[start + suffix_length :]
                    if remainder:
                        return Path(*remainder)
                    return Path()
        return candidate


def _collect_schema_paths(entries: Iterable[str | None]) -> set[Path]:
    """Collect normalised schema references from a sequence of entries."""

    discovered: set[Path] = set()
    for entry in entries:
        normalised = _canonical_schema_reference(entry)
        if normalised is not None:
            discovered.add(normalised)
    return discovered


def test_api_registry_routes_have_unique_signatures(
    api_registry: dict[str, Any],
) -> None:
    """Ensure each registry route exposes a unique method/path combination."""

    seen: dict[tuple[str, str], str] = {}
    duplicates: list[str] = []
    for route in api_registry.get("routes", []):
        method = str(route.get("method", "")).upper()
        path = str(route.get("path", ""))
        name = str(route.get("name", "")) or f"{method} {path}"
        signature = (method, path)
        if signature in seen:
            duplicates.append(f"{name} duplicates {seen[signature]}")
        else:
            seen[signature] = name
    assert not duplicates, f"Duplicate API route signatures detected: {duplicates}"


def test_api_registry_routes_match_documentation(
    api_registry: dict[str, Any], documented_routes: list[dict[str, Any]]
) -> None:
    """Verify declarative registry routes align with the generated documentation."""

    registry_routes = {route["name"]: route for route in api_registry.get("routes", [])}
    documented = {route["name"]: route for route in documented_routes}
    assert registry_routes, "No routes discovered in configs/api/registry.yaml"
    assert documented, "No routes discovered in docs/api/routes.json"
    assert registry_routes.keys() == documented.keys(), (
        "Registry routes and documented routes diverge: "
        f"{sorted(registry_routes.keys() ^ documented.keys())}"
    )

    for name, route in registry_routes.items():
        doc = documented[name]
        assert doc["method"].upper() == str(route.get("method", "")).upper()
        assert doc["path"] == route.get("path")
        assert doc.get("scope") == route.get("scope")
        assert doc.get("webhooks", []) == route.get("webhooks", [])

        registry_request = _canonical_schema_reference(route.get("request_schema"))
        registry_response = _canonical_schema_reference(route.get("response_schema"))
        doc_request = _canonical_schema_reference(doc.get("request_schema"))
        doc_response = _canonical_schema_reference(doc.get("response_schema"))
        assert (
            doc_request == registry_request
        ), f"Request schema mismatch for route {name}"
        assert (
            doc_response == registry_response
        ), f"Response schema mismatch for route {name}"


def test_api_registry_smoke_tests_match_documentation(
    api_registry: dict[str, Any], documented_smoke_tests: list[dict[str, Any]]
) -> None:
    """Ensure smoke test scenarios exported to documentation mirror the registry."""

    expected: dict[str, dict[str, Any]] = {}
    for route in api_registry.get("routes", []):
        route_name = route.get("name")
        for smoke in route.get("smoke_tests", []) or []:
            name = smoke.get("name")
            if name is None:
                continue
            if name in expected:
                raise AssertionError(f"Duplicate smoke test name detected: {name}")
            request = smoke.get("request", {}) or {}
            expected[name] = {
                "route": route_name,
                "description": smoke.get("description"),
                "method": request.get("method"),
                "path": request.get("path"),
                "headers": request.get("headers") or {},
                "body": request.get("body"),
                "expected_status": smoke.get("expected_status"),
                "response_schema": smoke.get("response_schema"),
            }

    documented = {entry["name"]: entry for entry in documented_smoke_tests}
    assert expected.keys() == documented.keys(), (
        "Registry smoke tests and documented smoke tests diverge: "
        f"{sorted(expected.keys() ^ documented.keys())}"
    )

    for name, spec in expected.items():
        doc = documented[name]
        assert (
            doc.get("route") == spec["route"]
        ), f"Route mismatch for smoke test {name}"
        assert doc.get("description") == spec["description"]
        assert doc.get("method") == spec["method"], f"HTTP method mismatch for {name}"
        assert doc.get("path") == spec["path"], f"Path mismatch for smoke test {name}"
        assert doc.get("headers", {}) == spec["headers"], f"Header mismatch for {name}"
        assert doc.get("body") == spec["body"], f"Body mismatch for smoke test {name}"
        assert (
            doc.get("expected_status") == spec["expected_status"]
        ), f"Expected status mismatch for smoke test {name}"
        doc_schema = _canonical_schema_reference(doc.get("response_schema"))
        expected_schema = _canonical_schema_reference(spec["response_schema"])
        assert doc_schema == expected_schema, f"Schema mismatch for smoke test {name}"


def test_api_registry_schema_references_exist(
    api_registry: dict[str, Any],
    documented_routes: list[dict[str, Any]],
    documented_smoke_tests: list[dict[str, Any]],
) -> None:
    """Validate that every referenced schema file exists and contains JSON."""

    referenced: set[Path] = set()

    def extract(entries: Iterable[dict[str, Any]]) -> None:
        for entry in entries:
            referenced.update(
                _collect_schema_paths(
                    (
                        entry.get("request_schema"),
                        entry.get("response_schema"),
                    )
                )
            )

    extract(api_registry.get("routes", []))
    extract(documented_routes)
    referenced.update(
        _collect_schema_paths(
            entry.get("response_schema") for entry in documented_smoke_tests
        )
    )

    assert referenced, "No schema references discovered across API registry artifacts"

    for relative_path in sorted(referenced):
        absolute = (REPO_ROOT / relative_path).resolve()
        assert absolute.exists(), f"Schema reference missing on disk: {relative_path}"
        payload = json.loads(absolute.read_text(encoding="utf-8"))
        assert isinstance(
            payload, dict
        ), f"Schema payload must be a JSON object: {relative_path}"
        assert payload, f"Schema payload should not be empty: {relative_path}"
        assert (
            "$schema" in payload or "type" in payload
        ), f"Schema metadata is incomplete for {relative_path}"
