"""Ultra low latency order management primitives."""

from __future__ import annotations

import asyncio
import mmap
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


class HardwareClock:
    """Expose microsecond precision timestamps using ``time.time_ns``."""

    @staticmethod
    def now_us() -> int:
        return time.time_ns() // 1_000


class HardwareTimestamp:
    """Helper for hardware derived timestamp payloads."""

    @staticmethod
    def from_raw(seconds: int, nanoseconds: int) -> int:
        return seconds * 1_000_000 + nanoseconds // 1_000


class ZeroCopyCodec:
    """Serialize and deserialize orders without intermediate copies."""

    _struct = struct.Struct("!QdI")

    @classmethod
    def encode(cls, sequence: int, price: float, size: int) -> memoryview:
        buffer = bytearray(cls._struct.size)
        cls._struct.pack_into(buffer, 0, sequence, price, size)
        return memoryview(buffer)

    @classmethod
    def decode(cls, payload: memoryview) -> tuple[int, float, int]:
        return cls._struct.unpack_from(payload, 0)


class DisruptorQueue:
    """Single-producer single-consumer ring buffer inspired by LMAX."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0 or capacity & (capacity - 1) != 0:
            raise ValueError("capacity must be a power of two")
        self._capacity = capacity
        self._mask = capacity - 1
        self._entries = [None] * capacity
        self._write_sequence = 0
        self._read_sequence = 0
        self._available = threading.Event()

    def publish(self, item: memoryview) -> None:
        next_seq = self._write_sequence
        index = next_seq & self._mask
        self._entries[index] = item
        self._write_sequence = next_seq + 1
        self._available.set()

    def poll(self) -> Optional[memoryview]:
        if self._read_sequence >= self._write_sequence:
            self._available.clear()
            return None
        index = self._read_sequence & self._mask
        item = self._entries[index]
        self._entries[index] = None
        self._read_sequence += 1
        return item

    def wait_and_poll(self, timeout: float | None = None) -> Optional[memoryview]:
        item = self.poll()
        if item is not None:
            return item
        if not self._available.wait(timeout):
            return None
        return self.poll()


class RDMATransport:
    """Simplified RDMA abstraction for colocated exchange gateways."""

    def __init__(self, send_fn: Callable[[memoryview], None]) -> None:
        self._send = send_fn

    def send(self, frame: memoryview) -> None:
        self._send(frame)


class KernelBypassSocket:
    """Facade over a DPDK-backed TX queue."""

    def __init__(self, tx_fn: Callable[[memoryview], None]) -> None:
        self._tx_fn = tx_fn

    def send(self, payload: memoryview) -> None:
        self._tx_fn(payload)


class FPGAIndicatorEngine:
    """Delegate indicator computation to a hardware accelerator."""

    def __init__(self, shared_mem: mmap.mmap) -> None:
        self._shared_mem = shared_mem

    def write_inputs(self, data: bytes) -> None:
        self._shared_mem.seek(0)
        self._shared_mem.write(data)

    def read_output(self, size: int) -> bytes:
        self._shared_mem.seek(0)
        return self._shared_mem.read(size)


@dataclass(slots=True)
class OrderEnvelope:
    sequence: int
    price: float
    size: int
    timestamp_us: int


class UltraLowLatencyOMS:
    """High-frequency order management system skeleton."""

    def __init__(
        self, capacity: int, transmitter: RDMATransport | KernelBypassSocket
    ) -> None:
        self._queue = DisruptorQueue(capacity)
        self._transmitter = transmitter

    def submit(self, price: float, size: int) -> OrderEnvelope:
        sequence = HardwareClock.now_us()
        payload = ZeroCopyCodec.encode(sequence, price, size)
        envelope = OrderEnvelope(sequence, price, size, HardwareClock.now_us())
        self._queue.publish(payload)
        return envelope

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            payload = await loop.run_in_executor(None, self._queue.wait_and_poll, 0.001)
            if payload is None:
                await asyncio.sleep(0)
                continue
            self._transmitter.send(payload)


__all__ = [
    "DisruptorQueue",
    "FPGAIndicatorEngine",
    "HardwareClock",
    "HardwareTimestamp",
    "KernelBypassSocket",
    "OrderEnvelope",
    "RDMATransport",
    "UltraLowLatencyOMS",
    "ZeroCopyCodec",
]
