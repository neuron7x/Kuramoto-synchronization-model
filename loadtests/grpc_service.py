"""gRPC facade exercising execution-layer code paths for load testing."""

from __future__ import annotations

import threading
from concurrent import futures
from typing import Iterable

import grpc

from loadtests.proto import trading_pb2, trading_pb2_grpc
from loadtests.scenario import MarketScenario


class LoadTestTradingService(trading_pb2_grpc.TradingServiceServicer):
    """Deterministic trading service enforcing VaR-driven position limits."""

    def __init__(self, scenario: MarketScenario) -> None:
        self._scenario = scenario
        self._positions: dict[str, float] = {scenario.symbol: 0.0}
        self._order_state: dict[str, float] = {}
        self._lock = threading.Lock()
        self._order_sequence = 1
        self._median_price = scenario.median_price

    def PlaceOrder(
        self, request: trading_pb2.Order, context: grpc.ServicerContext
    ) -> trading_pb2.OrderResponse:
        price = request.price or self._median_price
        side = request.side.lower() or "buy"
        direction = 1.0 if side == "buy" else -1.0
        quantity = max(float(request.quantity), 0.0)
        symbol = request.symbol or self._scenario.symbol

        with self._lock:
            current_position = self._positions.get(symbol, 0.0)
            target_position = current_position + direction * quantity
            target_notional = abs(target_position * price)
            max_units = self._scenario.max_position_notional / max(price, 1e-6)
            if target_notional > self._scenario.max_position_notional:
                # Clamp to the VaR-derived exposure cap.
                capped_position = max(-max_units, min(max_units, target_position))
            else:
                capped_position = target_position
            executed_qty = capped_position - current_position
            self._positions[symbol] = capped_position
            order_id = f"lt-{self._order_sequence:08d}"
            self._order_state[order_id] = executed_qty
            self._order_sequence += 1

        return trading_pb2.OrderResponse(
            order_id=order_id,
            status="FILLED",
            filled_quantity=abs(executed_qty),
            average_price=price,
        )

    def CancelOrder(
        self, request: trading_pb2.OrderID, context: grpc.ServicerContext
    ) -> trading_pb2.CancelResponse:
        with self._lock:
            existed = self._order_state.pop(request.order_id, None)
            if existed is not None:
                symbol = self._scenario.symbol
                self._positions[symbol] -= existed
            return trading_pb2.CancelResponse(success=existed is not None)

    def GetPositions(
        self, request: trading_pb2.Empty, context: grpc.ServicerContext
    ) -> trading_pb2.PositionList:
        with self._lock:
            positions = []
            for symbol, qty in self._positions.items():
                notional = abs(qty * self._median_price)
                positions.append(
                    trading_pb2.Position(
                        symbol=symbol,
                        quantity=qty,
                        notional=notional,
                        var95=self._scenario.var_95,
                    )
                )
        return trading_pb2.PositionList(positions=positions)

    def StreamTickers(
        self, request: trading_pb2.SymbolList, context: grpc.ServicerContext
    ) -> Iterable[trading_pb2.Ticker]:
        requested = set(request.symbols) if request.symbols else {self._scenario.symbol}
        for symbol, price, volume, timestamp in self._scenario.ticker_series():
            if symbol not in requested:
                continue
            yield trading_pb2.Ticker(
                symbol=symbol,
                price=price,
                volume=volume,
                timestamp=int(timestamp.timestamp()),
            )


def serve(address: str, scenario: MarketScenario) -> grpc.Server:
    """Start the load-test trading service and return the running server."""

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    trading_pb2_grpc.add_TradingServiceServicer_to_server(
        LoadTestTradingService(scenario), server
    )
    server.add_insecure_port(address)
    server.start()
    return server


__all__ = ["LoadTestTradingService", "serve"]
