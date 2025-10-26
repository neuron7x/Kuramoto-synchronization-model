"""Runtime facade that enforces integration contracts during dispatch.

The :class:`ModuleIntegrationGateway` coordinates the :class:`IntegrationRouter`
with declarative contracts (:mod:`src.system.integration_contracts`).  It
verifies authorisation headers, injects tracing metadata, enforces idempotency
rules and transparently retries transient publish failures.  The goal is to
provide a single entry point for the API gateway (or other boundary adapters)
so that every outgoing event respects the same operational guarantees.
"""

from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass, replace
from typing import Mapping

from core.messaging.event_bus import EventEnvelope
from observability.tracing import current_traceparent, inject_trace_context

from .api_messaging_integration import (
    GatewayRequest,
    IntegrationRoute,
    IntegrationRouter,
    RouteDispatchResult,
)
from .integration_contracts import (
    AuthorizationError,
    ContractValidationError,
    DeliverySemantics,
    IntegrationContract,
    IntegrationContractRegistry,
    RetryPolicy,
)


@dataclass(slots=True, frozen=True)
class IntegrationDispatchReport:
    """Summary returned after dispatching a contract bound request."""

    contract: IntegrationContract
    caller: str
    route: IntegrationRoute
    envelope: EventEnvelope
    attempts: int
    deduplicated: bool
    traceparent: str | None


class ModuleIntegrationGateway:
    """Encapsulates cross-module dispatch enforcing declared contracts."""

    def __init__(
        self,
        *,
        router: IntegrationRouter,
        registry: IntegrationContractRegistry,
        rng: random.Random | None = None,
    ) -> None:
        self._router = router
        self._registry = registry
        self._rng = rng or random.Random()

    def resolve_contract(
        self, name: str, version: str | None = None
    ) -> IntegrationContract:
        return self._registry.get(name, version)

    async def dispatch(
        self,
        contract_name: str,
        request: GatewayRequest,
        *,
        version: str | None = None,
    ) -> IntegrationDispatchReport:
        contract = self.resolve_contract(contract_name, version)

        if not contract.api.matches(request.method, request.path):
            raise ContractValidationError(
                f"Request {request.method} {request.path} does not satisfy contract"
            )

        try:
            caller = contract.validate_request_headers(request.headers)
        except AuthorizationError as exc:
            raise ContractValidationError(str(exc)) from exc

        idempotency_key = self._lookup_header(
            request.headers, contract.idempotency.key_header
        )

        if (
            contract.idempotency.semantics is DeliverySemantics.EXACTLY_ONCE
            and not idempotency_key
        ):
            raise ContractValidationError(
                "Exactly-once contract requires idempotency key header"
            )

        result = self._router.route_request(request)
        result = self._apply_idempotency(contract, result, idempotency_key)
        result, traceparent = self._apply_tracing(contract, result, request.headers)

        envelope = result.envelope
        deduplicated = False
        attempts = 0

        store = self._router.event_bus.idempotency_store
        if store.was_processed(envelope.event_id):
            deduplicated = True
        else:
            attempts = await self._publish_with_retry(result, contract.retries)
            store.mark_processed(envelope.event_id)

        return IntegrationDispatchReport(
            contract=contract,
            caller=caller,
            route=result.route,
            envelope=envelope,
            attempts=attempts,
            deduplicated=deduplicated,
            traceparent=traceparent,
        )

    async def _publish_with_retry(
        self, result: RouteDispatchResult, policy: RetryPolicy
    ) -> int:
        attempts = 0
        while True:
            try:
                await self._router.event_bus.publish(result.topic, result.envelope)
                return attempts + 1
            except Exception:
                attempts += 1
                if attempts >= policy.max_attempts:
                    raise
                delay = policy.compute_backoff(attempts)
                if policy.jitter_seconds:
                    delay += self._rng.uniform(0.0, policy.jitter_seconds)
                await asyncio.sleep(delay)

    def _apply_idempotency(
        self,
        contract: IntegrationContract,
        result: RouteDispatchResult,
        idempotency_key: str | None,
    ) -> RouteDispatchResult:
        envelope = result.envelope
        headers = dict(envelope.headers)

        if idempotency_key:
            headers[result.route.name + ":idempotency"] = idempotency_key
            if envelope.event_id != idempotency_key:
                envelope = replace(envelope, event_id=idempotency_key)

        headers.setdefault(result.route.name + ":idempotency", envelope.event_id)
        headers.setdefault(contract.idempotency.key_header, envelope.event_id)
        headers.setdefault(
            result.route.name + ":idempotency-semantics",
            result.route.schema_version if hasattr(result.route, "schema_version") else "",
        )
        envelope = replace(envelope, headers=headers)
        return replace(result, envelope=envelope)

    def _apply_tracing(
        self,
        contract: IntegrationContract,
        result: RouteDispatchResult,
        request_headers: Mapping[str, str],
    ) -> tuple[RouteDispatchResult, str | None]:
        if not contract.tracing_enabled:
            return result, None

        envelope = result.envelope
        headers = dict(envelope.headers)

        trace_header_name = contract.expected_trace_header()
        request_traceparent = self._lookup_header(request_headers, trace_header_name)
        if request_traceparent:
            headers[trace_header_name] = request_traceparent
        else:
            traceparent = current_traceparent()
            if not traceparent:
                traceparent = self._generate_traceparent()
            headers[trace_header_name] = traceparent
            request_traceparent = traceparent

        inject_trace_context(headers)
        envelope = replace(envelope, headers=headers)
        return replace(result, envelope=envelope), request_traceparent

    def _generate_traceparent(self) -> str:
        trace_id = uuid.uuid4().hex
        span_id = self._rng.getrandbits(64).to_bytes(8, "big").hex()
        return f"00-{trace_id}-{span_id}-01"

    @staticmethod
    def _lookup_header(headers: Mapping[str, str], name: str) -> str | None:
        lowered = name.lower()
        for header, value in headers.items():
            if header.lower() == lowered:
                return value
        return None


__all__ = ["IntegrationDispatchReport", "ModuleIntegrationGateway"]
