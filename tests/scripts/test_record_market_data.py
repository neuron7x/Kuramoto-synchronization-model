import hashlib
import hmac
import json
import types
from pathlib import Path

import aiohttp
import pytest

from scripts import record_market_data as rmd


class DummyResponse:
    def __init__(self, status: int, payload, raise_error=None):
        self.status = status
        self._payload = payload
        self._raise_error = raise_error
        self.request_info = None
        self.history = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_error:
            raise self._raise_error


class DummySession:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def get(self, url, *, headers=None, timeout=None):
        try:
            response = next(self._responses)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise AssertionError("No more responses prepared") from exc
        response.request_info = types.SimpleNamespace(real_url=url, method="GET", headers=headers)
        response.history = tuple()
        self.calls.append({"url": url, "headers": headers})
        return response


class DummyWriter:
    def __init__(self):
        self.records = []

    async def write(self, record):
        self.records.append(record)


class FailingWriter:
    async def write(self, record):  # pragma: no cover - used for failure path
        raise OSError("disk full")


@pytest.fixture(autouse=True)
def disable_fsync(monkeypatch):
    monkeypatch.setattr(rmd, "safe_fsync", lambda fd: None)


def build_config(tmp_path: Path, **overrides):
    base = dict(
        api_key="key",
        api_secret="secret",
        output_path=tmp_path / "out.jsonl",
        state_path=tmp_path / "state.json",
        rest_url="https://example.com",
        rest_endpoint="/v1/data",
        websocket_url="wss://example.com/ws",
        websocket_channel="trades",
        symbol="BTC-USD",
        rate_limit=10,
        rate_period=1.0,
        rest_page_size=2,
        rest_retry_attempts=1,
        rest_retry_base_delay=0.01,
        rest_max_backoff=0.5,
        ws_max_retries=2,
        ws_reconnect_base=0.01,
        ws_max_backoff=0.5,
        schema_required_fields=("timestamp", "price", "volume"),
        timestamp_field="timestamp",
        price_field="price",
        volume_field="volume",
    )
    base.update(overrides)
    return rmd.Config(**base)


def test_config_requires_credentials(tmp_path):
    with pytest.raises(rmd.ConfigurationError):
        rmd.Config(
            api_key="",
            api_secret="",
            output_path=tmp_path / "out.jsonl",
            state_path=tmp_path / "state.json",
        )


def test_record_validator_normalizes_fields(tmp_path):
    config = build_config(tmp_path)
    validator = rmd.RecordValidator(config)
    record = {"timestamp": "1.5", "price": "10", "volume": "0.1", "side": "buy"}
    normalized = validator.validate(record)
    assert normalized[config.timestamp_field] == pytest.approx(1.5)
    assert normalized[config.price_field] == pytest.approx(10.0)
    assert normalized[config.volume_field] == pytest.approx(0.1)
    assert validator.last_timestamp == pytest.approx(1.5)


def test_record_validator_rejects_regressions(tmp_path):
    config = build_config(tmp_path)
    validator = rmd.RecordValidator(config, initial_timestamp=5.0)
    with pytest.raises(ValueError):
        validator.validate({"timestamp": 4, "price": 1, "volume": 1})


def test_session_state_recovers_from_output(tmp_path):
    output_path = tmp_path / "data.jsonl"
    output_path.write_text('{"timestamp":1}\n{"timestamp":2}\n', encoding="utf-8")
    state_path = tmp_path / "state.json"
    state = rmd.SessionState(state_path, output_path, "timestamp")
    assert state.last_timestamp == pytest.approx(2.0)


def test_session_state_update_persists(tmp_path):
    output_path = tmp_path / "data.jsonl"
    state_path = tmp_path / "state.json"
    state = rmd.SessionState(state_path, output_path, "timestamp")
    state.update(123.456)
    saved = json.loads(state_path.read_text(encoding="utf-8"))
    assert saved["last_timestamp"] == pytest.approx(123.456)


@pytest.mark.asyncio
async def test_jsonl_writer_writes_single_line(tmp_path):
    writer = rmd.JsonlWriter(tmp_path / "out.jsonl", indent=2)
    await writer.write({"volume": 2, "timestamp": 1, "price": 3})
    contents = (tmp_path / "out.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1
    payload = json.loads(contents[0])
    assert payload == {"price": 3, "timestamp": 1, "volume": 2}


def test_backoff_delay_is_capped(monkeypatch):
    monkeypatch.setattr(rmd.random, "uniform", lambda _a, base: base)
    delay = rmd.backoff_delay(0.1, 5, 0.5)
    assert delay <= 0.5


@pytest.mark.asyncio
async def test_signed_get_retries_on_429(tmp_path, monkeypatch):
    config = build_config(tmp_path, rest_retry_attempts=2)
    rate_limiter = rmd.RateLimiter(100, 60)
    time_sync = rmd.TimeSynchronizer()

    responses = [
        DummyResponse(429, {"error": "rate"}),
        DummyResponse(200, {"ok": True}),
    ]
    session = DummySession(responses)

    async def fast_sleep(_):
        return None

    monkeypatch.setattr(rmd.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(rmd.random, "uniform", lambda _a, _b: 0)

    result = await rmd.signed_get(session, config, rate_limiter, time_sync, "/endpoint", {"a": 1})
    assert result == {"ok": True}
    assert session.calls[0]["url"].endswith("?a=1")
    assert session.calls[1]["url"].endswith("?a=1")


@pytest.mark.asyncio
async def test_signed_get_raises_after_retries(tmp_path, monkeypatch):
    request_info = types.SimpleNamespace(real_url="https://example.com/endpoint")

    def make_error():
        return aiohttp.ClientResponseError(request_info, (), status=500, message="boom")

    responses = [
        DummyResponse(500, {"error": 1}, raise_error=make_error()),
        DummyResponse(500, {"error": 2}, raise_error=make_error()),
    ]
    session = DummySession(responses)
    config = build_config(tmp_path, rest_retry_attempts=1)
    rate_limiter = rmd.RateLimiter(100, 60)
    time_sync = rmd.TimeSynchronizer()

    async def fast_sleep(_):
        return None

    monkeypatch.setattr(rmd.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(rmd.random, "uniform", lambda _a, _b: 0)

    with pytest.raises(aiohttp.ClientResponseError):
        await rmd.signed_get(session, config, rate_limiter, time_sync, "/endpoint")


@pytest.mark.asyncio
async def test_fetch_historical_data_filters_invalid(tmp_path, monkeypatch):
    config = build_config(tmp_path, rest_page_size=3)
    state = rmd.SessionState(config.state_path, config.output_path, config.timestamp_field)
    validator = rmd.RecordValidator(config)
    writer = DummyWriter()
    rate_limiter = rmd.RateLimiter(100, 60)
    time_sync = rmd.TimeSynchronizer()

    payloads = [
        {
            "data": [
                {"timestamp": 1, "price": "10", "volume": "0.2"},
                {"timestamp": "bad", "price": "10", "volume": "0.3"},
                {"timestamp": 2, "price": "11", "volume": "0.4"},
            ]
        },
        {"data": []},
    ]

    async def fake_signed_get(*_args, **_kwargs):
        return payloads.pop(0)

    monkeypatch.setattr(rmd, "signed_get", fake_signed_get)

    await rmd.fetch_historical_data(
        session=None,
        config=config,
        rate_limiter=rate_limiter,
        time_sync=time_sync,
        state=state,
        writer=writer,
        validator=validator,
    )

    assert [rec["timestamp"] for rec in writer.records] == [1.0, 2.0]
    assert state.last_timestamp == pytest.approx(2.0)
    assert validator.last_timestamp == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_process_record_updates_state(tmp_path):
    config = build_config(tmp_path)
    state = rmd.SessionState(config.state_path, config.output_path, config.timestamp_field)
    validator = rmd.RecordValidator(config)
    writer = DummyWriter()

    await rmd.process_record({"timestamp": 1, "price": 2, "volume": 3}, validator, writer, state, config)

    assert writer.records[0]["timestamp"] == pytest.approx(1.0)
    assert state.last_timestamp == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_process_record_propagates_persistence_errors(tmp_path):
    config = build_config(tmp_path)
    state = rmd.SessionState(config.state_path, config.output_path, config.timestamp_field)
    validator = rmd.RecordValidator(config)

    with pytest.raises(OSError):
        await rmd.process_record(
            {"timestamp": 1, "price": 2, "volume": 3},
            validator,
            FailingWriter(),
            state,
            config,
        )


@pytest.mark.asyncio
async def test_rate_limiter_waits_when_exhausted(monkeypatch):
    times = {"value": 0.0}

    def fake_monotonic():
        return times["value"]

    async def fake_sleep(duration):
        times["value"] += duration

    monkeypatch.setattr(rmd.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(rmd.asyncio, "sleep", fake_sleep)

    limiter = rmd.RateLimiter(1, 1.0)
    await limiter.acquire()
    await limiter.acquire()
    assert times["value"] >= 1.0


def test_sign_request_matches_expected(tmp_path):
    config = build_config(tmp_path, api_secret="secret")
    signature = rmd.sign_request(config, 1234567890, "GET", "/endpoint", "a=1")
    expected = hmac.new(
        b"secret",
        b"1234567890GET/endpointa=1",
        hashlib.sha256,
    ).hexdigest()
    assert signature == expected
