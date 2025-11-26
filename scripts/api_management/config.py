"""Configuration models for API governance workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping

import yaml


@dataclass(slots=True, frozen=True)
class Maintainer:
    """Metadata describing a platform maintainer."""

    name: str
    contact: str


@dataclass(slots=True, frozen=True)
class CompatibilityDefaults:
    """Default compatibility guarantees for the public API."""

    default: str
    support_window_days: int


@dataclass(slots=True, frozen=True)
class ApiMetadata:
    """Top-level metadata associated with the API registry."""

    service: str
    release: str
    docs_base_url: str
    default_signature_algorithm: str
    idempotency_header: str
    maintainers: tuple[Maintainer, ...]
    compatibility: CompatibilityDefaults


@dataclass(slots=True, frozen=True)
class EnvironmentConfig:
    """Base URL metadata for a deployed environment."""

    name: str
    base_url: str


@dataclass(slots=True, frozen=True)
class CachePolicy:
    """Cache-control guidance for a route."""

    strategy: str
    max_age: int
    stale_while_revalidate: int


@dataclass(slots=True, frozen=True)
class ThrottlePolicy:
    """Short term throttling characteristics for a route."""

    burst: int
    period_seconds: int


@dataclass(slots=True, frozen=True)
class RateLimitPolicy:
    """Rate limit envelope for a route."""

    per_minute: int | None
    per_hour: int | None
    per_day: int | None


@dataclass(slots=True, frozen=True)
class SignaturePolicy:
    """Transport-level signature requirements."""

    required: bool
    algorithm: str
    header: str
    version: str | None = None


@dataclass(slots=True, frozen=True)
class IdempotencyPolicy:
    """Idempotency enforcement policy."""

    required: bool
    header: str | None
    ttl_seconds: int | None


@dataclass(slots=True, frozen=True)
class SimulatorExample:
    """Example payload used by the response simulator."""

    status_code: int
    description: str
    body: Mapping[str, object]


@dataclass(slots=True, frozen=True)
class SmokeTestRequest:
    """HTTP request template for smoke tests."""

    method: str
    path: str
    headers: Mapping[str, str]
    body: Mapping[str, object] | None = None


@dataclass(slots=True, frozen=True)
class SmokeTest:
    """Definition of a smoke test derived from the registry."""

    name: str
    description: str
    request: SmokeTestRequest
    expected_status: int
    response_schema: Path


@dataclass(slots=True, frozen=True)
class ApiRoute:
    """Concrete API route definition."""

    name: str
    method: str
    path: str
    summary: str
    description: str
    scope: str
    tags: tuple[str, ...]
    cache: CachePolicy
    throttle: ThrottlePolicy
    rate_limit: RateLimitPolicy
    request_schema: Path | None
    response_schema: Path
    signatures: SignaturePolicy
    idempotency: IdempotencyPolicy
    webhooks: tuple[str, ...]
    simulators: tuple[SimulatorExample, ...]
    smoke_tests: tuple[SmokeTest, ...]


@dataclass(slots=True, frozen=True)
class WebhookContract:
    """Webhook contract derived from the registry."""

    name: str
    summary: str
    method: str
    retry_max_attempts: int
    retry_backoff_seconds: int
    signature_header: str
    signature_algorithm: str
    signature_version: str
    schema: Path


@dataclass(slots=True, frozen=True)
class MigrationNotice:
    """Migration notice surfaced to clients."""

    identifier: str
    applies_to: tuple[str, ...]
    summary: str
    effective_on: str
    instructions_url: str


@dataclass(slots=True, frozen=True)
class DeprecationNotice:
    """Deprecation announcement for a route."""

    route: str
    sunset_date: str
    reason: str
    replacement: str | None
    status: str


@dataclass(slots=True, frozen=True)
class ChangelogEntry:
    """Versioned change log for the API."""

    version: str
    released_at: str
    summary: str
    compatibility: str
    highlights: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class CompatibilityGuard:
    """Route-specific compatibility requirement."""

    route: str
    minimum_client_version: str
    status: str
    comments: str | None


@dataclass(slots=True, frozen=True)
class ApiRegistry:
    """Aggregate API registry representation."""

    metadata: ApiMetadata
    environments: tuple[EnvironmentConfig, ...]
    routes: tuple[ApiRoute, ...]
    webhooks: tuple[WebhookContract, ...]
    compatibility: tuple[CompatibilityGuard, ...]
    migrations: tuple[MigrationNotice, ...]
    deprecations: tuple[DeprecationNotice, ...]
    changelog: tuple[ChangelogEntry, ...]

    def route_map(self) -> Mapping[str, ApiRoute]:
        return {route.name: route for route in self.routes}

    def webhook_map(self) -> Mapping[str, WebhookContract]:
        return {webhook.name: webhook for webhook in self.webhooks}


def _as_path(value: str | None, base_dir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.is_absolute():
        return (base_dir / path).resolve()
    return path


def _require(mapping: Mapping[str, object], key: str) -> object:
    try:
        return mapping[key]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise KeyError(
            f"Missing required key '{key}' in registry configuration"
        ) from exc


def _load_metadata(raw: Mapping[str, object]) -> ApiMetadata:
    compatibility_raw = _require(raw, "compatibility")
    compat = CompatibilityDefaults(
        default=str(_require(compatibility_raw, "default")),
        support_window_days=int(_require(compatibility_raw, "support_window_days")),
    )
    maintainers = tuple(
        Maintainer(name=str(item["name"]), contact=str(item["contact"]))
        for item in raw.get("maintainers", [])
    )
    return ApiMetadata(
        service=str(_require(raw, "service")),
        release=str(_require(raw, "release")),
        docs_base_url=str(_require(raw, "docs_base_url")),
        default_signature_algorithm=str(_require(raw, "default_signature_algorithm")),
        idempotency_header=str(_require(raw, "idempotency_header")),
        maintainers=maintainers,
        compatibility=compat,
    )


def _load_environment(raw: Mapping[str, object]) -> EnvironmentConfig:
    return EnvironmentConfig(
        name=str(_require(raw, "name")), base_url=str(_require(raw, "base_url"))
    )


def _load_cache(raw: Mapping[str, object]) -> CachePolicy:
    return CachePolicy(
        strategy=str(_require(raw, "strategy")),
        max_age=int(_require(raw, "max_age")),
        stale_while_revalidate=int(_require(raw, "stale_while_revalidate")),
    )


def _load_throttle(raw: Mapping[str, object]) -> ThrottlePolicy:
    return ThrottlePolicy(
        burst=int(_require(raw, "burst")),
        period_seconds=int(_require(raw, "period_seconds")),
    )


def _load_rate_limit(raw: Mapping[str, object]) -> RateLimitPolicy:
    return RateLimitPolicy(
        per_minute=(
            int(raw["per_minute"]) if raw.get("per_minute") is not None else None
        ),
        per_hour=int(raw["per_hour"]) if raw.get("per_hour") is not None else None,
        per_day=int(raw["per_day"]) if raw.get("per_day") is not None else None,
    )


def _load_signature(raw: Mapping[str, object]) -> SignaturePolicy:
    return SignaturePolicy(
        required=bool(_require(raw, "required")),
        algorithm=str(_require(raw, "algorithm")),
        header=str(_require(raw, "header")),
        version=str(raw.get("version")) if raw.get("version") is not None else None,
    )


def _load_idempotency(raw: Mapping[str, object]) -> IdempotencyPolicy:
    return IdempotencyPolicy(
        required=bool(_require(raw, "required")),
        header=str(raw.get("header")) if raw.get("header") is not None else None,
        ttl_seconds=(
            int(raw["ttl_seconds"]) if raw.get("ttl_seconds") is not None else None
        ),
    )


def _load_simulator(raw: Mapping[str, object]) -> SimulatorExample:
    return SimulatorExample(
        status_code=int(_require(raw, "status_code")),
        description=str(_require(raw, "description")),
        body=dict(raw.get("body", {})),
    )


def _load_smoke_test(raw: Mapping[str, object], base_dir: Path) -> SmokeTest:
    request_raw = _require(raw, "request")
    headers = {
        str(key): str(value)
        for key, value in dict(request_raw.get("headers", {})).items()
    }
    body = request_raw.get("body")
    request = SmokeTestRequest(
        method=str(_require(request_raw, "method")),
        path=str(_require(request_raw, "path")),
        headers=headers,
        body=dict(body) if isinstance(body, Mapping) else None,
    )
    schema = _as_path(str(_require(raw, "response_schema")), base_dir)
    if schema is None:  # pragma: no cover - defensive fallback
        raise ValueError("Smoke test response schema cannot be null")
    return SmokeTest(
        name=str(_require(raw, "name")),
        description=str(_require(raw, "description")),
        request=request,
        expected_status=int(_require(raw, "expected_status")),
        response_schema=schema,
    )


def _load_route(raw: Mapping[str, object], base_dir: Path) -> ApiRoute:
    cache = _load_cache(_require(raw, "cache"))
    throttle = _load_throttle(_require(raw, "throttle"))
    rate_limit = _load_rate_limit(_require(raw, "rate_limit"))
    signatures = _load_signature(_require(raw, "signatures"))
    idempotency = _load_idempotency(_require(raw, "idempotency"))
    request_schema = _as_path(raw.get("request_schema"), base_dir)
    response_schema = _as_path(_require(raw, "response_schema"), base_dir)
    simulators = tuple(_load_simulator(item) for item in raw.get("simulators", []))
    smoke_tests = tuple(
        _load_smoke_test(item, base_dir) for item in raw.get("smoke_tests", [])
    )
    return ApiRoute(
        name=str(_require(raw, "name")),
        method=str(_require(raw, "method")),
        path=str(_require(raw, "path")),
        summary=str(_require(raw, "summary")),
        description=str(_require(raw, "description")),
        scope=str(_require(raw, "scope")),
        tags=tuple(str(tag) for tag in raw.get("tags", [])),
        cache=cache,
        throttle=throttle,
        rate_limit=rate_limit,
        request_schema=request_schema,
        response_schema=response_schema if response_schema is not None else Path(),
        signatures=signatures,
        idempotency=idempotency,
        webhooks=tuple(str(name) for name in raw.get("webhooks", [])),
        simulators=simulators,
        smoke_tests=smoke_tests,
    )


def _load_webhook(raw: Mapping[str, object], base_dir: Path) -> WebhookContract:
    delivery = _require(raw, "delivery")
    retry_policy = _require(delivery, "retry_policy")
    signature = _require(delivery, "signature")
    schema = _as_path(str(_require(raw, "schema")), base_dir)
    if schema is None:  # pragma: no cover - defensive fallback
        raise ValueError("Webhook schema cannot be null")
    return WebhookContract(
        name=str(_require(raw, "name")),
        summary=str(_require(raw, "summary")),
        method=str(_require(raw, "method")),
        retry_max_attempts=int(_require(retry_policy, "max_attempts")),
        retry_backoff_seconds=int(_require(retry_policy, "backoff_seconds")),
        signature_header=str(_require(signature, "header")),
        signature_algorithm=str(_require(signature, "algorithm")),
        signature_version=str(_require(signature, "version")),
        schema=schema,
    )


def _load_migration(raw: Mapping[str, object]) -> MigrationNotice:
    applies = tuple(str(value) for value in raw.get("applies_to", []))
    return MigrationNotice(
        identifier=str(_require(raw, "id")),
        applies_to=applies,
        summary=str(_require(raw, "summary")),
        effective_on=str(_require(raw, "effective_on")),
        instructions_url=str(_require(raw, "instructions_url")),
    )


def _load_deprecation(raw: Mapping[str, object]) -> DeprecationNotice:
    return DeprecationNotice(
        route=str(_require(raw, "route")),
        sunset_date=str(_require(raw, "sunset_date")),
        reason=str(_require(raw, "reason")),
        replacement=(
            str(raw.get("replacement")) if raw.get("replacement") is not None else None
        ),
        status=str(_require(raw, "status")),
    )


def _load_changelog_entry(raw: Mapping[str, object]) -> ChangelogEntry:
    return ChangelogEntry(
        version=str(_require(raw, "version")),
        released_at=str(_require(raw, "released_at")),
        summary=str(_require(raw, "summary")),
        compatibility=str(_require(raw, "compatibility")),
        highlights=tuple(str(item) for item in raw.get("highlights", [])),
    )


def _load_compatibility(raw: Mapping[str, object]) -> CompatibilityGuard:
    return CompatibilityGuard(
        route=str(_require(raw, "route")),
        minimum_client_version=str(_require(raw, "minimum_client_version")),
        status=str(_require(raw, "status")),
        comments=str(raw.get("comments")) if raw.get("comments") is not None else None,
    )


def load_registry(path: Path, *, repo_root: Path | None = None) -> ApiRegistry:
    """Load an API registry definition from *path*."""

    data = yaml.safe_load(path.read_text())
    if not isinstance(data, MutableMapping):  # pragma: no cover - defensive guard
        raise ValueError("Registry configuration must be a mapping")

    base_dir = repo_root or path.resolve().parent.parent

    metadata = _load_metadata(_require(data, "metadata"))
    environments = tuple(
        _load_environment(item) for item in data.get("environments", [])
    )
    routes = tuple(_load_route(item, base_dir) for item in data.get("routes", []))
    webhooks = tuple(_load_webhook(item, base_dir) for item in data.get("webhooks", []))
    compatibility = tuple(
        _load_compatibility(item) for item in data.get("compatibility", [])
    )
    migrations = tuple(_load_migration(item) for item in data.get("migrations", []))
    deprecations = tuple(
        _load_deprecation(item) for item in data.get("deprecations", [])
    )
    changelog = tuple(_load_changelog_entry(item) for item in data.get("changelog", []))

    return ApiRegistry(
        metadata=metadata,
        environments=environments,
        routes=routes,
        webhooks=webhooks,
        compatibility=compatibility,
        migrations=migrations,
        deprecations=deprecations,
        changelog=changelog,
    )
