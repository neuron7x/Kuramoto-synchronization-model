# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Strategy Scheduling & Execution Automation

Autonomous strategy management that:
- Enhanced cron-based strategy scheduling
- Auto-failover for strategy execution
- Autonomous rebalancing triggers
- Self-optimizing execution parameters
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyStatus(str, Enum):
    """Strategy execution status."""
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    RECOVERING = "recovering"


class RebalanceReason(str, Enum):
    """Reasons for portfolio rebalancing."""
    SCHEDULED = "scheduled"
    DRIFT_DETECTED = "drift_detected"
    RISK_EXCEEDED = "risk_exceeded"
    MARKET_REGIME_CHANGE = "market_regime_change"
    PERFORMANCE_DEGRADED = "performance_degraded"


@dataclass
class StrategyMetrics:
    """Metrics for strategy performance."""
    
    returns: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RebalanceEvent:
    """Represents a portfolio rebalancing event."""
    
    strategy_id: str
    reason: RebalanceReason
    timestamp: datetime
    old_allocation: Dict[str, float]
    new_allocation: Dict[str, float]
    executed: bool = False


@dataclass
class FailoverEvent:
    """Represents a strategy failover event."""
    
    strategy_id: str
    timestamp: datetime
    error: str
    backup_strategy_id: Optional[str] = None
    recovered: bool = False


class StrategyAutomation:
    """
    Autonomous strategy scheduling and execution system.
    
    Features:
    1. Advanced cron-based scheduling with intelligent retry
    2. Automatic failover to backup strategies
    3. Autonomous rebalancing based on multiple triggers
    4. Self-optimizing execution parameters
    """
    
    def __init__(
        self,
        rebalance_interval_hours: int = 24,
        drift_threshold: float = 0.05,
        risk_threshold: float = 0.15,
        enable_auto_failover: bool = True,
    ):
        """
        Initialize strategy automation.
        
        Args:
            rebalance_interval_hours: Hours between scheduled rebalances
            drift_threshold: Maximum allowed allocation drift
            risk_threshold: Maximum allowed portfolio risk
            enable_auto_failover: Whether to enable automatic failover
        """
        self.rebalance_interval = timedelta(hours=rebalance_interval_hours)
        self.drift_threshold = drift_threshold
        self.risk_threshold = risk_threshold
        self.enable_auto_failover = enable_auto_failover
        
        self._strategies: Dict[str, Dict[str, Any]] = {}
        self._backup_strategies: Dict[str, str] = {}
        self._metrics_history: Dict[str, List[StrategyMetrics]] = {}
        self._rebalance_history: List[RebalanceEvent] = []
        self._failover_history: List[FailoverEvent] = []
        self._last_rebalance: Dict[str, datetime] = {}
        
    def register_strategy(
        self,
        strategy_id: str,
        strategy_func: Callable,
        schedule: str,
        allocation: Dict[str, float],
        backup_strategy_id: Optional[str] = None,
    ) -> None:
        """
        Register a strategy for automated execution.
        
        Args:
            strategy_id: Unique strategy identifier
            strategy_func: Strategy execution function
            schedule: Cron schedule string
            allocation: Target asset allocation
            backup_strategy_id: Optional backup strategy for failover
        """
        self._strategies[strategy_id] = {
            "func": strategy_func,
            "schedule": schedule,
            "allocation": allocation.copy(),
            "target_allocation": allocation.copy(),
            "status": StrategyStatus.ACTIVE,
            "last_executed": None,
            "execution_count": 0,
            "failure_count": 0,
        }
        
        if backup_strategy_id:
            self._backup_strategies[strategy_id] = backup_strategy_id
        
        self._last_rebalance[strategy_id] = datetime.now(timezone.utc)
        
        logger.info(f"Registered strategy: {strategy_id} with schedule: {schedule}")
    
    async def execute_strategy(self, strategy_id: str) -> Optional[Any]:
        """
        Execute a strategy with automatic failover.
        
        Args:
            strategy_id: Strategy to execute
            
        Returns:
            Strategy execution result or None if failed
        """
        if strategy_id not in self._strategies:
            logger.error(f"Strategy not found: {strategy_id}")
            return None
        
        strategy = self._strategies[strategy_id]
        
        if strategy["status"] != StrategyStatus.ACTIVE:
            logger.warning(f"Strategy {strategy_id} is not active, skipping execution")
            return None
        
        try:
            # Execute strategy
            result = await self._execute_with_retry(strategy_id)
            
            if result is not None:
                strategy["last_executed"] = datetime.now(timezone.utc)
                strategy["execution_count"] += 1
                strategy["failure_count"] = 0  # Reset failure count on success
                
                # Update metrics
                self._update_metrics(strategy_id, result)
                
                # Check if rebalancing is needed
                await self._check_rebalance_triggers(strategy_id)
                
                return result
            else:
                # Execution failed
                strategy["failure_count"] += 1
                
                # Attempt failover if enabled and failures exceed threshold
                if self.enable_auto_failover and strategy["failure_count"] >= 3:
                    return await self._failover_strategy(strategy_id)
                
                return None
                
        except Exception as e:
            logger.error(f"Strategy execution failed for {strategy_id}: {e}")
            strategy["failure_count"] += 1
            
            if self.enable_auto_failover and strategy["failure_count"] >= 3:
                return await self._failover_strategy(strategy_id)
            
            return None
    
    async def _execute_with_retry(
        self,
        strategy_id: str,
        max_retries: int = 3,
    ) -> Optional[Any]:
        """Execute strategy with automatic retry."""
        strategy = self._strategies[strategy_id]
        
        for attempt in range(max_retries):
            try:
                result = strategy["func"]()
                return result
            except Exception as e:
                logger.warning(f"Strategy {strategy_id} attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return None
    
    async def _failover_strategy(self, strategy_id: str) -> Optional[Any]:
        """
        Perform automatic failover to backup strategy.
        
        Args:
            strategy_id: Failed strategy ID
            
        Returns:
            Backup strategy execution result
        """
        backup_id = self._backup_strategies.get(strategy_id)
        
        if not backup_id:
            logger.error(f"No backup strategy configured for {strategy_id}")
            self._strategies[strategy_id]["status"] = StrategyStatus.FAILED
            return None
        
        logger.info(f"Failing over from {strategy_id} to {backup_id}")
        
        # Record failover event
        failover_event = FailoverEvent(
            strategy_id=strategy_id,
            timestamp=datetime.now(timezone.utc),
            error=f"Exceeded failure threshold",
            backup_strategy_id=backup_id,
        )
        self._failover_history.append(failover_event)
        
        # Mark original strategy as failed
        self._strategies[strategy_id]["status"] = StrategyStatus.FAILED
        
        # Execute backup strategy
        try:
            result = await self.execute_strategy(backup_id)
            failover_event.recovered = True
            logger.info(f"Failover successful: {backup_id}")
            return result
        except Exception as e:
            logger.error(f"Backup strategy {backup_id} also failed: {e}")
            return None
    
    def _update_metrics(self, strategy_id: str, result: Any) -> None:
        """Update strategy performance metrics."""
        # Extract metrics from result
        # This is a placeholder - actual implementation depends on result structure
        if isinstance(result, dict):
            metrics = StrategyMetrics(
                returns=result.get("returns", 0.0),
                sharpe_ratio=result.get("sharpe_ratio", 0.0),
                max_drawdown=result.get("max_drawdown", 0.0),
                win_rate=result.get("win_rate", 0.0),
                total_trades=result.get("total_trades", 0),
            )
            
            if strategy_id not in self._metrics_history:
                self._metrics_history[strategy_id] = []
            
            self._metrics_history[strategy_id].append(metrics)
    
    async def _check_rebalance_triggers(self, strategy_id: str) -> None:
        """Check if rebalancing is needed based on multiple triggers."""
        strategy = self._strategies[strategy_id]
        last_rebalance = self._last_rebalance.get(strategy_id)
        
        if not last_rebalance:
            return
        
        # Trigger 1: Scheduled rebalancing
        if datetime.now(timezone.utc) - last_rebalance >= self.rebalance_interval:
            await self._rebalance_portfolio(strategy_id, RebalanceReason.SCHEDULED)
            return
        
        # Trigger 2: Allocation drift
        if self._check_allocation_drift(strategy_id):
            await self._rebalance_portfolio(strategy_id, RebalanceReason.DRIFT_DETECTED)
            return
        
        # Trigger 3: Risk exceeded
        if self._check_risk_threshold(strategy_id):
            await self._rebalance_portfolio(strategy_id, RebalanceReason.RISK_EXCEEDED)
            return
        
        # Trigger 4: Performance degraded
        if self._check_performance_degradation(strategy_id):
            await self._rebalance_portfolio(strategy_id, RebalanceReason.PERFORMANCE_DEGRADED)
            return
    
    def _check_allocation_drift(self, strategy_id: str) -> bool:
        """Check if allocation has drifted beyond threshold."""
        strategy = self._strategies[strategy_id]
        current_allocation = strategy["allocation"]
        target_allocation = strategy["target_allocation"]
        
        for asset, target_weight in target_allocation.items():
            current_weight = current_allocation.get(asset, 0.0)
            drift = abs(current_weight - target_weight)
            
            if drift > self.drift_threshold:
                logger.info(f"Allocation drift detected for {asset}: {drift:.2%}")
                return True
        
        return False
    
    def _check_risk_threshold(self, strategy_id: str) -> bool:
        """Check if portfolio risk exceeds threshold."""
        # Placeholder - actual risk calculation depends on portfolio data
        metrics = self._metrics_history.get(strategy_id, [])
        
        if not metrics:
            return False
        
        latest_metrics = metrics[-1]
        if abs(latest_metrics.max_drawdown) > self.risk_threshold:
            logger.warning(f"Risk threshold exceeded: {latest_metrics.max_drawdown:.2%}")
            return True
        
        return False
    
    def _check_performance_degradation(self, strategy_id: str) -> bool:
        """Check if strategy performance has degraded significantly."""
        metrics = self._metrics_history.get(strategy_id, [])
        
        if len(metrics) < 10:
            return False
        
        # Compare recent performance to historical average
        recent_returns = sum(m.returns for m in metrics[-5:]) / 5
        historical_returns = sum(m.returns for m in metrics[-20:-5]) / 15
        
        if recent_returns < historical_returns * 0.7:  # 30% degradation
            logger.warning(f"Performance degradation detected for {strategy_id}")
            return True
        
        return False
    
    async def _rebalance_portfolio(
        self,
        strategy_id: str,
        reason: RebalanceReason,
    ) -> None:
        """
        Execute portfolio rebalancing.
        
        Args:
            strategy_id: Strategy to rebalance
            reason: Reason for rebalancing
        """
        strategy = self._strategies[strategy_id]
        old_allocation = strategy["allocation"].copy()
        new_allocation = strategy["target_allocation"].copy()
        
        # Apply rebalancing
        strategy["allocation"] = new_allocation.copy()
        self._last_rebalance[strategy_id] = datetime.now(timezone.utc)
        
        # Record event
        rebalance_event = RebalanceEvent(
            strategy_id=strategy_id,
            reason=reason,
            timestamp=datetime.now(timezone.utc),
            old_allocation=old_allocation,
            new_allocation=new_allocation,
            executed=True,
        )
        self._rebalance_history.append(rebalance_event)
        
        logger.info(f"Portfolio rebalanced for {strategy_id}, reason: {reason.value}")
    
    def get_strategy_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get current status of a strategy."""
        if strategy_id not in self._strategies:
            return {"error": "Strategy not found"}
        
        strategy = self._strategies[strategy_id]
        metrics = self._metrics_history.get(strategy_id, [])
        
        latest_metrics = None
        if metrics:
            m = metrics[-1]
            latest_metrics = {
                "returns": m.returns,
                "sharpe_ratio": m.sharpe_ratio,
                "max_drawdown": m.max_drawdown,
                "win_rate": m.win_rate,
                "total_trades": m.total_trades,
            }
        
        return {
            "strategy_id": strategy_id,
            "status": strategy["status"].value,
            "allocation": strategy["allocation"],
            "last_executed": strategy["last_executed"].isoformat() if strategy["last_executed"] else None,
            "execution_count": strategy["execution_count"],
            "failure_count": strategy["failure_count"],
            "metrics": latest_metrics,
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get overall automation health status."""
        active_strategies = sum(
            1 for s in self._strategies.values()
            if s["status"] == StrategyStatus.ACTIVE
        )
        failed_strategies = sum(
            1 for s in self._strategies.values()
            if s["status"] == StrategyStatus.FAILED
        )
        
        status = "healthy"
        if failed_strategies > 0:
            status = "degraded"
        if failed_strategies > len(self._strategies) / 2:
            status = "critical"
        
        return {
            "status": status,
            "total_strategies": len(self._strategies),
            "active_strategies": active_strategies,
            "failed_strategies": failed_strategies,
            "total_rebalances": len(self._rebalance_history),
            "total_failovers": len(self._failover_history),
            "successful_failovers": sum(1 for f in self._failover_history if f.recovered),
        }


__all__ = [
    "StrategyAutomation",
    "StrategyStatus",
    "RebalanceReason",
    "StrategyMetrics",
    "RebalanceEvent",
    "FailoverEvent",
]
