# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""P&L attribution by regime and decision type.

Proves value in money: how much did each regime/decision contribute
to total P&L? What was the cost of OBSERVE (missed opportunities)
vs the savings from ABORT (avoided losses)?

This is the module that turns physics into capital.
Without it, CoherenceBridge is a research tool.
With it, it's an auditable alpha source.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass


@dataclass(slots=True)
class RegimeStats:
    """P&L statistics for one regime."""

    count: int = 0
    total_pnl: float = 0.0
    sum_sq_pnl: float = 0.0
    max_gain: float = 0.0
    max_loss: float = 0.0
    total_size: float = 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.count if self.count > 0 else 0.0

    @property
    def pnl_std(self) -> float:
        if self.count < 2:
            return 0.0
        var = self.sum_sq_pnl / self.count - self.avg_pnl**2
        return math.sqrt(max(0.0, var))

    @property
    def sharpe(self) -> float:
        """Annualized Sharpe (assuming ~252 trading days, 1 signal/day)."""
        if self.pnl_std < 1e-12:
            return 0.0
        return self.avg_pnl / self.pnl_std * math.sqrt(252)

    @property
    def avg_size(self) -> float:
        return self.total_size / self.count if self.count > 0 else 0.0


@dataclass(frozen=True, slots=True)
class AttributionReport:
    """Complete P&L attribution snapshot."""

    by_regime: dict[str, RegimeStats]
    by_decision: dict[str, RegimeStats]
    total_pnl: float
    total_trades: int
    total_observes: int
    total_aborts: int
    observe_missed_pnl: float  # what we would have earned/lost if we traded
    abort_avoided_pnl: float  # what we would have lost if we traded
    protection_value: float  # abort_avoided_pnl (positive = saved money)


class PnLAttributor:
    """Tracks P&L attribution per regime and decision type.

    Usage:
        attributor = PnLAttributor()

        # After each tick:
        attributor.record(
            regime="METASTABLE",
            decision="TRADE",
            pnl=0.003,
            size=0.8,
            hypothetical_pnl=0.003,  # what full size would have earned
        )

        # After OBSERVE decision:
        attributor.record(
            regime="CRITICAL",
            decision="OBSERVE",
            pnl=0.0,  # didn't trade
            size=0.0,
            hypothetical_pnl=-0.05,  # what we would have lost
        )

        report = attributor.report()
    """

    def __init__(self) -> None:
        self._by_regime: dict[str, RegimeStats] = defaultdict(RegimeStats)
        self._by_decision: dict[str, RegimeStats] = defaultdict(RegimeStats)
        self._observe_missed: float = 0.0
        self._abort_avoided: float = 0.0
        self._total_trades: int = 0
        self._total_observes: int = 0
        self._total_aborts: int = 0

    def record(
        self,
        *,
        regime: str,
        decision: str,
        pnl: float,
        size: float,
        hypothetical_pnl: float = 0.0,
    ) -> None:
        """Record one decision outcome.

        Parameters
        ----------
        regime
            Market regime at time of decision.
        decision
            "TRADE", "OBSERVE", "ABORT", or "DISSOCIATED".
        pnl
            Actual realized P&L (0 if didn't trade).
        size
            Actual position size used.
        hypothetical_pnl
            What P&L would have been at full size. Used to compute
            protection value of OBSERVE/ABORT.
        """
        pnl = pnl if math.isfinite(pnl) else 0.0
        hypo = hypothetical_pnl if math.isfinite(hypothetical_pnl) else 0.0

        # Update regime stats
        rs = self._by_regime[regime]
        rs.count += 1
        rs.total_pnl += pnl
        rs.sum_sq_pnl += pnl**2
        rs.max_gain = max(rs.max_gain, pnl)
        rs.max_loss = min(rs.max_loss, pnl)
        rs.total_size += size

        # Update decision stats
        ds = self._by_decision[decision]
        ds.count += 1
        ds.total_pnl += pnl
        ds.sum_sq_pnl += pnl**2
        ds.max_gain = max(ds.max_gain, pnl)
        ds.max_loss = min(ds.max_loss, pnl)
        ds.total_size += size

        # Track missed/avoided
        if decision == "TRADE":
            self._total_trades += 1
        elif decision == "OBSERVE":
            self._total_observes += 1
            self._observe_missed += hypo
        elif decision in ("ABORT", "DISSOCIATED"):
            self._total_aborts += 1
            if hypo < 0:
                self._abort_avoided += abs(hypo)

    def report(self) -> AttributionReport:
        """Generate attribution report."""
        total_pnl = sum(rs.total_pnl for rs in self._by_regime.values())
        return AttributionReport(
            by_regime=dict(self._by_regime),
            by_decision=dict(self._by_decision),
            total_pnl=round(total_pnl, 6),
            total_trades=self._total_trades,
            total_observes=self._total_observes,
            total_aborts=self._total_aborts,
            observe_missed_pnl=round(self._observe_missed, 6),
            abort_avoided_pnl=round(self._abort_avoided, 6),
            protection_value=round(self._abort_avoided, 6),
        )

    def summary_dict(self) -> dict[str, object]:
        """Flat dict for QuestDB / Grafana / RF features."""
        r = self.report()
        result: dict[str, object] = {
            "total_pnl": r.total_pnl,
            "total_trades": r.total_trades,
            "total_observes": r.total_observes,
            "total_aborts": r.total_aborts,
            "protection_value": r.protection_value,
            "observe_missed_pnl": r.observe_missed_pnl,
        }
        for regime, stats in r.by_regime.items():
            result[f"pnl_{regime.lower()}"] = round(stats.total_pnl, 6)
            result[f"sharpe_{regime.lower()}"] = round(stats.sharpe, 4)
            result[f"count_{regime.lower()}"] = stats.count
        return result
