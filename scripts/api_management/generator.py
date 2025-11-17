"""Artifact generation helpers for API governance."""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .config import ApiRegistry, ApiRoute, RateLimitPolicy


@dataclass(slots=True)
class GeneratedArtifacts:
    """Collection of files emitted by the artifact generator."""

    python_client: Path
    typescript_client: Path
    overview: Path
    routes_index: Path
    webhooks_doc: Path
    smoke_tests_index: Path
    changelog: Path
    deprecations: Path
    migrations: Path
    visualization: Path
    examples: tuple[Path, ...]


class ApiArtifactGenerator:
    """Generate SDKs, documentation, and governance artifacts from the registry."""

    def __init__(self, registry: ApiRegistry, *, repo_root: Path) -> None:
        self._registry = registry
        self._repo_root = repo_root

    # ------------------------------------------------------------------
    # Public orchestration methods
    # ------------------------------------------------------------------
    def generate(
        self,
        *,
        clients_dir: Path,
        docs_dir: Path,
        examples_dir: Path,
        visualization_path: Path | None = None,
    ) -> GeneratedArtifacts:
        """Generate all supported artifacts and return their locations."""

        clients_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.mkdir(parents=True, exist_ok=True)
        examples_dir.mkdir(parents=True, exist_ok=True)

        python_client = self._generate_python_client(
            clients_dir / "tradepulse_client.py"
        )
        typescript_client = self._generate_typescript_client(
            clients_dir / "tradepulseClient.ts"
        )
        overview = self._generate_overview(docs_dir / "overview.md")
        routes_index = self._generate_route_index(docs_dir / "routes.json")
        webhooks_doc = self._generate_webhook_doc(docs_dir / "webhooks.md")
        smoke_tests_index = self._generate_smoke_tests_index(
            docs_dir / "smoke_tests.json"
        )
        changelog = self._generate_changelog(docs_dir / "CHANGELOG.md")
        deprecations = self._generate_deprecations(docs_dir / "deprecations.md")
        migrations = self._generate_migrations(docs_dir / "migrations.md")
        visualization_target = visualization_path or (docs_dir / "registry.dot")
        visualization = self._generate_visualization(visualization_target)
        examples = self._generate_examples(examples_dir)

        return GeneratedArtifacts(
            python_client=python_client,
            typescript_client=typescript_client,
            overview=overview,
            routes_index=routes_index,
            webhooks_doc=webhooks_doc,
            smoke_tests_index=smoke_tests_index,
            changelog=changelog,
            deprecations=deprecations,
            migrations=migrations,
            visualization=visualization,
            examples=examples,
        )

    # ------------------------------------------------------------------
    # Client generation
    # ------------------------------------------------------------------
    def _normalise_schema_reference(self, path: Path | None) -> str | None:
        """Return a repository-relative string for the provided *path*."""

        if path is None:
            return None

        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self._repo_root)
        except ValueError:
            return str(resolved)
        return str(relative)

    def _generate_python_client(self, path: Path) -> Path:
        routes = self._registry.routes
        method_blocks: list[str] = []
        for route in routes:
            method_blocks.append(self._render_python_method(route))
        client_template = textwrap.dedent(
            """
            \"\"\"Auto-generated TradePulse REST client.\"\"\"

            from __future__ import annotations

            from typing import Any, Mapping

            import httpx


            class TradePulseAPIClient:
                \"\"\"Minimal synchronous client for the TradePulse public API.\"\"\"

                def __init__(
                    self,
                    base_url: str,
                    *,
                    default_headers: Mapping[str, str] | None = None,
                    timeout: float = 10.0,
                    transport: httpx.BaseTransport | None = None,
                ) -> None:
                    self._base_url = base_url.rstrip("/") or "https://api.tradepulse"
                    self._default_headers = dict(default_headers or {})
                    self._client = httpx.Client(
                        base_url=self._base_url,
                        headers=self._default_headers,
                        timeout=httpx.Timeout(timeout, read=timeout),
                        transport=transport,
                    )

                def close(self) -> None:
                    \"\"\"Close the underlying httpx client.\"\"\"

                    self._client.close()

                def with_headers(self, headers: Mapping[str, str]) -> "TradePulseAPIClient":
                    \"\"\"Return a shallow copy with additional default headers.\"\"\"

                    combined = dict(self._default_headers)
                    combined.update(headers)
                    return TradePulseAPIClient(
                        base_url=self._base_url,
                        default_headers=combined,
                        timeout=float(self._client.timeout.connect),
                    )

            {{METHODS}}
            """
        ).strip()
        method_source = textwrap.indent("\n\n".join(method_blocks), "    ")
        client_source = (
            client_template.replace("{{METHODS}}", method_source).rstrip() + "\n"
        )
        _write_if_changed(path, client_source)
        return path

    def _render_python_method(self, route: ApiRoute) -> str:
        method_name = route.name.replace("-", "_")
        path_params = _path_parameters(route.path)
        param_signature = ", ".join(f"{name}: str" for name in path_params)
        if param_signature:
            param_signature = ", " + param_signature
        request_builder = self._render_python_request_builder(route, path_params)
        doc_lines = self._render_method_docstring(route)
        docstring = '    """' + doc_lines.replace("\n", "\n    ") + '\n    """'
        signature = (
            f"def {method_name}(self{param_signature}, *, payload: Mapping[str, Any] | None = None, "
            "headers: Mapping[str, str] | None = None) -> httpx.Response:"
        )
        return "\n".join([signature, docstring, request_builder])

    def _render_method_docstring(self, route: ApiRoute) -> str:
        lines = [route.summary]
        lines.append("")
        lines.append(f"Method: {route.method} {route.path}")
        lines.append(f"Scope: {route.scope}")
        lines.append(f"Cache: {route.cache.strategy}; max-age={route.cache.max_age}s")
        if route.idempotency.required:
            ttl = (
                f" ttl={route.idempotency.ttl_seconds}s"
                if route.idempotency.ttl_seconds
                else ""
            )
            lines.append(
                f"Idempotency: required via {route.idempotency.header or self._registry.metadata.idempotency_header}{ttl}"
            )
        else:
            lines.append("Idempotency: optional")
        return "\n".join(lines)

    def _render_python_request_builder(
        self, route: ApiRoute, path_params: Sequence[str]
    ) -> str:
        path_expr = route.path
        for name in path_params:
            path_expr = path_expr.replace(f"{{{name}}}", "{" + name + "}")
        path_format = f'f"{path_expr}"'
        has_body = route.method.upper() in {"POST", "PUT", "PATCH"}
        lines = [
            "request_headers = dict(self._default_headers)",
            "if headers:",
            "    request_headers.update(headers)",
            'request_kwargs: dict[str, Any] = {"headers": request_headers}',
        ]
        if has_body:
            lines.extend(
                [
                    "if payload is not None:",
                    '    request_kwargs["json"] = payload',
                ]
            )
        response_lines = [
            "response = self._client.request(",
            f'    "{route.method.upper()}",',
            f"    {path_format},",
            "    **request_kwargs,",
            ")",
            "response.raise_for_status()",
            "return response",
        ]
        lines.extend(response_lines)
        return textwrap.indent("\n".join(lines), "    ")

    def _generate_typescript_client(self, path: Path) -> Path:
        method_blocks = [
            self._render_typescript_method(route) for route in self._registry.routes
        ]
        template = textwrap.dedent(
            """
/* Auto-generated TradePulse REST client (TypeScript). */

export type RequestOptions = {
    headers?: Record<string, string>;
    signal?: AbortSignal;
    payload?: unknown;
};

export interface ClientConfig {
    baseUrl?: string;
    defaultHeaders?: Record<string, string>;
}

export class TradePulseClient {
    private readonly baseUrl: string;
    private readonly defaultHeaders: Record<string, string>;

    constructor(config: ClientConfig = {}) {
        this.baseUrl = (config.baseUrl || "https://api.tradepulse").replace(/\\u002F$/, "");
        this.defaultHeaders = { ...(config.defaultHeaders || {}) };
    }

    withHeaders(headers: Record<string, string>): TradePulseClient {
        return new TradePulseClient({
            baseUrl: this.baseUrl,
            defaultHeaders: { ...this.defaultHeaders, ...headers },
        });
    }

{{METHODS}}
}
            """
        ).strip()
        method_source = textwrap.indent("\n\n".join(method_blocks), "    ")
        source = template.replace("{{METHODS}}", method_source) + "\n"
        _write_if_changed(path, source)
        return path

    def _render_typescript_method(self, route: ApiRoute) -> str:
        method_name = route.name.replace("-", "_")
        path_params = _path_parameters(route.path)
        args_signature = ""
        if path_params:
            args_signature = ", " + ", ".join(f"{name}: string" for name in path_params)
        request_path = route.path
        for name in path_params:
            request_path = request_path.replace(f"{{{name}}}", f"${{{name}}}")
        has_body = route.method.upper() in {"POST", "PUT", "PATCH"}
        lines = [
            f"async {method_name}(options: RequestOptions = {{}}{args_signature}): Promise<Response> {{",
            "    const headers = { ...this.defaultHeaders, ...(options.headers || {}) };",
            f"    const requestUrl = `${{this.baseUrl}}{request_path}`;",
            "    const response = await fetch(requestUrl, {",
            f'        method: "{route.method.upper()}",',
            "        headers,",
        ]
        if has_body:
            lines.append(
                "        body: options.payload !== undefined ? JSON.stringify(options.payload) : undefined,"
            )
        lines.extend(
            [
                "        signal: options.signal,",
                "    });",
                "    if (!response.ok) {",
                "        throw new Error(`Request failed with status ${response.status}`);",
                "    }",
                "    return response;",
                "}",
            ]
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Documentation generation
    # ------------------------------------------------------------------
    def _generate_overview(self, path: Path) -> Path:
        sections: list[str] = []
        sections.append(self._render_metadata_section())
        sections.append(self._render_environment_section())
        sections.append(self._render_route_table())
        sections.append(self._render_smoke_test_summary())
        sections.append(self._render_compatibility_section())
        sections.append(self._render_maintainers_section())
        content = "\n\n".join(sections) + "\n"
        _write_if_changed(path, content)
        return path

    def _render_metadata_section(self) -> str:
        metadata = self._registry.metadata
        return textwrap.dedent(
            f"""
            # TradePulse API Governance Overview

            * Service: **{metadata.service}**
            * Release: **{metadata.release}**
            * Documentation: {metadata.docs_base_url}
            * Default signature algorithm: `{metadata.default_signature_algorithm}`
            * Default idempotency header: `{metadata.idempotency_header}`
            * Compatibility tier: `{metadata.compatibility.default}` (support window {metadata.compatibility.support_window_days} days)
            """
        ).strip()

    def _render_environment_section(self) -> str:
        if not self._registry.environments:
            return "## Environments\n\n_No environments defined._"
        rows = ["| Name | Base URL |", "| --- | --- |"]
        for env in self._registry.environments:
            rows.append(f"| {env.name} | {env.base_url} |")
        table = "\n".join(rows)
        return f"## Environments\n\n{table}"

    def _render_route_table(self) -> str:
        headers = [
            "Name",
            "Method",
            "Path",
            "Scope",
            "Cache",
            "Rate limits",
            "Throttle",
            "Idempotency",
            "Signature",
            "Webhooks",
        ]
        rows = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]
        for route in self._registry.routes:
            cache = f"{route.cache.strategy}; max-age={route.cache.max_age}; swr={route.cache.stale_while_revalidate}"
            rate_limit = _format_rate_limit(route.rate_limit)
            throttle = (
                f"burst={route.throttle.burst} / {route.throttle.period_seconds}s"
            )
            if route.idempotency.required:
                ttl = (
                    f" ttl={route.idempotency.ttl_seconds}s"
                    if route.idempotency.ttl_seconds
                    else ""
                )
                idempotency = f"required ({route.idempotency.header or self._registry.metadata.idempotency_header}{ttl})"
            else:
                idempotency = "optional"
            signature = "required" if route.signatures.required else "optional"
            suffix = f" {route.signatures.version}" if route.signatures.version else ""
            signature += (
                f" ({route.signatures.algorithm} via {route.signatures.header}{suffix})"
            )
            webhooks = ", ".join(route.webhooks) if route.webhooks else "—"
            rows.append(
                "| "
                + " | ".join(
                    [
                        route.name,
                        route.method.upper(),
                        route.path,
                        route.scope,
                        cache,
                        rate_limit,
                        throttle,
                        idempotency,
                        signature,
                        webhooks,
                    ]
                )
                + " |"
            )
        return "## Routes\n\n" + "\n".join(rows)

    def _render_smoke_test_summary(self) -> str:
        tests = [test for route in self._registry.routes for test in route.smoke_tests]
        if not tests:
            return "## Smoke tests\n\n_No smoke tests declared._"
        rows = [
            "| Name | Description | Expected status | Route |",
            "| --- | --- | --- | --- |",
        ]
        for route in self._registry.routes:
            for test in route.smoke_tests:
                rows.append(
                    "| "
                    + " | ".join(
                        [
                            test.name,
                            test.description,
                            str(test.expected_status),
                            route.name,
                        ]
                    )
                    + " |"
                )
        return "## Smoke tests\n\n" + "\n".join(rows)

    def _render_compatibility_section(self) -> str:
        guards = self._registry.compatibility
        if not guards:
            return "## Compatibility\n\n_The registry does not define additional compatibility guards._"
        rows = [
            "| Route | Minimum client version | Status | Comments |",
            "| --- | --- | --- | --- |",
        ]
        for guard in guards:
            rows.append(
                f"| {guard.route} | {guard.minimum_client_version} | {guard.status} | {guard.comments or '—'} |"
            )
        return "## Compatibility\n\n" + "\n".join(rows)

    def _render_maintainers_section(self) -> str:
        maintainers = self._registry.metadata.maintainers
        if not maintainers:
            return "## Maintainers\n\n_No maintainer records available._"
        bullet_lines = [
            f"- **{maintainer.name}** — {maintainer.contact}"
            for maintainer in maintainers
        ]
        return "## Maintainers\n\n" + "\n".join(bullet_lines)

    def _generate_route_index(self, path: Path) -> Path:
        route_index: list[Mapping[str, object]] = []
        for route in self._registry.routes:
            entry = {
                "name": route.name,
                "method": route.method.upper(),
                "path": route.path,
                "scope": route.scope,
                "cache": {
                    "strategy": route.cache.strategy,
                    "max_age": route.cache.max_age,
                    "stale_while_revalidate": route.cache.stale_while_revalidate,
                },
                "rate_limit": {
                    "per_minute": route.rate_limit.per_minute,
                    "per_hour": route.rate_limit.per_hour,
                    "per_day": route.rate_limit.per_day,
                },
                "throttle": {
                    "burst": route.throttle.burst,
                    "period_seconds": route.throttle.period_seconds,
                },
                "signatures": {
                    "required": route.signatures.required,
                    "algorithm": route.signatures.algorithm,
                    "header": route.signatures.header,
                    "version": route.signatures.version,
                },
                "idempotency": {
                    "required": route.idempotency.required,
                    "header": route.idempotency.header
                    or self._registry.metadata.idempotency_header,
                    "ttl_seconds": route.idempotency.ttl_seconds,
                },
                "request_schema": self._normalise_schema_reference(
                    route.request_schema
                ),
                "response_schema": self._normalise_schema_reference(
                    route.response_schema
                ),
                "webhooks": list(route.webhooks),
            }
            route_index.append(entry)
        _write_json_if_changed(path, route_index)
        return path

    def _generate_webhook_doc(self, path: Path) -> Path:
        lines = ["# Webhook Contracts", ""]
        for webhook in self._registry.webhooks:
            lines.append(f"## {webhook.name}")
            lines.append(webhook.summary)
            lines.append("")
            lines.append(f"- Method: `{webhook.method}`")
            lines.append(f"- Schema: `{webhook.schema}`")
            lines.append(
                "- Delivery: max attempts {} with {}s backoff".format(
                    webhook.retry_max_attempts, webhook.retry_backoff_seconds
                )
            )
            lines.append(
                f"- Signature: `{webhook.signature_header}` via `{webhook.signature_algorithm}` (version {webhook.signature_version})"
            )
            lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
        _write_if_changed(path, content)
        return path

    def _generate_smoke_tests_index(self, path: Path) -> Path:
        tests: list[Mapping[str, object]] = []
        for route in self._registry.routes:
            for test in route.smoke_tests:
                tests.append(
                    {
                        "name": test.name,
                        "description": test.description,
                        "route": route.name,
                        "method": test.request.method,
                        "path": test.request.path,
                        "headers": dict(test.request.headers),
                        "body": test.request.body,
                        "expected_status": test.expected_status,
                        "response_schema": self._normalise_schema_reference(
                            test.response_schema
                        ),
                    }
                )
        _write_json_if_changed(path, tests)
        return path

    def _generate_changelog(self, path: Path) -> Path:
        lines = ["# API Changelog", ""]
        for entry in self._registry.changelog:
            lines.append(f"## {entry.version} — {entry.released_at}")
            lines.append(entry.summary)
            lines.append("")
            lines.append(f"Compatibility: `{entry.compatibility}`")
            if entry.highlights:
                lines.append("")
                lines.append("### Highlights")
                for highlight in entry.highlights:
                    lines.append(f"- {highlight}")
            lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
        _write_if_changed(path, content)
        return path

    def _generate_deprecations(self, path: Path) -> Path:
        lines = ["# Deprecation Notices", ""]
        if not self._registry.deprecations:
            lines.append("No active deprecations.")
        for notice in self._registry.deprecations:
            lines.append(f"## {notice.route}")
            lines.append(f"Status: {notice.status}")
            lines.append(f"Sunset date: {notice.sunset_date}")
            lines.append(f"Reason: {notice.reason}")
            lines.append(f"Replacement: {notice.replacement or '—'}")
            lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
        _write_if_changed(path, content)
        return path

    def _generate_migrations(self, path: Path) -> Path:
        lines = ["# Migration Notices", ""]
        if not self._registry.migrations:
            lines.append("No migrations are scheduled.")
        for migration in self._registry.migrations:
            lines.append(f"## {migration.identifier}")
            lines.append(f"Summary: {migration.summary}")
            lines.append(f"Applies to: {', '.join(migration.applies_to) or '—'}")
            lines.append(f"Effective on: {migration.effective_on}")
            lines.append(f"Instructions: {migration.instructions_url}")
            lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
        _write_if_changed(path, content)
        return path

    def _generate_visualization(self, path: Path) -> Path:
        lines = [
            "digraph TradePulseAPI {",
            "    rankdir=LR;",
            "    node [shape=box, style=rounded, fontname=Helvetica];",
        ]
        for route in self._registry.routes:
            label = f"{route.method.upper()}\\n{route.path}"
            lines.append(f'    "{route.name}" [label="{label}"];')
        for webhook in self._registry.webhooks:
            lines.append(
                f'    "{webhook.name}" [shape=ellipse, style=filled, fillcolor=lightgrey];'
            )
        for route in self._registry.routes:
            if not route.webhooks:
                continue
            for webhook in route.webhooks:
                lines.append(f'    "{route.name}" -> "{webhook}";')
        lines.append("}")
        content = "\n".join(lines) + "\n"
        _write_if_changed(path, content)
        return path

    def _generate_examples(self, directory: Path) -> tuple[Path, ...]:
        paths: list[Path] = []
        for route in self._registry.routes:
            for simulator in route.simulators:
                file_name = f"{route.name}-{simulator.status_code}.json"
                target = directory / file_name
                _write_json_if_changed(target, simulator.body)
                paths.append(target)
        return tuple(paths)


# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------


def _write_if_changed(path: Path, content: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == content:
        return
    path.write_text(content, encoding="utf-8")


def _write_json_if_changed(
    path: Path, payload: Mapping[str, object] | Sequence[object]
) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == serialized:
        return
    path.write_text(serialized + "\n", encoding="utf-8")


def _path_parameters(path: str) -> list[str]:
    params: list[str] = []
    for segment in path.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            params.append(segment.strip("{}"))
    return params


def _format_rate_limit(
    rate_limit: Mapping[str, int | None] | RateLimitPolicy | None,
) -> str:
    if isinstance(rate_limit, Mapping):
        per_minute = rate_limit.get("per_minute")
        per_hour = rate_limit.get("per_hour")
        per_day = rate_limit.get("per_day")
    else:
        per_minute = getattr(rate_limit, "per_minute", None)
        per_hour = getattr(rate_limit, "per_hour", None)
        per_day = getattr(rate_limit, "per_day", None)
    parts: list[str] = []
    if per_minute:
        parts.append(f"{per_minute}/min")
    if per_hour:
        parts.append(f"{per_hour}/hour")
    if per_day:
        parts.append(f"{per_day}/day")
    return ", ".join(parts) if parts else "—"
