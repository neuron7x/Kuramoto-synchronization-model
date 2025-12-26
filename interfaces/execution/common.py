"""Shared utilities for authenticated execution connectors."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum, auto
from queue import Empty, Queue
from typing import Any, Callable, Dict, Iterable, Mapping

import httpx

try:  # pragma: no cover - optional dependency guard
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - library not installed

    def load_dotenv(*_: object, **__: object) -> None:
        """Fallback noop when python-dotenv is not available."""

else:
    load_dotenv()


from execution.connectors import ExecutionConnector

VaultResolver = Callable[[str], Mapping[str, str]]
RotationHook = Callable[[Mapping[str, str]], None]
TimestampExtractor = Callable[[httpx.Response], float | None]


class CredentialError(RuntimeError):
    """Raised when credentials are missing or invalid."""


@dataclass(slots=True)
class APICredentials:
    """Simple container for API credentials."""

    api_key: str
    api_secret: str
    passphrase: str | None = None
    extra: Mapping[str, str] = field(default_factory=dict)


class CredentialProvider:
    """Load credentials from environment variables or a Vault resolver."""

    def __init__(
        self,
        env_prefix: str,
        *,
        required_keys: Iterable[str] = ("API_KEY", "API_SECRET"),
        optional_keys: Iterable[str] | None = None,
        vault_resolver: VaultResolver | None = None,
        vault_path: str | None = None,
        vault_path_env: str | None = None,
        rotation_hook: RotationHook | None = None,
    ) -> None:
        self.env_prefix = env_prefix
        self.required_keys = tuple(required_keys)
        self.optional_keys = tuple(optional_keys or ())
        self.vault_resolver = vault_resolver
        self._vault_path = vault_path
        self._vault_path_env = vault_path_env
        self.rotation_hook = rotation_hook
        self._cache: Mapping[str, str] | None = None
        self._lock = threading.Lock()

    def _load_from_env(self) -> Dict[str, str]:
        values: Dict[str, str] = {}
        prefix = self.env_prefix.upper()
        for key in (*self.required_keys, *self.optional_keys):
            env_key = f"{prefix}_{key.upper()}"
            value = os.getenv(env_key)
            if value:
                values[key.upper()] = value
        return values

    def _load_from_vault(self) -> Dict[str, str]:
        if not self.vault_resolver:
            return {}
        vault_path = self._vault_path
        if not vault_path:
            env_name = self._vault_path_env or f"{self.env_prefix.upper()}_VAULT_PATH"
            vault_path = os.getenv(env_name)
        if not vault_path:
            return {}
        payload = self.vault_resolver(vault_path)
        if not isinstance(payload, Mapping):
            raise CredentialError(
                "Vault resolver must return a mapping of credential keys to values"
            )
        return {str(k).upper(): str(v) for k, v in payload.items()}

    def load(self, *, force: bool = False) -> Mapping[str, str]:
        with self._lock:
            if self._cache is not None and not force:
                return self._cache
            values = {}
            values.update(self._load_from_vault())
            values.update(self._load_from_env())
            missing = [key for key in self.required_keys if key.upper() not in values]
            if missing:
                raise CredentialError(
                    f"Missing credential values for {', '.join(missing)} (prefix={self.env_prefix})"
                )
            self._cache = values
            return values

    def rotate(self, new_values: Mapping[str, str] | None = None) -> Mapping[str, str]:
        if new_values is not None:
            normalized = {k.upper(): v for k, v in new_values.items()}
            missing = [
                key for key in self.required_keys if key.upper() not in normalized
            ]
            if missing:
                raise CredentialError(
                    "Cannot rotate credentials because required keys are missing: "
                    + ", ".join(missing)
                )
            with self._lock:
                self._cache = normalized
        else:
            with self._lock:
                self._cache = None
            normalized = self.load(force=True)
        if self.rotation_hook:
            self.rotation_hook(normalized)
        return normalized


class HMACSigner:
    """Helper for computing HMAC signatures for authenticated requests."""

    def __init__(self, secret: str, *, algorithm: str = "sha256") -> None:
        self.secret = secret.encode()
        self.algorithm = algorithm

    def sign(self, payload: str) -> str:
        digest = hmac.new(
            self.secret, payload.encode(), getattr(hashlib, self.algorithm)
        )
        return digest.hexdigest()


class HTTPBackoffController:
    """Adaptive rate limiter/backoff controller for REST calls."""

    def __init__(
        self,
        *,
        base_delay: float = 0.25,
        max_delay: float = 8.0,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        if base_delay <= 0:
            raise ValueError("base_delay must be positive")
        if max_delay < base_delay:
            raise ValueError("max_delay must be greater than or equal to base_delay")
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self._lock = threading.Lock()
        self._backoff_until: float = 0.0
        self._attempts: int = 0
        self._throttle_events: int = 0

    def throttle(self) -> None:
        with self._lock:
            delay = self._backoff_until - self._clock()
        if delay > 0:
            self._throttle_events += 1
            self._sleep(delay)

    def reset(self) -> None:
        with self._lock:
            self._attempts = 0
            self._backoff_until = 0.0
            self._throttle_events = 0

    def backoff(self, response: httpx.Response | None = None) -> None:
        with self._lock:
            self._attempts += 1
            exponential = min(
                self.base_delay * (2 ** (self._attempts - 1)), self.max_delay
            )
            delay = random.uniform(self.base_delay, exponential)
            if response is not None:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
            self._backoff_until = self._clock() + delay
        self._sleep(delay)


class CircuitBreakerState(Enum):
    """States for :class:`CircuitBreaker`."""

    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a request is blocked by an open circuit breaker."""


class CircuitBreaker:
    """Circuit breaker tracking consecutive failures with half-open recovery."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_success_threshold: int = 2,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if half_open_success_threshold <= 0:
            raise ValueError("half_open_success_threshold must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at: float | None = None

    def before_call(self) -> None:
        with self._lock:
            now = self._clock()
            if self._state is CircuitBreakerState.OPEN:
                assert self._opened_at is not None
                if now - self._opened_at >= self.recovery_timeout:
                    self._state = CircuitBreakerState.HALF_OPEN
                    self._successes = 0
                else:
                    raise CircuitBreakerOpenError("Circuit breaker open")

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.half_open_success_threshold:
                    self._transition_to_closed()
            else:
                self._transition_to_closed()

    def record_failure(self, _: Exception | None = None) -> None:
        with self._lock:
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._trip(now=self._clock())
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._trip(now=self._clock())

    def _trip(self, *, now: float) -> None:
        self._state = CircuitBreakerState.OPEN
        self._opened_at = now
        self._failures = 0
        self._successes = 0

    def _transition_to_closed(self) -> None:
        self._state = CircuitBreakerState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at = None


@dataclass(slots=True)
class _DuplicateRecord:
    digest: str
    first_seen: float
    last_seen: float


class DuplicateResponseDetector:
    """Track response hashes and flag duplicates for downstream consumers."""

    def __init__(
        self,
        *,
        ttl: float = 30.0,
        max_entries: int = 512,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if ttl <= 0:
            raise ValueError("ttl must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl = ttl
        self._max_entries = max_entries
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._records: "OrderedDict[str, _DuplicateRecord]" = OrderedDict()

    def register(
        self, fingerprint: str, response: httpx.Response
    ) -> tuple[bool, float | None]:
        payload = response.content
        digest = hashlib.sha256(payload).hexdigest()
        now = self._clock()
        with self._lock:
            self._purge(now)
            existing = self._records.get(fingerprint)
            if existing and existing.digest == digest:
                existing.last_seen = now
                self._records.move_to_end(fingerprint)
                return True, existing.first_seen
            self._records[fingerprint] = _DuplicateRecord(
                digest=digest, first_seen=now, last_seen=now
            )
            if len(self._records) > self._max_entries:
                self._records.popitem(last=False)
            return False, None

    def _purge(self, now: float) -> None:
        expiration = now - self._ttl
        expired = [
            key
            for key, record in self._records.items()
            if record.last_seen < expiration
        ]
        for key in expired:
            self._records.pop(key, None)


class ConnectionHealthMonitor:
    """Track websocket heartbeats to detect unhealthy connections."""

    def __init__(self, *, heartbeat_interval: float = 30.0) -> None:
        self.heartbeat_interval = heartbeat_interval
        self._lock = threading.Lock()
        self._last_heartbeat = time.monotonic()

    def touch(self) -> None:
        with self._lock:
            self._last_heartbeat = time.monotonic()

    def is_stale(self) -> bool:
        with self._lock:
            return time.monotonic() - self._last_heartbeat > self.heartbeat_interval * 2


class IdempotencyStore:
    """In-memory idempotency key registry with reconciliation support."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, Mapping[str, str]] = {}

    def get(self, key: str) -> Mapping[str, str] | None:
        with self._lock:
            return self._records.get(key)

    def put(self, key: str, payload: Mapping[str, str]) -> None:
        with self._lock:
            self._records[key] = dict(payload)

    def reconcile(
        self,
        key: str,
        fetcher: Callable[[Mapping[str, str]], Mapping[str, str] | None],
    ) -> Mapping[str, str] | None:
        """Ensure previously stored state matches remote data."""

        record = self.get(key)
        if not record:
            return None
        remote = fetcher(record)
        if remote is None:
            return None
        if remote.get("order_id") == record.get("order_id"):
            return remote
        # Update cached mapping to remote canonical state
        self.put(key, remote)
        return remote


def parse_server_time(response: httpx.Response) -> float | None:
    """Attempt to parse a timestamp from HTTP response headers."""

    date_header = response.headers.get("Date")
    if date_header:
        try:
            parsed = parsedate_to_datetime(date_header)
        except (ValueError, TypeError):
            # Invalid date format in header - expected case
            parsed = None
        if parsed is not None:
            return parsed.timestamp()
    server_time = response.headers.get("X-Server-Time") or response.headers.get(
        "Server-Time"
    )
    if server_time:
        try:
            return (
                float(server_time) / 1000
                if len(server_time) > 11
                else float(server_time)
            )
        except ValueError:
            return None
    return None


def ensure_timestamp_skew(response: httpx.Response, *, max_skew: float = 5.0) -> None:
    """Validate that the server time is within the allowed skew."""

    server_ts = parse_server_time(response)
    if server_ts is None:
        return
    local_ts = datetime.now(timezone.utc).timestamp()
    if abs(local_ts - server_ts) > max_skew:
        raise RuntimeError(
            f"Timestamp skew exceeds tolerance: local={local_ts}, server={server_ts}"
        )


def is_rate_limited(response: httpx.Response) -> bool:
    """Return True when the response indicates a rate limit condition."""

    if response.status_code == 429:
        return True
    headers = {k.lower(): v for k, v in response.headers.items()}
    remaining = headers.get("x-ratelimit-remaining")
    if remaining is not None:
        try:
            if float(remaining) <= 0:
                return True
        except ValueError:
            pass
    if "retry-after" in headers:
        return True
    return False


class AuthenticatedRESTExecutionConnector(ExecutionConnector):
    """Base class bundling authentication, rate limiting and WS plumbing."""

    def __init__(
        self,
        env_prefix: str,
        *,
        sandbox: bool = True,
        base_url: str,
        sandbox_url: str | None = None,
        ws_url: str | None = None,
        sandbox_ws_url: str | None = None,
        credential_provider: CredentialProvider | None = None,
        optional_credential_keys: Iterable[str] | None = None,
        vault_resolver: VaultResolver | None = None,
        vault_path: str | None = None,
        vault_path_env: str | None = None,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
        backoff: HTTPBackoffController | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        duplicate_detector: DuplicateResponseDetector | None = None,
        health_monitor: ConnectionHealthMonitor | None = None,
        ws_factory: Callable[[str], Any] | None = None,
        enable_stream: bool = True,
        timeout: float = 10.0,
        max_retries: int = 5,
    ) -> None:
        super().__init__(sandbox=sandbox)
        self.env_prefix = env_prefix
        self._base_url = (sandbox_url if sandbox and sandbox_url else base_url).rstrip(
            "/"
        )
        self._ws_url = sandbox_ws_url if sandbox and sandbox_ws_url else ws_url
        self._timeout = timeout
        self._transport = transport
        if max_retries <= 0:
            raise ValueError("max_retries must be positive")
        self._max_retries = max_retries
        self._credential_provider = credential_provider or CredentialProvider(
            env_prefix,
            optional_keys=optional_credential_keys,
            vault_resolver=vault_resolver,
            vault_path=vault_path,
            vault_path_env=vault_path_env,
        )
        self._http_client = http_client
        self._backoff = backoff or HTTPBackoffController()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._duplicate_detector = duplicate_detector or DuplicateResponseDetector()
        self._health = health_monitor or ConnectionHealthMonitor()
        self._ws_factory = ws_factory or self._default_ws_factory
        self._ws_enabled = enable_stream and self._ws_url is not None
        self._ws_thread: threading.Thread | None = None
        self._ws_stop = threading.Event()
        self._event_queue: "Queue[dict[str, Any]]" = Queue()
        self._credentials: Mapping[str, str] | None = None
        self._signer: HMACSigner | None = None
        self._rotation_attempted = False
        self._idempotency_store = IdempotencyStore()

    @property
    def credentials(self) -> Mapping[str, str]:
        if self._credentials is None:
            raise CredentialError("Connector is not connected")
        return self._credentials

    def connect(self, credentials: Mapping[str, str] | None = None) -> None:
        if credentials is not None:
            self._credentials = self._credential_provider.rotate(credentials)
        else:
            self._credentials = self._credential_provider.load()
        self._signer = self._create_signer(self.credentials)
        if self._http_client is None:
            timeout_config = httpx.Timeout(
                self._timeout, connect=self._timeout, read=self._timeout * 3
            )
            self._http_client = httpx.Client(
                base_url=self._base_url,
                timeout=timeout_config,
                transport=self._transport,
                headers=self._default_headers(),
            )
        if self._ws_enabled:
            self._start_streaming()

    def disconnect(self) -> None:
        self._ws_stop.set()
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2.0)
        self._ws_thread = None
        if self._http_client is not None:
            self._http_client.close()
        self._http_client = None
        self._credentials = None
        self._signer = None
        self._rotation_attempted = False

    # --- Hook points -------------------------------------------------

    def _default_headers(self) -> dict[str, str]:
        return {}

    def _create_signer(self, credentials: Mapping[str, str]) -> HMACSigner:
        return HMACSigner(credentials["API_SECRET"])

    def _apply_signature(
        self,
        method: str,
        path: str,
        params: dict[str, Any],
        headers: dict[str, str],
        body: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
        return params, headers, body

    def _handle_stream_payload(self, payload: dict[str, Any]) -> None:
        self._event_queue.put(payload)

    @staticmethod
    def _normalise_component(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): AuthenticatedRESTExecutionConnector._normalise_component(val)
                for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, (list, tuple, set)):
            return [
                AuthenticatedRESTExecutionConnector._normalise_component(item)
                for item in value
            ]
        if isinstance(value, (bytes, bytearray)):
            try:
                return value.decode()
            except UnicodeDecodeError:
                # Binary data that cannot be decoded to UTF-8; return hex representation
                return value.hex()
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _fingerprint_request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        body: Mapping[str, Any] | None,
        idempotency_key: str | None,
    ) -> str:
        payload = {
            "method": method,
            "path": path,
            "params": self._normalise_component(params or {}),
            "body": self._normalise_component(body or {}),
            "idempotency_key": idempotency_key,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode()).hexdigest()

    # --- HTTP helpers -------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        signed: bool = True,
        allow_retry: bool = True,
        idempotency_key: str | None = None,
        idempotent: bool | None = None,
        request_timeout: float | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._http_client is None:
            raise RuntimeError("HTTP client is not initialised")
        params = dict(params or {})
        headers = dict(headers or {})
        request_kwargs = dict(kwargs)
        timeout_override = (
            request_timeout
            if request_timeout is not None
            else request_kwargs.pop("timeout", None)
        )
        effective_timeout = (
            timeout_override if timeout_override is not None else self._timeout
        )
        normalized_method = method.upper()
        if idempotent is None:
            idempotent = normalized_method in {
                "GET",
                "HEAD",
                "OPTIONS",
                "DELETE",
                "PUT",
            }
            if normalized_method in {"POST", "PATCH"} and idempotency_key is not None:
                idempotent = True
        max_attempts = self._max_retries if allow_retry and idempotent else 1
        fingerprint = self._fingerprint_request(
            normalized_method, path, params, body, idempotency_key
        )
        attempt = 0
        last_error: Exception | None = None
        while attempt < max_attempts:
            attempt += 1
            self._backoff.throttle()
            self._circuit_breaker.before_call()
            req_params = dict(params)
            req_headers = dict(headers)
            if idempotency_key is not None:
                req_headers.setdefault("Idempotency-Key", idempotency_key)
            req_body = dict(body) if body is not None else None
            if signed:
                if self._signer is None:
                    raise CredentialError("Cannot sign request without credentials")
                req_params, req_headers, req_body = self._apply_signature(
                    method, path, req_params, req_headers, req_body
                )
            try:
                response = self._http_client.request(
                    method,
                    path,
                    params=req_params or None,
                    json=req_body if req_body is not None else None,
                    headers=req_headers or None,
                    timeout=effective_timeout,
                    **request_kwargs,
                )
            except httpx.RequestError as exc:
                self._circuit_breaker.record_failure(exc)
                last_error = exc
                if not allow_retry or attempt >= max_attempts:
                    raise
                self._backoff.backoff(None)
                continue
            try:
                ensure_timestamp_skew(response)
            except RuntimeError:
                response.raise_for_status()
            status = response.status_code
            if is_rate_limited(response):
                self._circuit_breaker.record_failure(None)
                if not allow_retry or attempt >= max_attempts:
                    _LOG.info(
                        "Rate limit encountered",
                        extra={
                            "event": "connector.rate_limit",
                            "env": self.env_prefix,
                            "status": status,
                        },
                    )
                    response.raise_for_status()
                self._backoff.backoff(response)
                continue
            if status in (401, 403) and allow_retry:
                self._circuit_breaker.record_failure(None)
                if self._rotation_attempted:
                    response.raise_for_status()
                self._refresh_credentials()
                self._rotation_attempted = True
                attempt -= 1  # allow another authenticated attempt
                continue
            if status >= 500:
                self._circuit_breaker.record_failure(None)
                if not allow_retry or attempt >= max_attempts:
                    response.raise_for_status()
                self._backoff.backoff(response)
                continue
            if not response.is_success:
                self._circuit_breaker.record_failure(None)
                response.raise_for_status()
            self._rotation_attempted = False
            self._backoff.reset()
            self._circuit_breaker.record_success()
            duplicate, first_seen = self._duplicate_detector.register(
                fingerprint, response
            )
            response.extensions["tradepulse_duplicate"] = duplicate
            if duplicate and first_seen is not None:
                response.extensions["tradepulse_duplicate_first_seen"] = first_seen
            return response
        if last_error is not None:
            raise last_error
        raise RuntimeError("HTTP request failed without raising an exception")

    def _refresh_credentials(self) -> None:
        self._credentials = self._credential_provider.rotate()
        self._signer = self._create_signer(self.credentials)

    def set_credential_provider(self, provider: CredentialProvider) -> None:
        """Inject a pre-configured credential provider used for subsequent rotations."""

        self._credential_provider = provider
        self._credentials = None
        self._signer = None

    # --- Websocket handling ------------------------------------------

    def _start_streaming(self) -> None:
        if self._ws_thread and self._ws_thread.is_alive():
            return
        self._ws_stop.clear()
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()

    def _default_ws_factory(self, url: str) -> Any:
        if not url:
            raise RuntimeError("Websocket URL is not configured")
        try:
            from websockets.sync.client import connect
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise RuntimeError(
                "websockets library is required for streaming support"
            ) from exc
        return connect(url)

    def _ws_loop(self) -> None:
        if not self._ws_url:
            return
        backoff = 1.0
        while not self._ws_stop.is_set():
            try:
                ws_obj = self._ws_factory(self._ws_url)
                context = ws_obj if hasattr(ws_obj, "__enter__") else None
                if context is not None:
                    with context as ws:
                        self._consume_ws(ws)
                else:
                    ws = ws_obj
                    try:
                        self._consume_ws(ws)
                    finally:
                        close = getattr(ws, "close", None)
                        if callable(close):
                            close()
                backoff = 1.0
            except Exception:
                if self._ws_stop.wait(backoff + random.uniform(0, 0.5)):
                    return
                backoff = min(backoff * 2, 30.0)

    def _consume_ws(self, ws: Any) -> None:
        self._health.touch()
        while not self._ws_stop.is_set():
            try:
                message = ws.recv()
            except Exception:
                break
            if message is None:
                continue
            self._health.touch()
            payload = self._normalise_ws_message(message)
            if payload is not None:
                self._handle_stream_payload(payload)

    def _normalise_ws_message(self, message: Any) -> dict[str, Any] | None:
        if isinstance(message, bytes):
            try:
                message = message.decode()
            except UnicodeDecodeError:
                return None
        if isinstance(message, str):
            try:
                import json

                data = json.loads(message)
            except json.JSONDecodeError:
                # Invalid JSON in websocket message - expected case
                return None
            if isinstance(data, dict):
                return data
            return None
        if isinstance(message, dict):
            return message
        return None

    # --- Event helpers -----------------------------------------------

    def next_event(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            return self._event_queue.get(timeout=timeout)
        except Empty:
            return None

    def stream_is_healthy(self) -> bool:
        return not self._health.is_stale()
_LOG = logging.getLogger(__name__)
