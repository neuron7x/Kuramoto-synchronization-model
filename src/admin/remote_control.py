"""FastAPI router implementing secure remote control operations."""

from __future__ import annotations

import asyncio
import ipaddress
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Deque, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.audit.audit_logger import AuditLogger
from src.risk.risk_manager import KillSwitchState, RiskManagerFacade
from src.security import AccessDeniedError

__all__ = [
    "AdminIdentity",
    "KillSwitchRequest",
    "KillSwitchResponse",
    "AdminRateLimiter",
    "AdminRateLimiterSnapshot",
    "create_remote_control_router",
]


@dataclass(slots=True)
class AdminRateLimiterSnapshot:
    """Point-in-time view of the administrative rate limiter state."""

    tracked_identifiers: int
    max_attempts: int
    interval_seconds: float
    max_utilization: float
    saturated_identifiers: list[str]


class AdminIdentity(BaseModel):
    """Authenticated administrator identity extracted from the request."""

    subject: str = Field(
        ..., description="Unique subject identifier for the administrator."
    )
    roles: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            "Normalised set of roles associated with the administrator. Roles are stored "
            "as lowercase strings to simplify downstream authorization checks."
        ),
    )

    model_config = ConfigDict(frozen=True)

    def has_role(self, role: str) -> bool:
        """Return ``True`` when *role* is associated with the identity."""

        candidate = role.strip().lower()
        if not candidate:
            raise ValueError("role must be a non-empty string")
        return candidate in self.role_set

    @property
    def role_set(self) -> set[str]:
        """Return the set of configured roles in lowercase form."""

        return {value.lower() for value in self.roles}


class KillSwitchRequest(BaseModel):
    """Request payload for activating the kill-switch."""

    reason: str = Field(
        ..., min_length=3, max_length=256, description="Human readable reason."
    )

    @field_validator("reason")
    @classmethod
    def _trim_and_validate_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 3:
            raise ValueError("reason must be at least 3 characters long")
        return stripped


class KillSwitchResponse(BaseModel):
    """Response payload describing the kill-switch state."""

    status: str = Field(..., description="Status message of the kill-switch operation.")
    kill_switch_engaged: bool = Field(
        ..., description="Whether the kill-switch is active."
    )
    reason: str = Field(
        ..., description="Reason supplied when the kill-switch was engaged."
    )
    already_engaged: bool = Field(
        ..., description="True if the kill-switch was already active."
    )


def _build_kill_switch_response(
    status: str, state: KillSwitchState
) -> KillSwitchResponse:
    """Serialise a kill-switch state into the public response model."""

    return KillSwitchResponse(
        status=status,
        kill_switch_engaged=state.engaged,
        reason=state.reason,
        already_engaged=state.already_engaged,
    )


class AdminRateLimiter:
    """Track administrative attempts and raise when limits are exceeded."""

    def __init__(
        self, *, max_attempts: int = 5, interval_seconds: float = 60.0
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._max_attempts = max_attempts
        self._interval = float(interval_seconds)
        self._records: dict[str, Deque[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, identifier: str) -> None:
        """Register an attempt for *identifier* and enforce rate limits."""

        loop = asyncio.get_running_loop()
        now = loop.time()
        async with self._lock:
            bucket = self._records.setdefault(identifier, deque())
            while bucket and now - bucket[0] >= self._interval:
                bucket.popleft()
            if len(bucket) >= self._max_attempts:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many administrative requests from this source",
                )
            bucket.append(now)

    async def snapshot(self) -> AdminRateLimiterSnapshot:
        """Return utilisation metrics for observability checks."""

        loop = asyncio.get_running_loop()
        now = loop.time()
        async with self._lock:
            cleaned: Dict[str, Deque[float]] = {}
            for identifier, bucket in list(self._records.items()):
                while bucket and now - bucket[0] >= self._interval:
                    bucket.popleft()
                if bucket:
                    cleaned[identifier] = deque(bucket)
                else:
                    self._records.pop(identifier, None)

        max_utilization = 0.0
        saturated: list[str] = []
        for identifier, bucket in cleaned.items():
            utilisation = len(bucket) / float(self._max_attempts)
            if utilisation > max_utilization:
                max_utilization = utilisation
            if utilisation >= 1.0:
                saturated.append(identifier)

        return AdminRateLimiterSnapshot(
            tracked_identifiers=len(cleaned),
            max_attempts=self._max_attempts,
            interval_seconds=self._interval,
            max_utilization=max_utilization,
            saturated_identifiers=saturated,
        )


def _resolve_ip(request: Request) -> str:
    """Return the originating IP address for the request."""

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = _normalize_ip(part)
            if candidate is not None:
                return candidate

    real_ip = _normalize_ip(request.headers.get("X-Real-IP"))
    if real_ip is not None:
        return real_ip

    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def _normalize_ip(raw: str | None) -> str | None:
    """Return a validated IP address extracted from header data."""

    if raw is None:
        return None

    candidate = raw.strip()
    if not candidate:
        return None

    # Mitigate header injection attempts such as "1.1.1.1   malicious".
    candidate = candidate.split()[0]

    # Remove square brackets that may wrap IPv6 addresses (e.g. "[::1]").
    candidate = candidate.strip("[]")

    # Drop a zone identifier (e.g. "fe80::1%eth0") as ipaddress cannot parse it.
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]

    # Handle IPv4 addresses that include a port component.
    if "." in candidate and candidate.count(":") == 1:
        host, _, port = candidate.rpartition(":")
        if port.isdigit():
            candidate = host

    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def create_remote_control_router(
    risk_manager: RiskManagerFacade,
    audit_logger: AuditLogger,
    identity_dependency: Callable[..., AdminIdentity | Awaitable[AdminIdentity]],
    *,
    rate_limiter: AdminRateLimiter | None = None,
    read_permission: (
        Callable[..., AdminIdentity | Awaitable[AdminIdentity]] | None
    ) = None,
    execute_permission: (
        Callable[..., AdminIdentity | Awaitable[AdminIdentity]] | None
    ) = None,
    reset_permission: (
        Callable[..., AdminIdentity | Awaitable[AdminIdentity]] | None
    ) = None,
) -> APIRouter:
    """Create a router exposing secure administrative endpoints."""

    router = APIRouter(
        prefix="/admin",
        tags=["admin"],
        responses={401: {"description": "Unauthorized"}},
    )

    def get_risk_manager() -> RiskManagerFacade:
        return risk_manager

    def get_audit_logger() -> AuditLogger:
        return audit_logger

    limiter = rate_limiter or AdminRateLimiter()

    read_dependency = read_permission or identity_dependency
    execute_dependency = execute_permission or identity_dependency
    reset_dependency = reset_permission or execute_dependency

    async def enforce_admin_rate_limit(request: Request) -> None:
        identifier = _resolve_ip(request)
        await limiter.check(identifier)

    @router.post(
        "/kill-switch",
        response_model=KillSwitchResponse,
        status_code=status.HTTP_200_OK,
        summary="Engage the global kill-switch",
        description="Engage or reaffirm the kill-switch and emit a signed audit log entry.",
    )
    async def engage_kill_switch(
        payload: KillSwitchRequest,
        request: Request,
        _: None = Depends(enforce_admin_rate_limit),
        identity: AdminIdentity = Depends(execute_dependency),
        manager: RiskManagerFacade = Depends(get_risk_manager),
        logger: AuditLogger = Depends(get_audit_logger),
    ) -> KillSwitchResponse:
        """Engage the risk manager kill-switch and log the operation."""

        try:
            state: KillSwitchState = manager.engage_kill_switch(
                payload.reason, actor=identity.subject, roles=identity.roles
            )
        except AccessDeniedError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        event_type = (
            "kill_switch_reaffirmed" if state.already_engaged else "kill_switch_engaged"
        )
        logger.log_event(
            event_type=event_type,
            actor=identity.subject,
            ip_address=_resolve_ip(request),
            details={
                "reason": state.reason,
                "already_engaged": state.already_engaged,
                "path": str(request.url.path),
            },
        )
        status_message = "already-engaged" if state.already_engaged else "engaged"
        return _build_kill_switch_response(status_message, state)

    @router.get(
        "/kill-switch",
        response_model=KillSwitchResponse,
        status_code=status.HTTP_200_OK,
        summary="Read the global kill-switch state",
        description="Inspect the kill-switch state and append an immutable audit record.",
    )
    async def read_kill_switch_state(
        request: Request,
        _: None = Depends(enforce_admin_rate_limit),
        identity: AdminIdentity = Depends(read_dependency),
        manager: RiskManagerFacade = Depends(get_risk_manager),
        logger: AuditLogger = Depends(get_audit_logger),
    ) -> KillSwitchResponse:
        """Return the current kill-switch status and audit the read."""

        try:
            state = manager.kill_switch_state(
                actor=identity.subject, roles=identity.roles
            )
        except AccessDeniedError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        logger.log_event(
            event_type="kill_switch_state_viewed",
            actor=identity.subject,
            ip_address=_resolve_ip(request),
            details={
                "kill_switch_engaged": state.engaged,
                "reason": state.reason,
                "path": str(request.url.path),
            },
        )
        status_message = "engaged" if state.engaged else "disengaged"
        return _build_kill_switch_response(status_message, state)

    @router.delete(
        "/kill-switch",
        response_model=KillSwitchResponse,
        status_code=status.HTTP_200_OK,
        summary="Reset the global kill-switch",
        description="Reset the kill-switch in an idempotent manner and preserve an audit trail.",
    )
    async def reset_kill_switch(
        request: Request,
        _: None = Depends(enforce_admin_rate_limit),
        identity: AdminIdentity = Depends(reset_dependency),
        manager: RiskManagerFacade = Depends(get_risk_manager),
        logger: AuditLogger = Depends(get_audit_logger),
    ) -> KillSwitchResponse:
        """Reset the kill-switch in an idempotent manner and audit the action."""

        try:
            state = manager.reset_kill_switch(
                actor=identity.subject, roles=identity.roles
            )
        except AccessDeniedError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        event_type = (
            "kill_switch_reset" if state.already_engaged else "kill_switch_reset_noop"
        )
        logger.log_event(
            event_type=event_type,
            actor=identity.subject,
            ip_address=_resolve_ip(request),
            details={
                "previously_engaged": state.already_engaged,
                "reason": state.reason,
                "path": str(request.url.path),
            },
        )
        status_message = "reset" if state.already_engaged else "already-clear"
        return _build_kill_switch_response(status_message, state)

    return router
