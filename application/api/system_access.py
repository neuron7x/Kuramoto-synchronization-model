"""FastAPI application exposing operational TradePulse system primitives."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from fastapi import Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from application.api.authorization import (
    get_authorization_gateway,
    require_permission,
)
from application.api.debug import install_debug_routes
from application.api.errors import register_exception_handlers
from application.api.middleware import AccessLogMiddleware
from application.api.rate_limit import (
    SlidingWindowRateLimiter,
    build_rate_limiter,
)
from application.api.security import verify_request_identity
from application.security.rbac import AuthorizationGateway
from application.settings import (
    ApiRateLimitSettings,
    BackendRuntimeSettings,
    NotificationSettings,
)
from application.system import TradePulseSystem
from application.trading import order_to_dto
from core.utils.debug import VariableInspector
from domain import Order, OrderSide, OrderType, Position
from observability.audit.trail import (
    AuditTrail,
    AuditTrailError,
    get_access_audit_trail,
    get_system_audit_trail,
)
from observability.logging import configure_logging
from observability.notifications import (
    EmailSender,
    NotificationDispatcher,
    SlackNotifier,
)
from src.admin.remote_control import AdminIdentity
from src.security import AccessDeniedError


def _read_version() -> str:
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        raw = version_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "0.0.0"
    return raw or "0.0.0"


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_notification_dispatcher(
    settings: NotificationSettings | None,
) -> NotificationDispatcher | None:
    if settings is None:
        return None

    email_sender: EmailSender | None = None
    if settings.email is not None:
        email_password = (
            settings.email.password.get_secret_value()
            if settings.email.password is not None
            else None
        )
        email_sender = EmailSender(
            host=settings.email.host,
            port=int(settings.email.port),
            sender=settings.email.sender,
            recipients=tuple(settings.email.recipients),
            username=settings.email.username,
            password=email_password,
            use_tls=settings.email.use_tls,
            use_ssl=settings.email.use_ssl,
            timeout=float(settings.email.timeout_seconds),
        )

    slack_notifier: SlackNotifier | None = None
    if settings.slack_webhook_url is not None:
        slack_notifier = SlackNotifier(
            str(settings.slack_webhook_url),
            channel=settings.slack_channel,
            username=settings.slack_username,
            timeout=float(settings.slack_timeout_seconds),
        )

    if email_sender is None and slack_notifier is None:
        return None

    return NotificationDispatcher(
        email_sender=email_sender,
        slack_notifier=slack_notifier,
    )


class StatusResponse(BaseModel):
    """Service health metadata exposed via the REST API."""

    status: str = Field(..., description="Operational state of the system.")
    uptime_seconds: float = Field(..., ge=0.0, description="Service uptime in seconds.")
    version: str = Field(
        ..., min_length=1, description="Semantic version of the deployment."
    )


class PositionSnapshot(BaseModel):
    """Normalised representation of a trading position."""

    symbol: str = Field(..., min_length=1)
    quantity: float = Field(..., description="Signed quantity representing exposure.")
    entry_price: float | None = Field(
        default=None, description="Average entry price where available."
    )
    current_price: float | None = Field(
        default=None, description="Latest mark price associated with the position."
    )
    unrealized_pnl: float | None = Field(
        default=None, description="Unrealised profit and loss inferred from venue data."
    )

    model_config = ConfigDict(populate_by_name=True)


class PositionsResponse(BaseModel):
    """Envelope containing active positions across venues."""

    positions: Sequence[PositionSnapshot] = Field(default_factory=list)


class OrderRequest(BaseModel):
    """Request payload describing an order submission."""

    symbol: str = Field(..., min_length=1)
    side: OrderSide
    order_type: OrderType = Field(default=OrderType.MARKET)
    quantity: float = Field(..., gt=0.0)
    price: float | None = Field(default=None, gt=0.0)
    reference_price: float | None = Field(
        default=None,
        gt=0.0,
        description="Reference market price used for risk validation when no limit price is provided.",
    )
    venue: str | None = Field(
        default=None,
        description="Target venue identifier. Defaults to the first configured connector.",
    )
    client_order_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional idempotency key forwarded to the execution adapter.",
    )

    @model_validator(mode="before")
    def _validate_price(cls, data: Any) -> Any:
        if isinstance(data, Mapping):
            raw_type = data.get("order_type")
            price = data.get("price")
            try:
                order_type = OrderType(raw_type)
            except Exception:
                order_type = None
            priced_types = {OrderType.LIMIT, OrderType.STOP, OrderType.STOP_LIMIT}
            if order_type in priced_types and price is None:
                raise ValueError("price must be supplied for priced order types")
        return data

    @model_validator(mode="after")
    def _validate_reference_price(self) -> "OrderRequest":
        if self.price is None and self.reference_price is None:
            raise ValueError(
                "reference_price must be supplied when no price is provided"
            )
        return self


class OrderResponse(BaseModel):
    """Subset of order lifecycle data returned to REST clients."""

    order_id: str | None = Field(
        default=None, description="Venue supplied order identifier."
    )
    status: str = Field(..., description="Latest known status of the order.")
    filled_quantity: float = Field(..., ge=0.0)
    average_price: float | None = Field(default=None, ge=0.0)


@dataclass(slots=True)
class _PositionNormaliser:
    """Translate heterogeneous connector payloads into :class:`PositionSnapshot`."""

    def normalise(self, payload: Mapping[str, Any]) -> PositionSnapshot:
        symbol = str(
            payload.get("symbol")
            or payload.get("instrument")
            or payload.get("pair")
            or payload.get("asset")
            or "unknown"
        )

        quantity = (
            _coerce_float(
                payload.get("quantity")
                or payload.get("qty")
                or payload.get("size")
                or payload.get("positionAmt")
                or payload.get("position")
            )
            or 0.0
        )

        entry_price = _coerce_float(
            payload.get("entry_price")
            or payload.get("entryPrice")
            or payload.get("avg_entry_price")
            or payload.get("average_price")
            or payload.get("avgPrice")
        )

        current_price = _coerce_float(
            payload.get("current_price")
            or payload.get("currentPrice")
            or payload.get("mark_price")
            or payload.get("markPrice")
            or payload.get("market_price")
            or payload.get("price")
        )

        unrealized = _coerce_float(
            payload.get("unrealized_pnl")
            or payload.get("unrealizedPnl")
            or payload.get("unrealizedPnL")
            or payload.get("pnl")
        )

        if unrealized is None and entry_price is not None and current_price is not None:
            try:
                position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=abs(entry_price) if quantity else 0.0,
                )
                position.mark_to_market(abs(current_price))
                unrealized = position.unrealized_pnl
                entry_price = position.entry_price or entry_price
                current_price = position.current_price or current_price
            except ValueError:
                # Fall back to raw values when payload cannot be coerced into Position.
                pass

        return PositionSnapshot(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized,
        )


def _trade_attributes_provider(request: Request, _: AdminIdentity) -> Mapping[str, Any]:
    """Extract trade-related attributes for RBAC evaluation."""

    def _normalise_header(name: str) -> str | None:
        value = request.headers.get(name)
        if value is None:
            return None
        candidate = value.strip()
        return candidate or None

    attributes: dict[str, Any] = {}

    environment = _normalise_header("X-Trade-Environment")
    if environment is not None:
        attributes["environment"] = environment

    desk = _normalise_header("X-Trade-Desk")
    if desk is not None:
        attributes["desk"] = desk

    return attributes


class SystemAccess:
    """Coordinator exposing TradePulse system capabilities over REST."""

    def __init__(
        self,
        system: TradePulseSystem,
        *,
        logger: logging.Logger | None = None,
        notifier: NotificationDispatcher | None = None,
        audit_trail: AuditTrail | None = None,
    ) -> None:
        self._system = system
        self._started_at = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()
        self._normaliser = _PositionNormaliser()
        self._connected: set[str] = set()
        self._version = _read_version()
        self._logger = logger or logging.getLogger("tradepulse.system_access")
        self._notifier = notifier
        self._audit_trail = audit_trail or get_system_audit_trail()
        self._auditable_levels = {"info", "warning", "error", "critical"}

    @property
    def version(self) -> str:
        return self._version

    def _log(
        self,
        level: str,
        message: str,
        *,
        identity: AdminIdentity | None = None,
        **fields: Any,
    ) -> None:
        logger_method = getattr(self._logger, level, None)
        if (
            logger_method is None
        ):  # pragma: no cover - defensive guard for invalid level
            raise AttributeError(f"Unsupported log level requested: {level}")
        audit_subject = identity.subject if identity is not None else None
        logger_payload = {"event": message, **fields}
        if audit_subject is not None:
            logger_payload.setdefault("subject", audit_subject)
        logger_method(message, extra=logger_payload)

        if self._audit_trail is not None and level.lower() in self._auditable_levels:
            try:
                self._audit_trail.record(
                    message,
                    severity=level.lower(),
                    subject=audit_subject,
                    details=fields,
                )
            except AuditTrailError:
                self._logger.error(
                    "system.audit.write_failed",
                    extra={"event": message, "severity": level.lower()},
                    exc_info=True,
                )

    async def _notify_order_event(
        self,
        event: str,
        *,
        subject: str,
        message: str,
        metadata: Mapping[str, Any],
    ) -> None:
        if self._notifier is None:
            return
        await self._notifier.dispatch(
            event, subject=subject, message=message, metadata=metadata
        )

    @staticmethod
    def _actor(identity: AdminIdentity | None) -> str:
        return identity.subject if identity is not None else "anonymous"

    def status(self, identity: AdminIdentity | None = None) -> StatusResponse:
        uptime = max(
            0.0,
            (datetime.now(timezone.utc) - self._started_at).total_seconds(),
        )
        kill_switch = self._system.risk_manager.kill_switch.is_triggered()
        status_value = "halted" if kill_switch else "running"
        self._log(
            "debug",
            "system.status",
            identity=identity,
            uptime_seconds=uptime,
            kill_switch_engaged=kill_switch,
        )
        return StatusResponse(
            status=status_value, uptime_seconds=uptime, version=self._version
        )

    def _default_venue(self) -> str:
        names = self._system.connector_names
        if not names:
            raise RuntimeError("TradePulseSystem has no configured execution venues")
        return names[0]

    def _ensure_connected(
        self, venue: str, *, identity: AdminIdentity | None = None
    ) -> None:
        key = venue.lower()
        if key in self._connected:
            self._log(
                "debug", "system.connector.cached", identity=identity, venue=venue
            )
            return
        connector = self._system.get_connector(venue)
        actor = self._actor(identity)
        roles = identity.roles if identity is not None else ()
        try:
            credentials = self._system.connector_credentials(
                venue, actor=actor, roles=roles
            )
        except AccessDeniedError as exc:
            self._log(
                "warning",
                "system.connector.access_denied",
                identity=identity,
                venue=venue,
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        self._log("debug", "system.connector.connect", identity=identity, venue=venue)
        try:
            connector.connect(credentials)
        except Exception as exc:  # pragma: no cover - connector implementations vary
            self._log(
                "error",
                "system.connector.connect_failed",
                identity=identity,
                venue=venue,
                error=str(exc),
            )
            raise
        self._connected.add(key)
        self._log("info", "system.connector.connected", identity=identity, venue=venue)

    async def list_positions(
        self, *, identity: AdminIdentity | None = None
    ) -> PositionsResponse:
        self._log("info", "system.positions.fetch", identity=identity)
        snapshots: list[PositionSnapshot] = []
        for venue in self._system.connector_names:
            connector = self._system.get_connector(venue)
            self._ensure_connected(venue, identity=identity)
            try:
                raw_positions = connector.get_positions()
            except Exception as exc:  # pragma: no cover - defensive
                self._log(
                    "error",
                    "system.positions.error",
                    identity=identity,
                    venue=venue,
                    error=str(exc),
                )
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to fetch positions from venue '{venue}': {exc}",
                ) from exc
            for payload in raw_positions:
                try:
                    snapshot = self._normaliser.normalise(payload)
                except Exception as exc:  # pragma: no cover - defensive
                    self._log(
                        "error",
                        "system.positions.normalize_failed",
                        identity=identity,
                        venue=venue,
                        error=str(exc),
                    )
                    raise HTTPException(
                        status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to normalise position payload from '{venue}': {exc}",
                    ) from exc
                snapshots.append(snapshot)
        self._log(
            "debug",
            "system.positions.fetched",
            identity=identity,
            venues=list(self._system.connector_names),
            position_count=len(snapshots),
        )
        return PositionsResponse(positions=snapshots)

    async def place_order(
        self,
        request: OrderRequest,
        identity: AdminIdentity | None = None,
    ) -> OrderResponse:
        venue = request.venue or self._default_venue()
        connector = self._system.get_connector(venue)
        actor = self._actor(identity)
        self._log(
            "info",
            "system.orders.submit",
            identity=identity,
            venue=venue,
            symbol=request.symbol,
            side=request.side.value,
            quantity=request.quantity,
            order_type=request.order_type.value,
        )
        async with self._lock:
            self._ensure_connected(venue, identity=identity)
            risk_price = request.price or request.reference_price
            if risk_price is None or risk_price <= 0:
                self._log(
                    "warning",
                    "system.orders.invalid_reference_price",
                    identity=identity,
                    venue=venue,
                    symbol=request.symbol,
                )
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="reference price must be positive",
                )
            try:
                self._system.risk_manager.validate_order(
                    request.symbol,
                    request.side.value,
                    request.quantity,
                    risk_price,
                )
            except Exception as exc:
                self._log(
                    "warning",
                    "system.orders.risk_rejected",
                    identity=identity,
                    venue=venue,
                    symbol=request.symbol,
                    error=str(exc),
                )
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(exc),
                ) from exc

            order = Order(
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                price=request.price,
                order_type=request.order_type,
            )

            placed: Order
            try:
                placed = connector.place_order(
                    order, idempotency_key=request.client_order_id
                )
            except Exception as exc:
                self._log(
                    "error",
                    "system.orders.connector_error",
                    identity=identity,
                    venue=venue,
                    symbol=request.symbol,
                    error=str(exc),
                )
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=f"Connector rejected order submission: {exc}",
                ) from exc

            if placed.filled_quantity > 0:
                fill_price = placed.average_price or placed.price
                if fill_price:
                    try:
                        self._system.risk_manager.register_fill(
                            placed.symbol,
                            placed.side.value,
                            placed.filled_quantity,
                            float(fill_price),
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        # Risk updates are best-effort; surfacing the order response takes precedence.
                        # Log the error for debugging and audit purposes.
                        self._logger.warning(
                            "Failed to register fill with risk manager",
                            extra={
                                "event": "system.orders.risk_register_fill_failed",
                                "symbol": placed.symbol,
                                "side": placed.side.value,
                                "quantity": placed.filled_quantity,
                                "price": float(fill_price),
                                "error": str(exc),
                                "error_type": type(exc).__name__,
                            },
                            exc_info=True,
                        )

            dto = order_to_dto(placed)
            response = OrderResponse(
                order_id=dto.get("order_id"),
                status=str(dto.get("status", placed.status.value)),
                filled_quantity=float(
                    dto.get("filled_quantity", placed.filled_quantity)
                ),
                average_price=_coerce_float(dto.get("average_price")),
            )

        metadata = {
            "actor": actor,
            "venue": venue,
            "symbol": request.symbol,
            "side": request.side.value,
            "quantity": request.quantity,
            "order_type": request.order_type.value,
            "status": response.status,
            "order_id": response.order_id,
            "filled_quantity": response.filled_quantity,
            "average_price": response.average_price,
        }
        self._log(
            "info",
            "system.orders.accepted",
            identity=identity,
            venue=venue,
            symbol=request.symbol,
            status=response.status,
            order_id=response.order_id,
            filled_quantity=response.filled_quantity,
        )
        await self._notify_order_event(
            "order.submitted",
            subject=f"Order {response.status.upper()} - {request.symbol}",
            message=(
                f"{actor} submitted a {request.side.value} order for {request.quantity} "
                f"{request.symbol} on {venue}. Status: {response.status}."
            ),
            metadata=metadata,
        )
        return response


def _get_access(request: Request) -> SystemAccess:
    access = getattr(request.app.state, "system_access", None)
    if not isinstance(access, SystemAccess):  # pragma: no cover - defensive
        raise RuntimeError("SystemAccess not initialised on application state")
    return access


def _resolve_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        for part in forwarded_for.split(","):
            candidate = part.strip().split()[0]
            if candidate:
                return candidate

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def create_system_app(
    system: TradePulseSystem,
    *,
    identity_dependency: (
        Callable[..., Awaitable[AdminIdentity] | AdminIdentity] | None
    ) = None,
    reader_roles: Sequence[str] = ("foundation:viewer",),
    trader_roles: Sequence[str] = ("trading:operator",),
    authorization_gateway: AuthorizationGateway | None = None,
    notification_dispatcher: NotificationDispatcher | None = None,
    notification_settings: NotificationSettings | None = None,
    log_sink: Callable[[dict[str, Any]], None] | None = None,
    log_level: int | str = logging.INFO,
    runtime_settings: BackendRuntimeSettings | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
    rate_limit_settings: ApiRateLimitSettings | None = None,
) -> FastAPI:
    """Instantiate a FastAPI app exposing TradePulse system endpoints.

    Args:
        system: TradePulse orchestration facade powering the API.
        rate_limiter: Optional limiter enforcing per-subject/IP throughput.
        rate_limit_settings: Settings used to build a limiter when one is not
            explicitly supplied.
    """

    provided_settings = runtime_settings is not None
    runtime_settings = runtime_settings or BackendRuntimeSettings()
    if not provided_settings and log_level != logging.INFO:
        runtime_settings = runtime_settings.model_copy(update={"log_level": log_level})
    resolved_log_level = runtime_settings.resolve_log_level()
    root_logger = logging.getLogger()
    if runtime_settings.should_configure_logging(
        handlers_installed=bool(root_logger.handlers),
        sink_provided=log_sink is not None,
    ):
        configure_logging(level=resolved_log_level, sink=log_sink)
    else:
        root_logger.setLevel(resolved_log_level)

    base_dependency = identity_dependency or verify_request_identity()

    def _gateway_dependency() -> AuthorizationGateway:
        if authorization_gateway is not None:
            return authorization_gateway
        return get_authorization_gateway()

    reader_dependency = require_permission(
        "system.status",
        "read",
        identity_dependency=base_dependency,
        gateway_dependency=_gateway_dependency,
    )
    positions_dependency = require_permission(
        "system.positions",
        "read",
        identity_dependency=base_dependency,
        gateway_dependency=_gateway_dependency,
    )
    trader_dependency = require_permission(
        "orders",
        "submit",
        identity_dependency=base_dependency,
        attributes_provider=_trade_attributes_provider,
        gateway_dependency=_gateway_dependency,
    )

    resolved_rate_limit_settings = rate_limit_settings or ApiRateLimitSettings()
    limiter = rate_limiter or build_rate_limiter(resolved_rate_limit_settings)

    notifier = notification_dispatcher or _build_notification_dispatcher(
        notification_settings
    )
    logger = logging.getLogger("tradepulse.system_access")
    access = SystemAccess(
        system,
        logger=logger,
        notifier=notifier,
        audit_trail=get_system_audit_trail(),
    )

    app = FastAPI(
        title="TradePulse System API",
        version=access.version,
        debug=runtime_settings.debug,
    )
    app.state.system_access = access
    app.state.notification_dispatcher = notifier
    app.add_middleware(
        AccessLogMiddleware,
        audit_trail=get_access_audit_trail(),
        service="system_api",
        capture_headers=("x-request-id", "x-correlation-id", "traceparent"),
    )

    inspector = VariableInspector(
        redact_patterns=runtime_settings.redact_pattern_values()
    )
    if runtime_settings.inspect_variables:
        inspector.register(
            "environment",
            lambda: inspector.collect_environment(runtime_settings.inspect_variables),
        )

    def _system_snapshot() -> dict[str, Any]:
        connectors = sorted(system.connector_names)
        connected = sorted(access._connected)
        risk_manager = getattr(system, "risk_manager", None)
        kill_switch = getattr(risk_manager, "kill_switch", None)
        try:
            engaged = (
                bool(kill_switch.is_triggered()) if kill_switch is not None else None
            )
        except Exception:  # pragma: no cover - defensive guard
            engaged = None
        reason = getattr(kill_switch, "reason", None)
        return {
            "version": access.version,
            "connectors": connectors,
            "connected": connected,
            "kill_switch_engaged": engaged,
            "kill_switch_reason": reason,
        }

    inspector.register("system", _system_snapshot)
    inspector.register(
        "runtime",
        lambda: {
            "debug": runtime_settings.debug,
            "log_level": logging.getLevelName(resolved_log_level),
        },
    )
    inspector.register(
        "notifications",
        lambda: {
            "dispatcher": type(notifier).__name__ if notifier is not None else None,
            "email_configured": bool(
                notification_settings and notification_settings.email
            ),
            "slack_configured": bool(
                notification_settings and notification_settings.slack_webhook_url
            ),
        },
    )
    inspector.register("rate_limiter", limiter.snapshot)
    app.state.variable_inspector = inspector
    app.state.runtime_settings = runtime_settings
    app.state.rate_limiter = limiter
    app.state.rate_limit_settings = resolved_rate_limit_settings
    if runtime_settings.debug and runtime_settings.log_variables_on_startup:
        debug_logger = logging.getLogger("tradepulse.debug")

        @app.on_event("startup")
        async def _log_system_debug_snapshot() -> None:
            snapshot = await inspector.snapshot()
            debug_logger.debug(
                "debug.variables.snapshot",
                extra={"variables": snapshot, "component": "system_access"},
            )

    def _wrap_with_rate_limit(
        dependency: Callable[..., Awaitable[AdminIdentity] | AdminIdentity],
    ) -> Callable[..., Awaitable[AdminIdentity]]:
        async def _precheck_rate_limit(
            request: Request,
        ) -> Callable[[AdminIdentity | None], Awaitable[None]]:
            ip_address = _resolve_ip(request)
            await limiter.check(subject=None, ip_address=ip_address)

            async def _finalize(identity: AdminIdentity | None) -> None:
                if identity is None:
                    return
                subject = getattr(identity, "subject", None)
                if subject is None:
                    return
                await limiter.check(subject=subject, ip_address=ip_address)

            return _finalize

        async def _rate_limited_dependency(
            request: Request,
            finalize: Callable[[AdminIdentity | None], Awaitable[None]] = Depends(
                _precheck_rate_limit
            ),
            identity: AdminIdentity = Depends(dependency),
        ) -> AdminIdentity:
            await finalize(identity)
            return identity

        return _rate_limited_dependency

    rate_limited_reader_dependency = _wrap_with_rate_limit(reader_dependency)
    rate_limited_positions_dependency = _wrap_with_rate_limit(positions_dependency)
    rate_limited_trader_dependency = _wrap_with_rate_limit(trader_dependency)

    install_debug_routes(
        app,
        inspector=inspector,
        enabled=runtime_settings.debug,
        identity_dependency=rate_limited_reader_dependency,
    )

    @app.get("/api/v1/status", response_model=StatusResponse, tags=["system"])
    async def read_status(
        identity: AdminIdentity = Depends(rate_limited_reader_dependency),
        access: SystemAccess = Depends(_get_access),
    ) -> StatusResponse:
        return access.status(identity)

    @app.get("/api/v1/positions", response_model=PositionsResponse, tags=["system"])
    async def read_positions(
        identity: AdminIdentity = Depends(rate_limited_positions_dependency),
        access: SystemAccess = Depends(_get_access),
    ) -> PositionsResponse:
        return await access.list_positions(identity=identity)

    @app.post(
        "/api/v1/orders",
        response_model=OrderResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["system"],
    )
    async def submit_order(
        payload: OrderRequest,
        identity: AdminIdentity = Depends(rate_limited_trader_dependency),
        access: SystemAccess = Depends(_get_access),
    ) -> OrderResponse:
        return await access.place_order(payload, identity=identity)

    register_exception_handlers(app)

    return app


__all__ = [
    "SystemAccess",
    "create_system_app",
    "OrderRequest",
    "OrderResponse",
    "PositionsResponse",
    "PositionSnapshot",
    "StatusResponse",
]
