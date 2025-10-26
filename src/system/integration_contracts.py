"""Formal integration contracts between TradePulse modules.

The TradePulse platform is composed of independently deployable services such as
data ingestion, analytics, risk and execution.  Each service communicates via
well defined asynchronous boundaries (HTTP gateways, message bus topics and
work queues).  This module defines *contract objects* that describe those
boundaries in a testable and versioned manner.  The contracts capture the
authorisation and resilience expectations for each integration point and can be
used by higher level facades to enforce invariants at runtime.

The design goals are:

* **Stability** – contracts are immutable dataclasses and versioned explicitly.
* **Observability** – metadata includes tracing hints and metric definitions
  (SLIs) so that downstream tooling can configure dashboards automatically.
* **Security** – service-to-service authorisation is modelled and validated via
  lightweight token based policies tailored for internal usage.
* **Resilience** – retries, deduplication and idempotency expectations are
  codified so that both producers and consumers reason about delivery semantics.

The module purposefully avoids hard dependencies on concrete transport layers;
instead it provides small validation helpers that higher level integration code
may call before performing network I/O.  This keeps the contracts importable in
tests and documentation tooling while remaining executable in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Mapping, MutableMapping, Sequence


class ContractError(RuntimeError):
    """Base class for contract related exceptions."""


class ContractRegistrationError(ContractError):
    """Raised when the same contract/version pair is registered twice."""


class ContractValidationError(ContractError):
    """Raised when a request or configuration violates a contract."""


class AuthorizationError(ContractValidationError):
    """Raised when a caller cannot satisfy the declared authorisation policy."""


class AuthorizationScheme(str, Enum):
    """Supported service-to-service authorisation schemes."""

    MUTUAL_TLS = "mtls"
    SIGNED_TOKEN = "signed-token"
    API_KEY = "api-key"


@dataclass(frozen=True)
class AuthorizationPolicy:
    """Definition of how a module authenticates callers.

    The policy models a simple token based authentication flow.  Callers must
    provide two headers:

    ``x-service-name``
        Declares the logical producer identity.

    ``x-service-token``
        Contains an opaque secret that must match the one registered for the
        service within the policy.

    The scheme attribute is advisory and can be used to coordinate how secrets
    are provisioned (for example HMAC signed tokens vs. mTLS client certs).
    """

    scheme: AuthorizationScheme
    audience: str
    allowed_callers: Mapping[str, str] = field(default_factory=dict)

    def validate_headers(self, headers: Mapping[str, str]) -> str:
        """Validate headers against the policy returning the caller identity.

        ``AuthorizationError`` is raised when the supplied headers do not carry
        a known service identity or when the token does not match the expected
        secret.  The comparison is performed in a case insensitive manner so it
        mirrors how HTTP intermediaries typically handle header casing.
        """

        service_header = self._lookup_header(headers, "x-service-name")
        if not service_header:
            raise AuthorizationError("Missing x-service-name header")

        token_header = self._lookup_header(headers, "x-service-token")
        if not token_header:
            raise AuthorizationError("Missing x-service-token header")

        expected_token = self.allowed_callers.get(service_header)
        if expected_token is None:
            raise AuthorizationError(
                f"Unknown caller '{service_header}' for audience '{self.audience}'"
            )

        if token_header != expected_token:
            raise AuthorizationError("Invalid service token supplied")

        return service_header

    @staticmethod
    def _lookup_header(headers: Mapping[str, str], name: str) -> str | None:
        lower_name = name.lower()
        for header, value in headers.items():
            if header.lower() == lower_name:
                return value
        return None


class DeliverySemantics(str, Enum):
    """Delivery guarantees across module boundaries."""

    AT_LEAST_ONCE = "at-least-once"
    EXACTLY_ONCE = "exactly-once"
    AT_MOST_ONCE = "at-most-once"


@dataclass(frozen=True)
class IdempotencyRule:
    """Idempotency configuration for integrations."""

    key_header: str = "x-idempotency-key"
    ttl_seconds: int = 3600
    semantics: DeliverySemantics = DeliverySemantics.AT_LEAST_ONCE


@dataclass(frozen=True)
class RetryPolicy:
    """Retry configuration shared by producers and consumers."""

    max_attempts: int = 5
    initial_backoff_seconds: float = 0.1
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 5.0
    jitter_seconds: float = 0.05

    def compute_backoff(self, attempt: int) -> float:
        """Return the backoff duration for ``attempt`` using exponential policy."""

        if attempt <= 0:
            return 0.0
        delay = self.initial_backoff_seconds * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff_seconds)


@dataclass(frozen=True)
class SLI:
    """A Service Level Indicator definition."""

    name: str
    metric: str
    objective: float
    description: str = ""


@dataclass(frozen=True)
class SLA:
    """Service Level Agreement metadata."""

    availability_target: float
    latency_p99_ms: int
    data_freshness_sla_seconds: int
    notes: str = ""


@dataclass(frozen=True)
class ApiBinding:
    """Represents an HTTP contract served by a module."""

    method: str
    path_pattern: str
    payload_schema: str

    def matches(self, method: str, path: str) -> bool:
        return method.upper() == self.method.upper() and bool(
            re.fullmatch(self.path_pattern, path)
        )


@dataclass(frozen=True)
class EventBinding:
    """Represents an asynchronous messaging contract."""

    topic: str
    schema: str
    version: str
    content_type: str = "application/json"


@dataclass(frozen=True)
class IntegrationContract:
    """Single interaction contract between two modules."""

    name: str
    producer: str
    consumer: str
    version: str
    api: ApiBinding
    event: EventBinding
    authorization: AuthorizationPolicy
    idempotency: IdempotencyRule = field(default_factory=IdempotencyRule)
    retries: RetryPolicy = field(default_factory=RetryPolicy)
    sla: SLA = field(
        default_factory=lambda: SLA(
            availability_target=0.999,
            latency_p99_ms=250,
            data_freshness_sla_seconds=5,
        )
    )
    slis: Sequence[SLI] = field(default_factory=tuple)
    tracing_enabled: bool = True

    def validate_request_headers(self, headers: Mapping[str, str]) -> str:
        """Validate the caller headers and return the authenticated caller."""

        return self.authorization.validate_headers(headers)

    def expected_trace_header(self) -> str:
        """Return the canonical trace header name used for propagation."""

        return "traceparent"


class IntegrationContractRegistry:
    """Registry that tracks contracts and ensures uniqueness."""

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, str], IntegrationContract] = {}

    def register(self, contract: IntegrationContract) -> IntegrationContract:
        key = (contract.name, contract.version)
        if key in self._contracts:
            raise ContractRegistrationError(
                f"Contract '{contract.name}' version '{contract.version}' already registered"
            )
        self._contracts[key] = contract
        return contract

    def get(self, name: str, version: str | None = None) -> IntegrationContract:
        if version is not None:
            contract = self._contracts.get((name, version))
            if contract is None:
                raise ContractValidationError(
                    f"Unknown contract '{name}' version '{version}'"
                )
            return contract

        # fall back to highest semantic version when unspecified
        matching = [contract for (contract_name, _), contract in self._contracts.items() if contract_name == name]
        if not matching:
            raise ContractValidationError(f"Unknown contract '{name}'")

        def _version_key(contract: IntegrationContract) -> Sequence[int]:
            return tuple(int(part) for part in contract.version.split("."))

        return max(matching, key=_version_key)

    def contracts(self) -> Sequence[IntegrationContract]:
        return tuple(self._contracts.values())


def ensure_headers_mutable(headers: Mapping[str, str]) -> MutableMapping[str, str]:
    """Return a mutable copy suitable for enrichment during dispatch."""

    if isinstance(headers, dict):
        return headers
    return dict(headers)


__all__ = [
    "ApiBinding",
    "AuthorizationError",
    "AuthorizationPolicy",
    "AuthorizationScheme",
    "ContractError",
    "ContractRegistrationError",
    "ContractValidationError",
    "DeliverySemantics",
    "EventBinding",
    "IdempotencyRule",
    "IntegrationContract",
    "IntegrationContractRegistry",
    "RetryPolicy",
    "SLA",
    "SLI",
    "ensure_headers_mutable",
]
