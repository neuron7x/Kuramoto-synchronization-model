# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime Link Activator.

This module maps thermodynamic bond abstractions to concrete
communication protocols. The implementation focuses on deterministic
behaviour so unit tests and production telemetry remain predictable.

It follows a three-tier fallback hierarchy for each bond type and keeps
track of activation history for observability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProtocolType(Enum):
    """Supported communication protocols."""

    RDMA = "rdma"
    CRDT = "crdt"
    GRPC = "grpc"
    SHARED_MEMORY = "shared_memory"
    GOSSIP = "gossip"
    LOCAL_QUEUE = "local_queue"
    LOCAL_LEDGER = "local_ledger"


@dataclass(slots=True)
class ActivationResult:
    """Result of a protocol activation attempt."""

    success: bool
    protocol_used: Optional[ProtocolType]
    cost: float
    latency_estimate_us: float
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LinkActivator:
    """Activate protocols according to bond semantics."""

    PROTOCOL_COSTS: Dict[ProtocolType, float] = {
        ProtocolType.RDMA: 1e-4,
        ProtocolType.SHARED_MEMORY: 2e-4,
        ProtocolType.CRDT: 5e-4,
        ProtocolType.GRPC: 1e-3,
        ProtocolType.GOSSIP: 5e-3,
        ProtocolType.LOCAL_QUEUE: 1e-2,
        ProtocolType.LOCAL_LEDGER: 1e-2,
    }

    LATENCY_ESTIMATES_US: Dict[ProtocolType, float] = {
        ProtocolType.RDMA: 2.0,
        ProtocolType.SHARED_MEMORY: 0.5,
        ProtocolType.CRDT: 100.0,
        ProtocolType.GRPC: 500.0,
        ProtocolType.GOSSIP: 1_000.0,
        ProtocolType.LOCAL_QUEUE: 50.0,
        ProtocolType.LOCAL_LEDGER: 50.0,
    }

    def __init__(self, *, enable_rdma: bool = True, enable_crdt: bool = True) -> None:
        self.enable_rdma = enable_rdma
        self.enable_crdt = enable_crdt
        self._activation_history: List[Dict[str, Any]] = []
        logger.debug("LinkActivator initialised with RDMA=%s, CRDT=%s", enable_rdma, enable_crdt)

    # Public API ---------------------------------------------------------
    def apply(
        self,
        bond_type: str,
        src: str,
        dst: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ActivationResult:
        """Activate an appropriate protocol for a bond.

        Parameters
        ----------
        bond_type:
            One of ``metallic``, ``ionic``, ``covalent``, ``hydrogen`` or ``vdw``.
        src, dst:
            Logical endpoints being connected.
        metadata:
            Optional diagnostic metadata that will be included in the activation
            history for observability.
        """

        handler_map = {
            "metallic": self._activate_metallic,
            "ionic": self._activate_ionic,
            "covalent": self._activate_covalent,
            "hydrogen": self._activate_hydrogen,
            "vdw": self._activate_vdw,
        }

        handler = handler_map.get(bond_type)
        if handler is None:
            logger.error("Unknown bond type requested: %s", bond_type)
            result = ActivationResult(
                success=False,
                protocol_used=None,
                cost=1.0,
                latency_estimate_us=float("inf"),
                error=f"unknown bond type: {bond_type}",
            )
            self._record_history(bond_type, src, dst, result, metadata)
            return result

        try:
            result = handler(src, dst)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Activation error for %s bond %s->%s", bond_type, src, dst)
            result = ActivationResult(
                success=False,
                protocol_used=None,
                cost=1.0,
                latency_estimate_us=float("inf"),
                error=str(exc),
            )

        self._record_history(bond_type, src, dst, result, metadata)
        return result

    def get_activation_history(self) -> List[Dict[str, Any]]:
        """Return all activation attempts ordered by time."""

        return list(self._activation_history)

    def get_total_cost(self) -> float:
        """Return the cumulative protocol cost."""

        return sum(entry["cost"] for entry in self._activation_history if entry["success"])

    # Internal helpers ---------------------------------------------------
    def _record_history(
        self,
        bond_type: str,
        src: str,
        dst: str,
        result: ActivationResult,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        record = {
            "bond_type": bond_type,
            "src": src,
            "dst": dst,
            "success": result.success,
            "protocol": result.protocol_used.value if result.protocol_used else None,
            "cost": result.cost,
            "latency_estimate_us": result.latency_estimate_us,
            "error": result.error,
            "metadata": metadata or {},
        }
        self._activation_history.append(record)

    # Activation pipelines -----------------------------------------------
    def _activate_metallic(self, src: str, dst: str) -> ActivationResult:
        if self.enable_crdt:
            return self._crdt_consensus(src, dst)
        try:
            return self._gossip(src, dst)
        except Exception:  # pragma: no cover - fallback should never raise
            return self._local_ledger(src, dst)

    def _activate_ionic(self, src: str, dst: str) -> ActivationResult:
        if self.enable_rdma:
            return self._rdma_channel(src, dst)
        try:
            return self._grpc_stream(src, dst)
        except Exception:  # pragma: no cover
            return self._local_queue(src, dst)

    def _activate_covalent(self, src: str, dst: str) -> ActivationResult:
        try:
            return self._shared_memory(src, dst)
        except Exception:  # pragma: no cover
            return self._local_queue(src, dst)

    def _activate_hydrogen(self, src: str, dst: str) -> ActivationResult:
        try:
            return self._grpc_stream(src, dst, ttl_seconds=300)
        except Exception:  # pragma: no cover
            return self._local_queue(src, dst)

    def _activate_vdw(self, src: str, dst: str) -> ActivationResult:
        try:
            return self._gossip(src, dst, priority="low")
        except Exception:  # pragma: no cover
            return self._local_queue(src, dst)

    # Concrete protocol implementations ---------------------------------
    def _rdma_channel(self, src: str, dst: str) -> ActivationResult:
        metadata = {"adapter": "mlx5_0", "queue_pair": f"{src}:{dst}"}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.RDMA,
            cost=self.PROTOCOL_COSTS[ProtocolType.RDMA],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.RDMA],
            metadata=metadata,
        )

    def _crdt_consensus(self, src: str, dst: str) -> ActivationResult:
        metadata = {"doc": f"crdt::{src}::{dst}", "peers": [src, dst]}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.CRDT,
            cost=self.PROTOCOL_COSTS[ProtocolType.CRDT],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.CRDT],
            metadata=metadata,
        )

    def _grpc_stream(
        self, src: str, dst: str, ttl_seconds: Optional[int] = None
    ) -> ActivationResult:
        metadata = {"stream_id": f"{src}-{dst}", "ttl_seconds": ttl_seconds}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.GRPC,
            cost=self.PROTOCOL_COSTS[ProtocolType.GRPC],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.GRPC],
            metadata=metadata,
        )

    def _shared_memory(self, src: str, dst: str) -> ActivationResult:
        metadata = {"segment": f"/geosync/{src}-{dst}", "bytes": 4096}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.SHARED_MEMORY,
            cost=self.PROTOCOL_COSTS[ProtocolType.SHARED_MEMORY],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.SHARED_MEMORY],
            metadata=metadata,
        )

    def _gossip(self, src: str, dst: str, *, priority: str = "normal") -> ActivationResult:
        metadata = {"channel": f"gossip::{src}->{dst}", "priority": priority}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.GOSSIP,
            cost=self.PROTOCOL_COSTS[ProtocolType.GOSSIP],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.GOSSIP],
            metadata=metadata,
        )

    def _local_queue(self, src: str, dst: str) -> ActivationResult:
        metadata = {"queue": f"local::{src}->{dst}", "maxsize": 1024}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.LOCAL_QUEUE,
            cost=self.PROTOCOL_COSTS[ProtocolType.LOCAL_QUEUE],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.LOCAL_QUEUE],
            metadata=metadata,
        )

    def _local_ledger(self, src: str, dst: str) -> ActivationResult:
        metadata = {"path": f"/var/lib/geosync/{src}_{dst}.db"}
        return ActivationResult(
            success=True,
            protocol_used=ProtocolType.LOCAL_LEDGER,
            cost=self.PROTOCOL_COSTS[ProtocolType.LOCAL_LEDGER],
            latency_estimate_us=self.LATENCY_ESTIMATES_US[ProtocolType.LOCAL_LEDGER],
            metadata=metadata,
        )


__all__ = ["LinkActivator", "ProtocolType", "ActivationResult"]
