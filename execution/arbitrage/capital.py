# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capital movement orchestration ensuring atomic settlement."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Mapping, Protocol, runtime_checkable

from .models import CapitalTransferPlan, TransferResult

_LOGGER = logging.getLogger(__name__)


class CapitalMovementError(RuntimeError):
    """Raised when capital cannot be atomically moved across venues."""


@runtime_checkable
class SettlementGateway(Protocol):
    """Abstraction representing a custodian or prime broker API."""

    async def reserve(
        self,
        exchange_id: str,
        asset: str,
        amount: Decimal,
        transfer_id: str,
    ) -> str:
        """Lock funds and return a reservation token."""

    async def commit(self, reservation_token: str) -> None:
        """Finalize a previously reserved transfer."""

    async def release(self, reservation_token: str) -> None:
        """Release a reservation when the transfer is aborted."""


@dataclass(slots=True)
class CapitalTransferLeg:
    exchange_id: str
    asset: str
    amount: Decimal
    reservation_token: str


class AtomicCapitalMover:
    """Coordinates multi-venue transfers with two-phase commit semantics."""

    def __init__(
        self,
        gateways: Mapping[str, SettlementGateway],
        *,
        timeout: float = 5.0,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._gateways: Dict[str, SettlementGateway] = dict(gateways)
        self._timeout = timeout
        self._lock = asyncio.Lock()

    async def execute(self, plan: CapitalTransferPlan) -> TransferResult:
        if not plan.legs:
            raise ValueError("transfer plan must include at least one leg")
        async with self._lock:
            legs: list[CapitalTransferLeg] = []
            committed_count = 0
            try:
                for (exchange_id, asset), amount in plan.legs.items():
                    gateway = self._gateways.get(exchange_id)
                    if gateway is None:
                        raise CapitalMovementError(
                            f"No settlement gateway configured for {exchange_id}"
                        )
                    if amount == Decimal("0"):
                        continue
                    if amount < Decimal("0"):
                        raise CapitalMovementError("Transfer amounts must be non-negative per leg")
                    token = await asyncio.wait_for(
                        gateway.reserve(exchange_id, asset, amount, plan.transfer_id),
                        timeout=self._timeout,
                    )
                    legs.append(
                        CapitalTransferLeg(
                            exchange_id=exchange_id,
                            asset=asset,
                            amount=amount,
                            reservation_token=token,
                        )
                    )
                for leg in legs:
                    gateway = self._gateways[leg.exchange_id]
                    await asyncio.wait_for(
                        gateway.commit(leg.reservation_token), timeout=self._timeout
                    )
                    committed_count += 1
                return TransferResult(
                    transfer_id=plan.transfer_id,
                    committed=True,
                    committed_at=datetime.now(timezone.utc),
                    reason=None,
                    committed_legs=committed_count,
                    partial=False,
                )
            except Exception as exc:  # pragma: no cover - defensive branch
                # Roll back ONLY legs that were reserved but not yet committed —
                # `legs` is committed in order, so `legs[committed_count:]` are the
                # uncommitted reservations (including the one whose commit failed).
                # A committed leg must NEVER be `release`d: that would reverse a
                # settled transfer. If any leg already settled, this is a partial
                # (non-atomic) failure requiring reconciliation, not a clean no-op.
                await self._rollback(legs[committed_count:])
                if committed_count:
                    _LOGGER.error(
                        "Capital transfer PARTIALLY committed — reconciliation required",
                        extra={
                            "transfer_id": plan.transfer_id,
                            "committed_legs": committed_count,
                            "total_legs": len(legs),
                            "error": str(exc),
                        },
                    )
                return TransferResult(
                    transfer_id=plan.transfer_id,
                    committed=False,
                    committed_at=datetime.now(timezone.utc),
                    reason=str(exc),
                    committed_legs=committed_count,
                    partial=committed_count > 0,
                )

    async def _rollback(self, legs: list[CapitalTransferLeg]) -> None:
        for leg in reversed(legs):
            gateway = self._gateways.get(leg.exchange_id)
            if gateway is None:
                continue
            try:
                await asyncio.wait_for(
                    gateway.release(leg.reservation_token), timeout=self._timeout
                )
            except Exception as exc:  # pragma: no cover - best-effort rollback
                _LOGGER.warning(
                    "Failed to release capital reservation during rollback",
                    extra={
                        "exchange_id": leg.exchange_id,
                        "asset": leg.asset,
                        "transfer_id": leg.reservation_token,
                        "error": str(exc),
                    },
                )
