# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Locust scenarios exercising HTTP and gRPC facades under sustained load."""

from __future__ import annotations

import os
import time
from pathlib import Path

import grpc
from locust import HttpUser, User, between, events, task

from loadtests.proto import trading_pb2, trading_pb2_grpc
from loadtests.scenario import MarketScenario
from loadtests.security import mint_loadtest_token

RECORDING_PATH = Path(
    os.environ.get("LOADTEST_MARKET_RECORDING", "tests/fixtures/recordings/coinbase_btcusd.jsonl")
)
HTTP_SCENARIO_TEMPLATE = MarketScenario.from_recording(RECORDING_PATH)
GRPC_SCENARIO_TEMPLATE = MarketScenario.from_recording(RECORDING_PATH)
GRPC_TARGET = os.environ.get("LOADTEST_GRPC_ADDRESS", "127.0.0.1:50051")


class TradeApiUser(HttpUser):
    """Hammer the FastAPI prediction endpoints with realistic payloads."""

    wait_time = between(0.001, 0.01)

    def on_start(self) -> None:
        self._scenario = HTTP_SCENARIO_TEMPLATE.clone()
        token = mint_loadtest_token(subject=f"http-user-{id(self)}")
        self._headers = {"Authorization": f"Bearer {token}"}

    @task(3)
    def compute_features(self) -> None:
        payload = self._scenario.build_feature_payload(size=32)
        with self.client.post(
            "/api/v1/features",
            json=payload,
            headers=self._headers,
            name="POST /api/v1/features",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status {response.status_code}")
                return
            try:
                body = response.json()
            except ValueError as exc:
                response.failure(f"Invalid JSON payload: {exc}")
                return
            returned = int(body.get("pagination", {}).get("returned", 0))
            if returned <= 0:
                response.failure("Feature endpoint returned no snapshots")
                return
            response.success()

    @task(2)
    def generate_prediction(self) -> None:
        base_payload = self._scenario.build_feature_payload(size=32)
        payload = dict(base_payload)
        payload["horizon_seconds"] = 300
        with self.client.post(
            "/api/v1/predictions",
            json=payload,
            headers=self._headers,
            name="POST /api/v1/predictions",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Unexpected status {response.status_code}")
                return
            try:
                body = response.json()
            except ValueError as exc:
                response.failure(f"Invalid JSON payload: {exc}")
                return
            if body.get("signal") is None:
                response.failure("Prediction response missing signal")
                return
            response.success()

    @task(1)
    def read_health(self) -> None:
        self.client.get("/health", name="GET /health")


class GrpcClient:
    """Minimal gRPC client instrumented for Locust metrics."""

    def __init__(self, target: str) -> None:
        self._target = target
        self._channel = grpc.insecure_channel(target)
        self._stub = trading_pb2_grpc.TradingServiceStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    def place_order(
        self, order: trading_pb2.Order, *, scenario: MarketScenario
    ) -> trading_pb2.OrderResponse:
        name = "TradingService.PlaceOrder"
        start = time.perf_counter()
        try:
            response = self._stub.PlaceOrder(order, timeout=0.5)
            notional = response.filled_quantity * max(order.price, 1e-6)
            if notional > scenario.max_position_notional * 1.01:
                raise ValueError(
                    f"VaR breach detected: {notional:.4f} > {scenario.max_position_notional:.4f}"
                )
        except Exception as exc:
            duration = (time.perf_counter() - start) * 1000
            events.request_failure.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=0,
                exception=exc,
            )
            raise
        else:
            duration = (time.perf_counter() - start) * 1000
            events.request_success.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=response.ByteSize(),
            )
            return response

    def get_positions(self, scenario: MarketScenario) -> trading_pb2.PositionList:
        name = "TradingService.GetPositions"
        start = time.perf_counter()
        try:
            response = self._stub.GetPositions(trading_pb2.Empty(), timeout=0.5)
            for position in response.positions:
                if abs(position.var95 - scenario.var_95) > 1e-6:
                    raise ValueError("Scenario VaR mismatch in position response")
        except Exception as exc:
            duration = (time.perf_counter() - start) * 1000
            events.request_failure.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=0,
                exception=exc,
            )
            raise
        else:
            duration = (time.perf_counter() - start) * 1000
            events.request_success.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=response.ByteSize(),
            )
            return response

    def stream_tickers(self, scenario: MarketScenario, limit: int = 5) -> None:
        name = "TradingService.StreamTickers"
        start = time.perf_counter()
        stream = None
        try:
            stream = self._stub.StreamTickers(
                trading_pb2.SymbolList(symbols=[scenario.symbol]), timeout=1.0
            )
            count = 0
            for ticker in stream:
                if ticker.symbol != scenario.symbol:
                    raise ValueError("Ticker stream returned unexpected symbol")
                count += 1
                if count >= limit:
                    break
        except Exception as exc:
            duration = (time.perf_counter() - start) * 1000
            events.request_failure.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=0,
                exception=exc,
            )
            raise
        else:
            duration = (time.perf_counter() - start) * 1000
            events.request_success.fire(
                request_type="gRPC",
                name=name,
                response_time=duration,
                response_length=count,
            )
        finally:
            if stream is not None:
                stream.cancel()


class ExecutionGrpcUser(User):
    """Drive the execution-layer gRPC service with VaR-aware orders."""

    wait_time = between(0.001, 0.005)

    def on_start(self) -> None:
        self._scenario = GRPC_SCENARIO_TEMPLATE.clone()
        self.client = GrpcClient(GRPC_TARGET)

    def on_stop(self) -> None:
        self.client.close()

    @task(3)
    def place_orders(self) -> None:
        candidate = self._scenario.sample_order()
        order = trading_pb2.Order(
            symbol=candidate.symbol,
            side=candidate.side,
            order_type=candidate.order_type,
            quantity=candidate.quantity,
            price=candidate.price,
        )
        self.client.place_order(order, scenario=self._scenario)

    @task(1)
    def positions(self) -> None:
        self.client.get_positions(self._scenario)

    @task(1)
    def tickers(self) -> None:
        self.client.stream_tickers(self._scenario, limit=5)


__all__ = ["TradeApiUser", "ExecutionGrpcUser"]
