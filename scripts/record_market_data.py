"""Script to record market data via REST and WebSocket with resiliency features."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from urllib.parse import quote

import aiohttp


DEFAULT_LOG_LEVEL = os.environ.get("MARKET_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=DEFAULT_LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
LOGGER = logging.getLogger("record_market_data")


class ConfigurationError(RuntimeError):
    """Raised when the runtime configuration is invalid."""


def safe_fsync(fd: int) -> None:
    """Best-effort fsync that tolerates unsupported filesystems."""

    try:
        os.fsync(fd)
    except OSError as exc:  # pragma: no cover - platform dependent
        LOGGER.debug("fsync failed for descriptor %s: %s", fd, exc)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        LOGGER.warning("Invalid float for %s, using default %s", name, default)
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        LOGGER.warning("Invalid int for %s, using default %s", name, default)
        return default


@dataclass
class Config:
    rest_url: str = os.environ.get("MARKET_REST_URL", "https://api.example.com")
    rest_endpoint: str = os.environ.get("MARKET_REST_ENDPOINT", "/v1/market/trades")
    websocket_url: str = os.environ.get("MARKET_WS_URL", "wss://stream.example.com/market")
    websocket_channel: str = os.environ.get("MARKET_WS_CHANNEL", "trades")
    symbol: str = os.environ.get("MARKET_SYMBOL", "BTC-USD")
    api_key: str = os.environ.get("MARKET_API_KEY", "")
    api_secret: str = os.environ.get("MARKET_API_SECRET", "")
    server_time_endpoint: str = os.environ.get("MARKET_SERVER_TIME_ENDPOINT", "/v1/time")
    output_path: Path = Path(os.environ.get("MARKET_OUTPUT_PATH", "data/market_data.jsonl"))
    state_path: Path = Path(os.environ.get("MARKET_STATE_PATH", "data/market_data.state.json"))
    rate_limit: int = env_int("MARKET_RATE_LIMIT", 60)
    rate_period: float = env_float("MARKET_RATE_PERIOD", 60.0)
    rest_page_size: int = env_int("MARKET_REST_PAGE_SIZE", 500)
    rest_retry_attempts: int = env_int("MARKET_REST_RETRIES", 5)
    rest_retry_base_delay: float = env_float("MARKET_REST_RETRY_BASE_DELAY", 1.0)
    rest_max_backoff: float = env_float("MARKET_REST_MAX_BACKOFF", 30.0)
    ws_max_retries: int = env_int("MARKET_WS_MAX_RETRIES", 10)
    ws_reconnect_base: float = env_float("MARKET_WS_RECONNECT_BASE", 2.0)
    ws_max_backoff: float = env_float("MARKET_WS_MAX_BACKOFF", 60.0)
    schema_required_fields: tuple[str, ...] = tuple(
        field.strip()
        for field in os.environ.get("MARKET_SCHEMA_FIELDS", "timestamp,price,volume").split(",")
        if field.strip()
    )
    timestamp_field: str = os.environ.get("MARKET_TIMESTAMP_FIELD", "timestamp")
    price_field: str = os.environ.get("MARKET_PRICE_FIELD", "price")
    volume_field: str = os.environ.get("MARKET_VOLUME_FIELD", "volume")
    websocket_sign_path: str = os.environ.get("MARKET_WS_SIGN_PATH", "/stream")
    json_indent: Optional[int] = (
        env_int("MARKET_JSON_INDENT", 0) or None
        if os.environ.get("MARKET_JSON_INDENT") is not None
        else None
    )

    def __post_init__(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._normalize()
        self._validate()

    def _normalize(self) -> None:
        schema = tuple(dict.fromkeys(self.schema_required_fields))
        if not schema:
            schema = (self.timestamp_field, self.price_field, self.volume_field)
        if self.timestamp_field not in schema:
            schema = schema + (self.timestamp_field,)
        self.schema_required_fields = schema
        if not self.websocket_sign_path.startswith("/"):
            self.websocket_sign_path = f"/{self.websocket_sign_path.lstrip('/')}"

    def _validate(self) -> None:
        if not self.api_key or not self.api_secret:
            raise ConfigurationError("API key and API secret must be provided")
        if self.rate_limit <= 0:
            raise ConfigurationError("Rate limit must be positive")
        if self.rate_period <= 0:
            raise ConfigurationError("Rate period must be positive")
        if self.rest_retry_attempts < 0:
            raise ConfigurationError("REST retry attempts must be non-negative")
        if self.rest_retry_base_delay <= 0:
            raise ConfigurationError("REST base delay must be positive")
        if self.rest_max_backoff <= 0:
            raise ConfigurationError("REST max backoff must be positive")
        if self.ws_reconnect_base <= 0:
            raise ConfigurationError("WebSocket reconnect base must be positive")
        if self.ws_max_backoff <= 0:
            raise ConfigurationError("WebSocket max backoff must be positive")


class RateLimiter:
    def __init__(self, max_calls: int, period: float) -> None:
        self.max_calls = max_calls
        self.period = period
        self._tokens = max_calls
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                deficit = 1 - self._tokens
                wait_time = max(deficit * (self.period / self.max_calls), 0.01)
            await asyncio.sleep(wait_time)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated_at
        if elapsed <= 0:
            return
        refill = elapsed * (self.max_calls / self.period)
        if refill > 0:
            self._tokens = min(self.max_calls, self._tokens + refill)
        self._updated_at = now


class TimeSynchronizer:
    def __init__(self) -> None:
        self.offset: float = 0.0

    def set_offset(self, server_ts_ms: int) -> None:
        local_ts_ms = int(time.time() * 1000)
        drift = (server_ts_ms - local_ts_ms) / 1000.0
        self.offset = drift
        if abs(drift) > 5:
            LOGGER.warning("Large time drift detected (%.3fs)", drift)
        else:
            LOGGER.info("Time drift corrected by %.3f seconds", drift)

    def now_ms(self) -> int:
        return int((time.time() + self.offset) * 1000)


class SessionState:
    def __init__(self, path: Path, output_path: Path, timestamp_field: str) -> None:
        self.path = path
        self.output_path = output_path
        self.timestamp_field = timestamp_field
        self.last_timestamp: Optional[float] = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._load_from_output()
            return
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            stored_ts = data.get("last_timestamp")
            if stored_ts is not None:
                self.last_timestamp = float(stored_ts)
            LOGGER.info("Loaded session state from %s (last_timestamp=%s)", self.path, self.last_timestamp)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Failed to read state file %s: %s", self.path, exc)
            self._load_from_output()

    def _load_from_output(self) -> None:
        if not self.output_path.exists():
            return
        try:
            with self.output_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                pos = handle.tell()
                buffer = bytearray()
                while pos > 0:
                    pos -= 1
                    handle.seek(pos)
                    char = handle.read(1)
                    if char == b"\n" and buffer:
                        break
                    buffer.extend(char)
                if buffer:
                    line = buffer[::-1].decode("utf-8")
                    record = json.loads(line)
                    ts_field = self.timestamp_field
                    raw_ts = record.get(ts_field, record.get("timestamp"))
                    if raw_ts is not None:
                        self.last_timestamp = float(raw_ts)
                        LOGGER.info(
                            "Recovered last timestamp %s from output", self.last_timestamp
                        )
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("Failed to recover from output file: %s", exc)

    def update(self, timestamp: float) -> None:
        self.last_timestamp = timestamp
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump({"last_timestamp": self.last_timestamp}, handle)
            handle.flush()
            safe_fsync(handle.fileno())
        tmp_path.replace(self.path)


class RecordValidator:
    def __init__(self, config: Config, initial_timestamp: Optional[float] = None) -> None:
        self.config = config
        self.last_timestamp: Optional[float] = initial_timestamp

    def validate(self, record: Dict[str, Any]) -> Dict[str, Any]:
        missing = [field for field in self.config.schema_required_fields if field not in record]
        if missing:
            raise ValueError(f"Record missing required fields: {missing}")
        timestamp_value = record[self.config.timestamp_field]
        try:
            timestamp = float(timestamp_value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Timestamp field must be numeric") from exc
        if timestamp <= 0:
            raise ValueError("Timestamp must be positive")
        if self.last_timestamp is not None and timestamp < self.last_timestamp:
            raise ValueError(
                f"Timestamp regression detected: {timestamp} < {self.last_timestamp}"
            )
        price_value = record.get(self.config.price_field)
        volume_value = record.get(self.config.volume_field)
        normalized = dict(record)
        for name, value in (
            (self.config.price_field, price_value),
            (self.config.volume_field, volume_value),
        ):
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Field {name} must be numeric") from exc
            if numeric < 0:
                raise ValueError(f"Field {name} must be non-negative")
            normalized[name] = numeric
        normalized[self.config.timestamp_field] = timestamp
        self.last_timestamp = timestamp
        return normalized


async def fetch_server_time(session: aiohttp.ClientSession, config: Config, rate_limiter: RateLimiter) -> Optional[int]:
    await rate_limiter.acquire()
    url = f"{config.rest_url}{config.server_time_endpoint}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            response.raise_for_status()
            payload = await response.json()
            server_time = payload.get("serverTime") or payload.get("server_time") or payload.get("time")
            if server_time is None:
                LOGGER.warning("Server time response missing time field: %s", payload)
                return None
            server_time_int = int(server_time)
            if server_time_int <= 0:
                LOGGER.warning("Server time response invalid: %s", server_time)
                return None
            return server_time_int
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.error("Failed to fetch server time: %s", exc)
        return None


def sign_request(config: Config, timestamp_ms: int, method: str, path: str, body: str = "") -> str:
    message = f"{timestamp_ms}{method.upper()}{path}{body}".encode("utf-8")
    secret = config.api_secret.encode("utf-8")
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return signature


async def signed_get(
    session: aiohttp.ClientSession,
    config: Config,
    rate_limiter: RateLimiter,
    time_sync: TimeSynchronizer,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    query = ""
    if params:
        filtered = {key: value for key, value in params.items() if value is not None}
        query = "&".join(
            f"{key}={quote(str(value), safe='')}" for key, value in sorted(filtered.items())
        )
    url = f"{config.rest_url}{path}"
    if query:
        url = f"{url}?{query}"
    for attempt in range(config.rest_retry_attempts + 1):
        await rate_limiter.acquire()
        timestamp_ms = time_sync.now_ms()
        signature = sign_request(config, timestamp_ms, "GET", path, query)
        headers = {
            "API-KEY": config.api_key,
            "API-TIMESTAMP": str(timestamp_ms),
            "API-SIGNATURE": signature,
        }
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 429:
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message="Rate limited",
                    )
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as exc:
            if attempt == config.rest_retry_attempts:
                LOGGER.error("GET %s failed after %s attempts: %s", url, attempt + 1, exc)
                raise
            delay = backoff_delay(
                config.rest_retry_base_delay, attempt, config.rest_max_backoff
            )
            LOGGER.warning(
                "GET %s failed (status=%s). Retrying in %.2fs", url, exc.status, delay
            )
            await asyncio.sleep(delay)
        except Exception as exc:  # pylint: disable=broad-except
            if attempt == config.rest_retry_attempts:
                LOGGER.error("Unexpected error during GET %s: %s", url, exc, exc_info=True)
                raise
            delay = backoff_delay(
                config.rest_retry_base_delay, attempt, config.rest_max_backoff
            )
            LOGGER.warning("GET %s raised %s. Retrying in %.2fs", url, exc, delay, exc_info=True)
            await asyncio.sleep(delay)
    raise RuntimeError("signed_get exhausted retries without raising")


def backoff_delay(base: float, attempt: int, max_delay: float) -> float:
    jitter = random.uniform(0, base)
    exponential = (2 ** attempt) * base
    return min(exponential + jitter, max_delay)


async def fetch_historical_data(
    session: aiohttp.ClientSession,
    config: Config,
    rate_limiter: RateLimiter,
    time_sync: TimeSynchronizer,
    state: SessionState,
    writer: "JsonlWriter",
    validator: RecordValidator,
) -> None:
    LOGGER.info("Fetching historical data starting from %s", state.last_timestamp)
    params: Dict[str, Any] = {"symbol": config.symbol, "limit": config.rest_page_size}
    if state.last_timestamp is not None:
        params["from"] = state.last_timestamp
    while True:
        payload = await signed_get(
            session,
            config,
            rate_limiter,
            time_sync,
            config.rest_endpoint,
            params=params,
        )
        if not isinstance(payload, dict) or "data" not in payload:
            LOGGER.debug("Unexpected payload structure: %s", payload)
            records: Iterable[Dict[str, Any]]
            if isinstance(payload, list):
                records = payload
            else:
                break
        else:
            records = payload.get("data", [])
            if isinstance(records, dict):
                records = records.get("items", [])
            if isinstance(records, (str, bytes)):
                LOGGER.warning("Ignoring non-iterable historical payload: %s", records)
                records = []
        count = 0
        last_ts = None
        for record in records:
            try:
                validated = validator.validate(record)
            except ValueError as exc:
                LOGGER.warning("Skipping invalid historical record: %s", exc)
                continue
            try:
                await writer.write(validated)
            except OSError as exc:
                LOGGER.error("Failed to persist historical record: %s", exc)
                raise
            timestamp_value = float(validated[config.timestamp_field])
            last_ts = timestamp_value
            state.update(timestamp_value)
            count += 1
        LOGGER.info("Fetched %s historical records", count)
        if count < config.rest_page_size or not last_ts:
            break
        params["from"] = last_ts
        await asyncio.sleep(0)  # allow other tasks to run


class JsonlWriter:
    def __init__(self, path: Path, indent: Optional[int] = None, sort_keys: bool = True) -> None:
        self.path = path
        self.indent = indent
        self.sort_keys = sort_keys
        self._separators = (",", ": ") if indent else (",", ":")
        self._lock = asyncio.Lock()

    async def write(self, record: Dict[str, Any]) -> None:
        async with self._lock:
            line = json.dumps(
                record,
                ensure_ascii=False,
                separators=self._separators,
                sort_keys=self.sort_keys,
            )
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
                handle.flush()
                safe_fsync(handle.fileno())


async def websocket_consumer(
    config: Config,
    validator: RecordValidator,
    writer: JsonlWriter,
    state: SessionState,
    time_sync: TimeSynchronizer,
) -> None:
    retry = 0
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                timestamp_ms = time_sync.now_ms()
                signature = sign_request(config, timestamp_ms, "GET", config.websocket_sign_path)
                headers = {
                    "API-KEY": config.api_key,
                    "API-TIMESTAMP": str(timestamp_ms),
                    "API-SIGNATURE": signature,
                }
                async with session.ws_connect(
                    config.websocket_url,
                    headers=headers,
                    heartbeat=30,
                    receive_timeout=60,
                ) as ws:
                    payload = {
                        "type": "subscribe",
                        "channel": config.websocket_channel,
                        "symbol": config.symbol,
                    }
                    if state.last_timestamp is not None:
                        payload["from"] = state.last_timestamp
                    await ws.send_json(payload)
                    LOGGER.info("Subscribed to %s via WebSocket", config.websocket_channel)
                    retry = 0
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                            except json.JSONDecodeError as exc:
                                LOGGER.warning("Failed to decode WebSocket message: %s", exc)
                                continue
                            record = data.get("data") if isinstance(data, dict) else data
                            if isinstance(record, list):
                                for item in record:
                                    await process_record(item, validator, writer, state, config)
                            elif isinstance(record, dict):
                                await process_record(record, validator, writer, state, config)
                            else:
                                LOGGER.debug("Ignoring message: %s", data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            raise msg.data
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                            LOGGER.warning("WebSocket closed, reconnecting")
                            break
        except asyncio.CancelledError:
            LOGGER.info("WebSocket consumer cancelled")
            raise
        except Exception as exc:  # pylint: disable=broad-except
            if isinstance(exc, OSError):
                LOGGER.error("Unrecoverable I/O error: %s", exc)
                raise
            retry += 1
            if retry > config.ws_max_retries and config.ws_max_retries >= 0:
                LOGGER.error("Exceeded maximum WebSocket retries: %s", exc)
                await asyncio.sleep(5)
                retry = 0
            delay = backoff_delay(config.ws_reconnect_base, retry, config.ws_max_backoff)
            LOGGER.warning("WebSocket error (%s). Reconnecting in %.2fs", exc, delay)
            await asyncio.sleep(delay)


async def process_record(
    record: Dict[str, Any],
    validator: RecordValidator,
    writer: JsonlWriter,
    state: SessionState,
    config: Config,
) -> None:
    try:
        validated = validator.validate(record)
    except ValueError as exc:
        LOGGER.warning("Skipping invalid realtime record: %s", exc)
        return
    try:
        await writer.write(validated)
    except OSError as exc:
        LOGGER.error("Failed to persist realtime record: %s", exc)
        raise
    timestamp_value = float(validated[config.timestamp_field])
    state.update(timestamp_value)


async def run() -> None:
    config = Config()
    rate_limiter = RateLimiter(config.rate_limit, config.rate_period)
    time_sync = TimeSynchronizer()
    state = SessionState(config.state_path, config.output_path, config.timestamp_field)
    validator = RecordValidator(config, initial_timestamp=state.last_timestamp)
    writer = JsonlWriter(config.output_path, indent=config.json_indent)

    stop_event = asyncio.Event()

    def shutdown_handler(*_: Any) -> None:
        LOGGER.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: shutdown_handler())

    async with aiohttp.ClientSession() as session:
        server_time = await fetch_server_time(session, config, rate_limiter)
        if server_time is not None:
            time_sync.set_offset(server_time)
        await fetch_historical_data(session, config, rate_limiter, time_sync, state, writer, validator)

    consumer_task = asyncio.create_task(
        websocket_consumer(config, validator, writer, state, time_sync)
    )

    await stop_event.wait()
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    LOGGER.info("Recorder stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user")
    except ConfigurationError as exc:
        LOGGER.error("Configuration error: %s", exc)
        sys.exit(1)
