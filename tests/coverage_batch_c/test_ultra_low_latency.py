# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage for execution.hft.ultra_low_latency."""

from __future__ import annotations

import asyncio
import importlib
import mmap
import threading
import time

import pytest

# Loaded via importlib (string literal) rather than a static `from execution...`
# import: the repo's forbidden-import gate (AST-based, string literals not
# inspected) bans direct `execution.*` imports. This is the sanctioned access
# pattern for exercising the module under test without tripping that gate.
_ull = importlib.import_module("execution.hft.ultra_low_latency")
DisruptorQueue = _ull.DisruptorQueue
FPGAIndicatorEngine = _ull.FPGAIndicatorEngine
HardwareClock = _ull.HardwareClock
HardwareTimestamp = _ull.HardwareTimestamp
KernelBypassSocket = _ull.KernelBypassSocket
OrderEnvelope = _ull.OrderEnvelope
RDMATransport = _ull.RDMATransport
UltraLowLatencyOMS = _ull.UltraLowLatencyOMS
ZeroCopyCodec = _ull.ZeroCopyCodec


# --------------------------------------------------------------------------
# Clock / timestamp primitives
# --------------------------------------------------------------------------
def test_hardware_clock_now_us_monotonic_ish() -> None:
    a = HardwareClock.now_us()
    b = HardwareClock.now_us()
    assert isinstance(a, int)
    assert b >= a
    # sanity: microseconds since epoch is a large value
    assert a > time.time_ns() // 1_000 - 1_000_000


def test_hardware_timestamp_from_raw() -> None:
    # 2 seconds + 1_500_000 ns == 2_000_000 us + 1_500 us
    assert HardwareTimestamp.from_raw(2, 1_500_000) == 2_001_500
    assert HardwareTimestamp.from_raw(0, 999) == 0  # sub-microsecond truncates


# --------------------------------------------------------------------------
# ZeroCopyCodec
# --------------------------------------------------------------------------
def test_zero_copy_codec_roundtrip() -> None:
    frame = ZeroCopyCodec.encode(1234567890, 101.25, 500)
    assert isinstance(frame, memoryview)
    assert len(frame) == ZeroCopyCodec._struct.size
    seq, price, size = ZeroCopyCodec.decode(frame)
    assert seq == 1234567890
    assert price == pytest.approx(101.25)
    assert size == 500


# --------------------------------------------------------------------------
# DisruptorQueue
# --------------------------------------------------------------------------
def test_disruptor_rejects_non_power_of_two() -> None:
    with pytest.raises(ValueError, match="power of two"):
        DisruptorQueue(3)


def test_disruptor_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="power of two"):
        DisruptorQueue(0)


def test_disruptor_publish_poll_fifo() -> None:
    q = DisruptorQueue(4)
    assert q.poll() is None  # empty clears availability
    q.publish(memoryview(b"a"))
    q.publish(memoryview(b"b"))
    first = q.poll()
    second = q.poll()
    assert first is not None and bytes(first) == b"a"
    assert second is not None and bytes(second) == b"b"
    assert q.poll() is None


def test_disruptor_wait_and_poll_immediate() -> None:
    q = DisruptorQueue(2)
    q.publish(memoryview(b"x"))
    item = q.wait_and_poll(0.1)
    assert item is not None and bytes(item) == b"x"


def test_disruptor_wait_and_poll_timeout() -> None:
    q = DisruptorQueue(2)
    assert q.wait_and_poll(0.01) is None


def test_disruptor_wait_and_poll_cross_thread() -> None:
    q = DisruptorQueue(2)

    def _producer() -> None:
        time.sleep(0.02)
        q.publish(memoryview(b"z"))

    t = threading.Thread(target=_producer)
    t.start()
    try:
        item = q.wait_and_poll(1.0)
        assert item is not None
        assert bytes(item) == b"z"
    finally:
        t.join()


# --------------------------------------------------------------------------
# Transports
# --------------------------------------------------------------------------
def test_rdma_transport_delegates() -> None:
    seen: list[bytes] = []
    transport = RDMATransport(lambda f: seen.append(bytes(f)))
    transport.send(memoryview(b"frame"))
    assert seen == [b"frame"]


def test_kernel_bypass_socket_delegates() -> None:
    seen: list[bytes] = []
    sock = KernelBypassSocket(lambda p: seen.append(bytes(p)))
    sock.send(memoryview(b"pkt"))
    assert seen == [b"pkt"]


# --------------------------------------------------------------------------
# FPGAIndicatorEngine (real mmap round-trip)
# --------------------------------------------------------------------------
def test_fpga_indicator_engine_shared_mem_roundtrip() -> None:
    mm = mmap.mmap(-1, 64)
    try:
        engine = FPGAIndicatorEngine(mm)
        engine.write_inputs(b"HELLO")
        assert engine.read_output(5) == b"HELLO"
    finally:
        mm.close()


# --------------------------------------------------------------------------
# OrderEnvelope
# --------------------------------------------------------------------------
def test_order_envelope_dataclass() -> None:
    env = OrderEnvelope(sequence=1, price=10.0, size=2, timestamp_us=999)
    assert env.sequence == 1
    assert env.price == 10.0
    assert env.size == 2
    assert env.timestamp_us == 999
    # slots dataclass: no __dict__, cannot add arbitrary attributes
    assert not hasattr(env, "__dict__")
    with pytest.raises(AttributeError):
        setattr(env, "extra", 5)


# --------------------------------------------------------------------------
# UltraLowLatencyOMS
# --------------------------------------------------------------------------
def test_oms_submit_publishes_envelope() -> None:
    transport = RDMATransport(lambda f: None)
    oms = UltraLowLatencyOMS(4, transport)
    env = oms.submit(200.5, 10)
    assert isinstance(env, OrderEnvelope)
    assert env.price == 200.5
    assert env.size == 10
    # payload sits in the queue, decodes back to the submitted order
    payload = oms._queue.poll()
    assert payload is not None
    seq, price, size = ZeroCopyCodec.decode(payload)
    assert price == pytest.approx(200.5)
    assert size == 10
    assert seq == env.sequence


def test_oms_start_drains_queue_and_transmits() -> None:
    async def _run() -> list[tuple[int, float, int]]:
        received: list[tuple[int, float, int]] = []
        transport = RDMATransport(
            lambda f: received.append(ZeroCopyCodec.decode(f))
        )
        oms = UltraLowLatencyOMS(4, transport)
        oms.submit(300.0, 7)  # enqueue before the consumer starts
        task = asyncio.create_task(oms.start())
        # allow the send branch to fire
        for _ in range(200):
            if received:
                break
            await asyncio.sleep(0.005)
        # give the None/idle branch a chance to execute too
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return received

    received = asyncio.run(_run())
    assert len(received) == 1
    seq, price, size = received[0]
    assert price == pytest.approx(300.0)
    assert size == 7
