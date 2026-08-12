# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration layer bridging API gateway requests to the messaging backbone."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Pattern

from core.messaging.event_bus import BaseEventBus, EventEnvelope, EventTopic


class IntegrationRouteError(RuntimeError):
    """Base class for integration routing exceptions."""


class IntegrationRouteConflictError(IntegrationRouteError):
    """Raised when attempting to register a conflicting route definition."""


class IntegrationRouteNotFoundError(IntegrationRouteError):
    """Raised when no route can be resolved for the supplied request."""


@dataclass(slots=True, frozen=True)
class GatewayRequest:
    """Canonical representation of a request entering the API gateway."""

    path: str
    method: str
    payload: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)
    query_params: Mapping[str, str] = field(default_factory=dict)
    correlation_id: str | None = None

    def normalized_method(self) -> str:
        """Return the HTTP method in uppercase for consistent comparisons."""

        return self.method.upper()

    def get_header(self, name: str, default: str | None = None) -> str | None:
        """Return a header value using case-insensitive lookup semantics."""

        lower_name = name.lower()
        for header, value in self.headers.items():
            if header.lower() == lower_name:
                return value
        return default

    @property
    def resolved_correlation_id(self) -> str | None:
        """Prefer explicit correlation identifiers when provided."""

        header_value = self.get_header("x-correlation-id") or self.get_header("x-request-id")
        return self.correlation_id or header_value


@dataclass(slots=True, frozen=True)
class IntegrationRoute:
    """Description of how to transform gateway requests into bus events."""

    name: str
    methods: frozenset[str]
    path_pattern: Pattern[str]
    topic: EventTopic
    partition_resolver: Callable[[GatewayRequest, re.Match[str]], str]
    payload_encoder: Callable[[GatewayRequest], bytes]
    header_builder: Callable[[GatewayRequest, re.Match[str]], MutableMapping[str, str]]
    content_type: str = "application/json"
    schema_version: str = "1.0"
    event_type: str | None = None


@dataclass(slots=True, frozen=True)
class RouteDispatchResult:
    """Outcome of routing a gateway request to the messaging layer."""

    route: IntegrationRoute
    topic: EventTopic
    envelope: EventEnvelope
    path_params: Mapping[str, str]


def _coerce_methods(methods: Iterable[str] | Mapping[str, Any]) -> frozenset[str]:
    return frozenset(method.upper() for method in methods)


def _default_payload_encoder(request: GatewayRequest) -> bytes:
    payload = request.payload
    if payload is None:
        return b""
    if isinstance(payload, (bytes, bytearray, memoryview)):
        return bytes(payload)

    def _default(obj: Any) -> Any:
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")

    return json.dumps(payload, default=_default, separators=(",", ":")).encode("utf-8")


def _default_header_builder(
    request: GatewayRequest, match: re.Match[str]
) -> MutableMapping[str, str]:
    headers: MutableMapping[str, str] = {}
    correlation_id = request.resolved_correlation_id
    if correlation_id:
        headers["x-correlation-id"] = correlation_id
    headers["x-gateway-method"] = request.normalized_method()
    headers["x-gateway-path"] = request.path
    if match.groupdict():
        headers["x-gateway-path-params"] = json.dumps(match.groupdict())
    if request.query_params:
        headers["x-gateway-query"] = json.dumps(request.query_params, separators=(",", ":"))
    return headers


def _default_partition_resolver(request: GatewayRequest, match: re.Match[str]) -> str:
    correlation_id = request.resolved_correlation_id
    if correlation_id:
        return correlation_id
    params = match.groupdict()
    if "symbol" in params and params["symbol"]:
        return params["symbol"]
    return request.path


@dataclass(slots=True)
class IntegrationRouter:
    """Routes API gateway requests onto the GeoSync messaging fabric."""

    event_bus: BaseEventBus
    event_id_factory: Callable[[], str] = uuid.uuid4
    _routes: dict[str, IntegrationRoute] = field(init=False, repr=False)
    _ordered_routes: list[IntegrationRoute] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_routes", {})
        object.__setattr__(self, "_ordered_routes", [])

    def register_route(
        self,
        *,
        name: str,
        methods: Iterable[str] | Mapping[str, Any],
        path_pattern: str | Pattern[str],
        topic: EventTopic,
        partition_resolver: Callable[[GatewayRequest, re.Match[str]], str] | None = None,
        payload_encoder: Callable[[GatewayRequest], bytes] | None = None,
        header_builder: (
            Callable[[GatewayRequest, re.Match[str]], MutableMapping[str, str]] | None
        ) = None,
        content_type: str = "application/json",
        schema_version: str = "1.0",
        event_type: str | None = None,
    ) -> IntegrationRoute:
        """Register a new route binding."""

        if name in self._routes:
            raise IntegrationRouteConflictError(f"Route named '{name}' already exists")

        compiled_pattern = (
            re.compile(path_pattern) if isinstance(path_pattern, str) else path_pattern
        )

        resolved_methods = _coerce_methods(methods)
        if not resolved_methods:
            raise IntegrationRouteError(f"Route '{name}' must define at least one HTTP method")

        route = IntegrationRoute(
            name=name,
            methods=resolved_methods,
            path_pattern=compiled_pattern,
            topic=topic,
            partition_resolver=partition_resolver or _default_partition_resolver,
            payload_encoder=payload_encoder or _default_payload_encoder,
            header_builder=header_builder or _default_header_builder,
            content_type=content_type,
            schema_version=schema_version,
            event_type=event_type,
        )
        self._routes[name] = route
        self._ordered_routes.append(route)
        return route

    def available_routes(self) -> list[IntegrationRoute]:
        """Return a snapshot of configured routes."""

        return list(self._ordered_routes)

    def _match_route(self, request: GatewayRequest) -> tuple[IntegrationRoute, re.Match[str]]:
        method = request.normalized_method()
        for route in self._ordered_routes:
            if method not in route.methods:
                continue
            match = route.path_pattern.fullmatch(request.path)
            if match:
                return route, match
        raise IntegrationRouteNotFoundError(
            f"No route registered for {request.method} {request.path}"
        )

    def route_request(self, request: GatewayRequest) -> RouteDispatchResult:
        """Resolve the request into a message envelope without publishing it."""

        route, match = self._match_route(request)
        partition_key = route.partition_resolver(request, match)
        if not partition_key:
            raise IntegrationRouteError(f"Resolved partition key for route '{route.name}' is empty")

        payload = route.payload_encoder(request)
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise IntegrationRouteError(
                f"Encoder for route '{route.name}' must return bytes, received {type(payload)!r}"
            )

        event_id = request.resolved_correlation_id or str(self.event_id_factory())
        headers = dict(route.header_builder(request, match))
        headers.setdefault("x-correlation-id", event_id)
        envelope = EventEnvelope(
            event_type=route.event_type or route.name,
            partition_key=partition_key,
            event_id=event_id,
            payload=bytes(payload),
            content_type=route.content_type,
            schema_version=route.schema_version,
            headers=headers,
        )
        return RouteDispatchResult(
            route=route,
            topic=route.topic,
            envelope=envelope,
            path_params=match.groupdict(),
        )

    async def dispatch(self, request: GatewayRequest) -> RouteDispatchResult:
        """Publish the resolved envelope using the configured event bus."""

        result = self.route_request(request)
        await self.event_bus.publish(result.topic, result.envelope)
        return result
