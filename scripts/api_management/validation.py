# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validation helpers for API governance artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from .config import ApiRegistry, ApiRoute, WebhookContract


@dataclass(slots=True)
class ApiValidationReport:
    """Structured summary of registry validation checks."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_check(self, message: str) -> None:
        self.checks.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if not self.errors:
            return
        details = "\n - ".join(self.errors)
        raise ValueError(f"API registry validation failed:\n - {details}")


class _SchemaValidatorCache:
    """Cache and reuse compiled JSON schema validators."""

    def __init__(self) -> None:
        self._validators: dict[Path, Draft202012Validator] = {}

    def validator_for(self, schema_path: Path) -> Draft202012Validator:
        try:
            return self._validators[schema_path]
        except KeyError:
            data = json.loads(schema_path.read_text())
            validator = Draft202012Validator(data)
            self._validators[schema_path] = validator
            return validator


def validate_registry(registry: ApiRegistry) -> ApiValidationReport:
    """Validate the registry contents and return a structured report."""

    report = ApiValidationReport()
    schema_cache = _SchemaValidatorCache()

    _validate_metadata(registry, report)
    _validate_routes(registry, report, schema_cache)
    _validate_webhooks(registry, report)
    _validate_cross_references(registry, report)
    _validate_changelog(registry, report)

    return report


def _validate_metadata(registry: ApiRegistry, report: ApiValidationReport) -> None:
    metadata = registry.metadata
    if metadata.compatibility.support_window_days <= 0:
        report.add_error("Support window must be positive.")
    if not metadata.maintainers:
        report.add_warning("No maintainers are defined for the API metadata.")
    if not metadata.docs_base_url.startswith("http"):
        report.add_warning("Documentation base URL should be an absolute HTTP(S) URL.")


def _validate_routes(
    registry: ApiRegistry,
    report: ApiValidationReport,
    schema_cache: _SchemaValidatorCache,
) -> None:
    seen: set[tuple[str, str]] = set()
    for route in registry.routes:
        key = (route.method.upper(), route.path)
        if key in seen:
            report.add_error(f"Duplicate route detected for {route.method} {route.path}.")
        else:
            seen.add(key)

        _validate_route_policies(route, report)
        _validate_route_schemas(route, report)

        if route.simulators:
            for simulator in route.simulators:
                try:
                    validator = schema_cache.validator_for(route.response_schema)
                    validator.validate(simulator.body)
                    report.add_check(
                        f"Simulator for {route.name} ({simulator.status_code}) matches {route.response_schema.name}."
                    )
                except FileNotFoundError:
                    report.add_error(
                        f"Missing response schema for route {route.name}: {route.response_schema}."
                    )
                except JsonSchemaValidationError as exc:
                    report.add_error(
                        f"Simulator payload for {route.name} ({simulator.status_code}) violates schema: {exc.message}."
                    )
        else:
            report.add_warning(f"Route {route.name} lacks response simulators.")

        if route.smoke_tests:
            for test in route.smoke_tests:
                if test.expected_status < 100 or test.expected_status > 599:
                    report.add_error(
                        f"Smoke test {test.name} for {route.name} has invalid status {test.expected_status}."
                    )
                if not test.response_schema.exists():
                    report.add_error(
                        f"Smoke test {test.name} references missing schema {test.response_schema}."
                    )
            report.add_check(f"Route {route.name} exposes {len(route.smoke_tests)} smoke test(s).")
        else:
            report.add_warning(f"Route {route.name} does not declare smoke tests.")


def _validate_route_policies(route: ApiRoute, report: ApiValidationReport) -> None:
    if route.cache.max_age < 0 or route.cache.stale_while_revalidate < 0:
        report.add_error(
            f"Cache max-age/stale-while-revalidate must be non-negative for {route.name}."
        )
    if route.throttle.burst <= 0 or route.throttle.period_seconds <= 0:
        report.add_error(f"Throttle policy must be positive for {route.name}.")
    for name, value in (
        ("per_minute", route.rate_limit.per_minute),
        ("per_hour", route.rate_limit.per_hour),
        ("per_day", route.rate_limit.per_day),
    ):
        if value is not None and value <= 0:
            report.add_error(f"Rate limit {name} must be positive for {route.name}.")
    if (
        route.rate_limit.per_minute is None
        and route.rate_limit.per_hour is None
        and route.rate_limit.per_day is None
    ):
        report.add_warning(f"Route {route.name} does not specify rate limits.")
    if route.idempotency.required and not route.idempotency.header:
        report.add_error(f"Route {route.name} requires idempotency but no header is configured.")
    if route.idempotency.ttl_seconds is not None and route.idempotency.ttl_seconds <= 0:
        report.add_error(f"Idempotency TTL must be positive when provided for {route.name}.")
    if route.signatures.required and not route.signatures.header:
        report.add_error(f"Route {route.name} requires signatures but no header is defined.")
    if not route.signatures.algorithm:
        report.add_warning(f"Signature algorithm missing for {route.name}.")


def _validate_route_schemas(route: ApiRoute, report: ApiValidationReport) -> None:
    if route.request_schema and not route.request_schema.exists():
        report.add_error(
            f"Route {route.name} references missing request schema {route.request_schema}."
        )
    if not route.response_schema.exists():
        report.add_error(
            f"Route {route.name} references missing response schema {route.response_schema}."
        )


def _validate_webhooks(registry: ApiRegistry, report: ApiValidationReport) -> None:
    names = {webhook.name for webhook in registry.webhooks}
    if len(names) != len(registry.webhooks):
        report.add_error("Webhook names must be unique.")
    for webhook in registry.webhooks:
        _validate_webhook_contract(webhook, report)


def _validate_webhook_contract(webhook: WebhookContract, report: ApiValidationReport) -> None:
    if not webhook.schema.exists():
        report.add_error(f"Webhook {webhook.name} references missing schema {webhook.schema}.")
    if webhook.retry_max_attempts <= 0 or webhook.retry_backoff_seconds <= 0:
        report.add_error(f"Webhook {webhook.name} retry policy must be positive.")
    if not webhook.signature_header:
        report.add_error(f"Webhook {webhook.name} signature header is empty.")
    if not webhook.signature_algorithm:
        report.add_warning(f"Webhook {webhook.name} signature algorithm is not specified.")


def _validate_cross_references(registry: ApiRegistry, report: ApiValidationReport) -> None:
    route_names = {route.name for route in registry.routes}
    webhook_names = {item.name for item in registry.webhooks}
    for route in registry.routes:
        for webhook in route.webhooks:
            if webhook not in webhook_names:
                report.add_error(f"Route {route.name} references unknown webhook {webhook}.")
    for guard in registry.compatibility:
        if guard.route not in route_names:
            report.add_error(f"Compatibility guard references unknown route {guard.route}.")
    for migration in registry.migrations:
        for route in migration.applies_to:
            if route not in route_names:
                report.add_error(
                    f"Migration {migration.identifier} references unknown route {route}."
                )
    for notice in registry.deprecations:
        if notice.route not in route_names:
            report.add_error(f"Deprecation references unknown route {notice.route}.")


def _validate_changelog(registry: ApiRegistry, report: ApiValidationReport) -> None:
    versions = [entry.version for entry in registry.changelog]
    if len(versions) != len(set(versions)):
        report.add_error("Duplicate versions detected in changelog.")
    if versions and registry.metadata.release not in versions:
        report.add_warning(
            f"Metadata release {registry.metadata.release} not found in changelog entries ({', '.join(versions)})."
        )
    if sorted(versions, reverse=True) != versions:
        report.add_warning("Changelog entries are not sorted in descending order.")
