# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Configuration models for Risk Guardian."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class RiskGuardianConfig:
    """Configuration for the Risk Guardian.

    Attributes:
        initial_capital: Starting capital for simulation.
        daily_loss_limit_pct: Maximum allowed daily loss as percentage (e.g., 5.0 = 5%).
        max_drawdown_pct: Kill-switch trigger level as percentage.
        safe_mode_threshold_pct: Enter safe-mode at this drawdown percentage.
        safe_mode_position_multiplier: Reduce positions by this factor in safe-mode.
        max_position_pct: Maximum position size as percentage of equity.
        enable_kill_switch: Whether to activate kill-switch at max drawdown.
        enable_safe_mode: Whether to use safe-mode at warning levels.
    """

    initial_capital: float = 100_000.0
    daily_loss_limit_pct: float = 5.0
    max_drawdown_pct: float = 10.0
    safe_mode_threshold_pct: float = 7.0
    safe_mode_position_multiplier: float = 0.5
    max_position_pct: float = 20.0
    enable_kill_switch: bool = True
    enable_safe_mode: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "initial_capital": self.initial_capital,
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "safe_mode_threshold_pct": self.safe_mode_threshold_pct,
            "safe_mode_position_multiplier": self.safe_mode_position_multiplier,
            "max_position_pct": self.max_position_pct,
            "enable_kill_switch": self.enable_kill_switch,
            "enable_safe_mode": self.enable_safe_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskGuardianConfig:
        """Create from dictionary."""
        return cls(
            initial_capital=float(data.get("initial_capital", 100_000.0)),
            daily_loss_limit_pct=float(data.get("daily_loss_limit_pct", 5.0)),
            max_drawdown_pct=float(data.get("max_drawdown_pct", 10.0)),
            safe_mode_threshold_pct=float(data.get("safe_mode_threshold_pct", 7.0)),
            safe_mode_position_multiplier=float(
                data.get("safe_mode_position_multiplier", 0.5)
            ),
            max_position_pct=float(data.get("max_position_pct", 20.0)),
            enable_kill_switch=bool(data.get("enable_kill_switch", True)),
            enable_safe_mode=bool(data.get("enable_safe_mode", True)),
        )

    @classmethod
    def from_yaml(cls, path: Path | str) -> RiskGuardianConfig:
        """Load configuration from YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("Configuration file must contain a YAML mapping")

        risk_config = data.get("risk_guardian", data)
        return cls.from_dict(risk_config)


@dataclass(slots=True)
class SimulationResult:
    """Result of a Risk Guardian simulation.

    Attributes:
        baseline_pnl: PnL without risk controls.
        protected_pnl: PnL with Risk Guardian enabled.
        baseline_max_drawdown: Maximum drawdown without controls.
        protected_max_drawdown: Maximum drawdown with controls.
        saved_capital: Amount of capital saved by risk controls.
        saved_capital_pct: Saved capital as percentage of peak equity.
        kill_switch_activations: Number of times kill-switch was triggered.
        safe_mode_periods: Number of periods spent in safe-mode.
        blocked_trades: Number of trades blocked by risk limits.
        baseline_sharpe: Sharpe ratio without controls.
        protected_sharpe: Sharpe ratio with controls.
        baseline_worst_day: Worst single day return without controls.
        protected_worst_day: Worst single day return with controls.
        total_periods: Total number of periods simulated.
        config: Configuration used for the simulation.
    """

    baseline_pnl: float = 0.0
    protected_pnl: float = 0.0
    baseline_max_drawdown: float = 0.0
    protected_max_drawdown: float = 0.0
    saved_capital: float = 0.0
    saved_capital_pct: float = 0.0
    kill_switch_activations: int = 0
    safe_mode_periods: int = 0
    blocked_trades: int = 0
    baseline_sharpe: float = 0.0
    protected_sharpe: float = 0.0
    baseline_worst_day: float = 0.0
    protected_worst_day: float = 0.0
    total_periods: int = 0
    config: RiskGuardianConfig = field(default_factory=RiskGuardianConfig)

    @property
    def sharpe_improvement(self) -> float:
        """Calculate percentage improvement in Sharpe ratio."""
        if self.baseline_sharpe == 0:
            return 0.0
        return (
            (self.protected_sharpe - self.baseline_sharpe) / abs(self.baseline_sharpe)
        ) * 100

    @property
    def drawdown_reduction(self) -> float:
        """Calculate percentage reduction in max drawdown."""
        if self.baseline_max_drawdown == 0:
            return 0.0
        return (
            (self.baseline_max_drawdown - self.protected_max_drawdown)
            / abs(self.baseline_max_drawdown)
        ) * 100

    def summary(self) -> str:
        """Generate a human-readable summary report."""
        lines = [
            "",
            "=" * 60,
            "          RISK GUARDIAN SIMULATION REPORT",
            "=" * 60,
            "",
            f"Period: {self.total_periods} bars",
            f"Initial Capital: ${self.config.initial_capital:,.2f}",
            "",
            "─" * 60,
            "                   BASELINE (No Risk Control)",
            "─" * 60,
            f"  Total Return:      {self.baseline_pnl / self.config.initial_capital * 100:+.1f}%",
            f"  Max Drawdown:      {self.baseline_max_drawdown * 100:.1f}%",
            f"  Sharpe Ratio:      {self.baseline_sharpe:.2f}",
            f"  Worst Day:         {self.baseline_worst_day * 100:.1f}%",
            "",
            "─" * 60,
            "                   WITH RISK GUARDIAN",
            "─" * 60,
            f"  Total Return:      {self.protected_pnl / self.config.initial_capital * 100:+.1f}%",
            f"  Max Drawdown:      {self.protected_max_drawdown * 100:.1f}% (capped at {self.config.max_drawdown_pct}%)",
            f"  Sharpe Ratio:      {self.protected_sharpe:.2f}",
            f"  Worst Day:         {self.protected_worst_day * 100:.1f}% (limited to {self.config.daily_loss_limit_pct}%)",
            "",
            f"  Kill-Switch Activations: {self.kill_switch_activations}",
            f"  Safe Mode Periods:       {self.safe_mode_periods}",
            f"  Blocked Trades:          {self.blocked_trades}",
            "",
            "─" * 60,
            "                   VALUE DELIVERED",
            "─" * 60,
            f"  💰 SAVED CAPITAL:       ${self.saved_capital:,.2f} ({self.saved_capital_pct:.1f}% of peak)",
            f"  📈 SHARPE IMPROVEMENT:  {self.sharpe_improvement:+.0f}%",
            f"  🛡️  DRAWDOWN REDUCTION: {self.drawdown_reduction:.0f}%",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "baseline": {
                "pnl": self.baseline_pnl,
                "pnl_pct": self.baseline_pnl / self.config.initial_capital * 100,
                "max_drawdown": self.baseline_max_drawdown,
                "sharpe_ratio": self.baseline_sharpe,
                "worst_day": self.baseline_worst_day,
            },
            "protected": {
                "pnl": self.protected_pnl,
                "pnl_pct": self.protected_pnl / self.config.initial_capital * 100,
                "max_drawdown": self.protected_max_drawdown,
                "sharpe_ratio": self.protected_sharpe,
                "worst_day": self.protected_worst_day,
            },
            "risk_events": {
                "kill_switch_activations": self.kill_switch_activations,
                "safe_mode_periods": self.safe_mode_periods,
                "blocked_trades": self.blocked_trades,
            },
            "value_delivered": {
                "saved_capital": self.saved_capital,
                "saved_capital_pct": self.saved_capital_pct,
                "sharpe_improvement_pct": self.sharpe_improvement,
                "drawdown_reduction_pct": self.drawdown_reduction,
            },
            "config": self.config.to_dict(),
            "total_periods": self.total_periods,
        }
