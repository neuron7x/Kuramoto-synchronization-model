# mypy: disable-error-code="attr-defined,operator,index,arg-type,call-overload,assignment"
"""gRPC server: start, health, stream, disconnect."""

from __future__ import annotations

from concurrent import futures
from unittest.mock import MagicMock

import grpc
import pytest

from coherence_bridge.generated import coherence_bridge_pb2 as pb
from coherence_bridge.generated import coherence_bridge_pb2_grpc as pb_grpc
from coherence_bridge.mock_engine import MockEngine
from coherence_bridge.server import CoherenceBridgeServicer


@pytest.fixture
def grpc_channel():
    """Start a test gRPC server and return a channel to it."""
    engine = MockEngine()
    writer = MagicMock()
    writer.write_signal = MagicMock()

    servicer = CoherenceBridgeServicer(engine, writer)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pb_grpc.add_CoherenceBridgeServicer_to_server(servicer, server)
    port = server.add_insecure_port("[::]:0")
    server.start()

    channel = grpc.insecure_channel(f"localhost:{port}")
    yield channel, writer

    channel.close()
    server.stop(grace=1)


def test_health(grpc_channel: tuple) -> None:
    channel, _ = grpc_channel
    stub = pb_grpc.CoherenceBridgeStub(channel)
    resp = stub.Health(pb.Empty())
    assert resp.healthy is True
    assert resp.uptime_s >= 0
    assert resp.signals_emitted == 0


def test_get_snapshot(grpc_channel: tuple) -> None:
    channel, _ = grpc_channel
    stub = pb_grpc.CoherenceBridgeStub(channel)
    sig = stub.GetSnapshot(pb.SnapshotRequest(instrument="EURUSD"))
    assert sig.instrument == "EURUSD"
    assert 0.0 <= sig.order_parameter_R <= 1.0
    assert sig.timestamp_ns > 0


def test_get_snapshot_not_found(grpc_channel: tuple) -> None:
    channel, _ = grpc_channel
    stub = pb_grpc.CoherenceBridgeStub(channel)
    with pytest.raises(grpc.RpcError) as exc_info:
        stub.GetSnapshot(pb.SnapshotRequest(instrument="NONEXISTENT"))
    assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND


def test_stream_signals(grpc_channel: tuple) -> None:
    channel, writer = grpc_channel
    stub = pb_grpc.CoherenceBridgeStub(channel)

    stream = stub.StreamSignals(
        pb.SignalRequest(instruments=["EURUSD"], min_interval_ms=100),
    )

    signals = []
    for sig in stream:
        signals.append(sig)
        if len(signals) >= 5:
            stream.cancel()
            break

    assert len(signals) >= 5
    for sig in signals:
        assert sig.instrument == "EURUSD"
        assert sig.timestamp_ns > 0

    # QuestDB writer should have been called (may lag by 1 due to timing)
    assert writer.write_signal.call_count >= 4


def test_multiple_instruments_stream(grpc_channel: tuple) -> None:
    channel, _ = grpc_channel
    stub = pb_grpc.CoherenceBridgeStub(channel)

    stream = stub.StreamSignals(
        pb.SignalRequest(instruments=["EURUSD", "GBPUSD"], min_interval_ms=100),
    )

    instruments_seen = set()
    count = 0
    for sig in stream:
        instruments_seen.add(sig.instrument)
        count += 1
        if count >= 10:
            stream.cancel()
            break

    assert "EURUSD" in instruments_seen
    assert "GBPUSD" in instruments_seen
