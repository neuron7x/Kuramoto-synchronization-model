"""
Backtest Report Generator Module

Модуль для генерації детальних звітів бектестів.

Features:
- Розрахунок метрик продуктивності
- Аналіз трейдів
- Статистика drawdown
- Візуалізація (текстова)
- Експорт звітів
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


class ReportFormat(str, Enum):
    """Формат звіту"""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"


@dataclass
class TradeStatistics:
    """Статистика трейдів"""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    profit_factor: float = 0.0
    payoff_ratio: float = 0.0
    expectancy: float = 0.0
    average_trade_duration: timedelta = field(default_factory=lambda: timedelta())
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0


@dataclass
class DrawdownStatistics:
    """Статистика drawdown"""

    max_drawdown: float = 0.0
    max_drawdown_duration: timedelta = field(default_factory=lambda: timedelta())
    average_drawdown: float = 0.0
    current_drawdown: float = 0.0
    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    drawdown_periods: int = 0


@dataclass
class PerformanceMetrics:
    """Метрики продуктивності"""

    total_return: float = 0.0
    annualized_return: float = 0.0
    volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    omega_ratio: float = 0.0
    information_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0


@dataclass
class MonthlyReturns:
    """Місячні повернення"""

    year: int
    month: int
    return_value: float
    cumulative_return: float


@dataclass
class BacktestReport:
    """Повний звіт бектесту"""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    performance: PerformanceMetrics
    trades: TradeStatistics
    drawdown: DrawdownStatistics
    monthly_returns: List[MonthlyReturns]
    generated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Trade:
    """Окремий трейд"""

    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    quantity: float
    side: str  # "long" or "short"
    pnl: float
    pnl_percent: float
    duration: timedelta


class BacktestReportGenerator:
    """
    Генератор звітів бектестів

    Створює детальні звіти з метриками та статистикою.
    """

    def __init__(
        self,
        risk_free_rate: float = 0.02,
        annualization_factor: int = 252,
        benchmark_returns: Optional[pd.Series] = None,
    ):
        """
        Ініціалізація генератора

        Args:
            risk_free_rate: Безризикова ставка
            annualization_factor: Фактор аналізації
            benchmark_returns: Повернення бенчмарку
        """
        self.risk_free_rate = risk_free_rate
        self.annualization_factor = annualization_factor
        self.benchmark_returns = benchmark_returns

    def generate_report(
        self,
        returns: pd.Series,
        trades: Optional[List[Trade]] = None,
        strategy_name: str = "Strategy",
        initial_capital: float = 100000.0,
    ) -> BacktestReport:
        """
        Генерація звіту бектесту

        Args:
            returns: Серія повернень
            trades: Список трейдів
            strategy_name: Назва стратегії
            initial_capital: Початковий капітал

        Returns:
            Об'єкт звіту
        """
        # Базові розрахунки
        cumulative_returns = (1 + returns).cumprod()
        final_capital = initial_capital * cumulative_returns.iloc[-1]

        # Метрики продуктивності
        performance = self._calculate_performance_metrics(returns)

        # Статистика трейдів
        trade_stats = self._calculate_trade_statistics(trades or [])

        # Статистика drawdown
        drawdown_stats = self._calculate_drawdown_statistics(cumulative_returns)

        # Місячні повернення
        monthly = self._calculate_monthly_returns(returns)

        return BacktestReport(
            strategy_name=strategy_name,
            start_date=returns.index[0] if len(returns) > 0 else datetime.now(),
            end_date=returns.index[-1] if len(returns) > 0 else datetime.now(),
            initial_capital=initial_capital,
            final_capital=float(final_capital),
            performance=performance,
            trades=trade_stats,
            drawdown=drawdown_stats,
            monthly_returns=monthly,
            metadata={
                "n_periods": len(returns),
                "risk_free_rate": self.risk_free_rate,
                "annualization_factor": self.annualization_factor,
            },
        )

    def _calculate_performance_metrics(self, returns: pd.Series) -> PerformanceMetrics:
        """Розрахунок метрик продуктивності"""
        if len(returns) < 2:
            return PerformanceMetrics()

        returns_array = returns.dropna().values

        # Базові метрики
        total_return = (1 + returns).prod() - 1
        annualized_return = (1 + total_return) ** (
            self.annualization_factor / len(returns)
        ) - 1
        volatility = returns.std() * np.sqrt(self.annualization_factor)

        # Sharpe Ratio
        excess_returns = returns - self.risk_free_rate / self.annualization_factor
        sharpe_ratio = (
            excess_returns.mean()
            / returns.std()
            * np.sqrt(self.annualization_factor)
            if returns.std() > 0
            else 0.0
        )

        # Sortino Ratio
        downside_returns = returns[returns < 0]
        downside_std = (
            downside_returns.std() * np.sqrt(self.annualization_factor)
            if len(downside_returns) > 0
            else volatility
        )
        sortino_ratio = (
            (annualized_return - self.risk_free_rate) / downside_std
            if downside_std > 0
            else 0.0
        )

        # Calmar Ratio
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min())
        calmar_ratio = (
            annualized_return / max_drawdown if max_drawdown > 0 else 0.0
        )

        # Omega Ratio
        threshold = self.risk_free_rate / self.annualization_factor
        gains = returns[returns > threshold].sum()
        losses = abs(returns[returns < threshold].sum())
        omega_ratio = gains / losses if losses > 0 else float("inf")

        # VaR та CVaR
        var_95 = np.percentile(returns_array, 5)
        cvar_95 = returns_array[returns_array <= var_95].mean() if len(
            returns_array[returns_array <= var_95]
        ) > 0 else var_95

        # Статистичні моменти
        skewness = float(pd.Series(returns_array).skew())
        kurtosis = float(pd.Series(returns_array).kurtosis())

        # Alpha та Beta (якщо є бенчмарк)
        alpha = 0.0
        beta = 0.0
        information_ratio = 0.0

        if self.benchmark_returns is not None and len(self.benchmark_returns) > 0:
            aligned = pd.DataFrame(
                {"strategy": returns, "benchmark": self.benchmark_returns}
            ).dropna()

            if len(aligned) > 2:
                cov = aligned["strategy"].cov(aligned["benchmark"])
                var_benchmark = aligned["benchmark"].var()
                beta = cov / var_benchmark if var_benchmark > 0 else 0.0
                alpha = (
                    annualized_return
                    - self.risk_free_rate
                    - beta
                    * (
                        aligned["benchmark"].mean() * self.annualization_factor
                        - self.risk_free_rate
                    )
                )

                # Information Ratio
                tracking_error = (
                    aligned["strategy"] - aligned["benchmark"]
                ).std() * np.sqrt(self.annualization_factor)
                active_return = annualized_return - aligned[
                    "benchmark"
                ].mean() * self.annualization_factor
                information_ratio = (
                    active_return / tracking_error if tracking_error > 0 else 0.0
                )

        return PerformanceMetrics(
            total_return=float(total_return),
            annualized_return=float(annualized_return),
            volatility=float(volatility),
            sharpe_ratio=float(sharpe_ratio),
            sortino_ratio=float(sortino_ratio),
            calmar_ratio=float(calmar_ratio),
            omega_ratio=float(min(omega_ratio, 100.0)),
            information_ratio=float(information_ratio),
            alpha=float(alpha),
            beta=float(beta),
            var_95=float(var_95),
            cvar_95=float(cvar_95),
            skewness=float(skewness),
            kurtosis=float(kurtosis),
        )

    def _calculate_trade_statistics(self, trades: List[Trade]) -> TradeStatistics:
        """Розрахунок статистики трейдів"""
        if not trades:
            return TradeStatistics()

        pnls = [t.pnl for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_trades = len(trades)
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        average_win = np.mean(wins) if wins else 0.0
        average_loss = np.mean(losses) if losses else 0.0
        largest_win = max(wins) if wins else 0.0
        largest_loss = min(losses) if losses else 0.0

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        payoff_ratio = (
            abs(average_win / average_loss) if average_loss != 0 else 0.0
        )
        expectancy = (
            win_rate * average_win + (1 - win_rate) * average_loss
        )

        # Середня тривалість трейду
        durations = [t.duration for t in trades]
        avg_duration = sum(durations, timedelta()) / len(durations) if durations else timedelta()

        # Послідовні виграші/програші
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        return TradeStatistics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=float(win_rate),
            average_win=float(average_win),
            average_loss=float(average_loss),
            largest_win=float(largest_win),
            largest_loss=float(largest_loss),
            profit_factor=float(min(profit_factor, 100.0)),
            payoff_ratio=float(payoff_ratio),
            expectancy=float(expectancy),
            average_trade_duration=avg_duration,
            max_consecutive_wins=max_consecutive_wins,
            max_consecutive_losses=max_consecutive_losses,
        )

    def _calculate_drawdown_statistics(
        self, cumulative_returns: pd.Series
    ) -> DrawdownStatistics:
        """Розрахунок статистики drawdown"""
        if len(cumulative_returns) < 2:
            return DrawdownStatistics()

        running_max = cumulative_returns.cummax()
        drawdown = (cumulative_returns - running_max) / running_max

        max_drawdown = abs(drawdown.min())
        current_drawdown = abs(drawdown.iloc[-1])
        average_drawdown = abs(drawdown.mean())

        # Тривалість максимального drawdown
        in_drawdown = drawdown < 0
        drawdown_periods = 0
        max_duration = timedelta()
        current_duration = 0

        for i, is_dd in enumerate(in_drawdown):
            if is_dd:
                current_duration += 1
                if current_duration == 1:
                    drawdown_periods += 1
            else:
                if current_duration > 0:
                    # Конвертація в timedelta (припускаємо денні дані)
                    duration = timedelta(days=current_duration)
                    if duration > max_duration:
                        max_duration = duration
                current_duration = 0

        # Recovery Factor
        total_return = cumulative_returns.iloc[-1] / cumulative_returns.iloc[0] - 1
        recovery_factor = total_return / max_drawdown if max_drawdown > 0 else 0.0

        # Ulcer Index
        squared_drawdowns = drawdown**2
        ulcer_index = np.sqrt(squared_drawdowns.mean())

        return DrawdownStatistics(
            max_drawdown=float(max_drawdown),
            max_drawdown_duration=max_duration,
            average_drawdown=float(average_drawdown),
            current_drawdown=float(current_drawdown),
            recovery_factor=float(recovery_factor),
            ulcer_index=float(ulcer_index),
            drawdown_periods=drawdown_periods,
        )

    def _calculate_monthly_returns(self, returns: pd.Series) -> List[MonthlyReturns]:
        """Розрахунок місячних повернень"""
        if len(returns) == 0:
            return []

        # Групування по місяцях
        monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
        cumulative = (1 + monthly).cumprod()

        result = []
        for date, ret in monthly.items():
            result.append(
                MonthlyReturns(
                    year=date.year,
                    month=date.month,
                    return_value=float(ret),
                    cumulative_return=float(cumulative.loc[date]),
                )
            )

        return result

    def format_report(
        self, report: BacktestReport, format_type: ReportFormat = ReportFormat.TEXT
    ) -> str:
        """
        Форматування звіту

        Args:
            report: Звіт
            format_type: Формат

        Returns:
            Відформатований текст звіту
        """
        if format_type == ReportFormat.TEXT:
            return self._format_text(report)
        elif format_type == ReportFormat.MARKDOWN:
            return self._format_markdown(report)
        elif format_type == ReportFormat.JSON:
            return self._format_json(report)
        else:
            return self._format_text(report)

    def _format_text(self, report: BacktestReport) -> str:
        """Форматування в текстовий вигляд"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"BACKTEST REPORT: {report.strategy_name}")
        lines.append("=" * 60)
        lines.append("")

        # Огляд
        lines.append("OVERVIEW")
        lines.append("-" * 40)
        lines.append(f"Period: {report.start_date.date()} to {report.end_date.date()}")
        lines.append(f"Initial Capital: ${report.initial_capital:,.2f}")
        lines.append(f"Final Capital: ${report.final_capital:,.2f}")
        lines.append(f"Total Return: {report.performance.total_return:.2%}")
        lines.append("")

        # Метрики продуктивності
        lines.append("PERFORMANCE METRICS")
        lines.append("-" * 40)
        p = report.performance
        lines.append(f"Annualized Return: {p.annualized_return:.2%}")
        lines.append(f"Volatility: {p.volatility:.2%}")
        lines.append(f"Sharpe Ratio: {p.sharpe_ratio:.2f}")
        lines.append(f"Sortino Ratio: {p.sortino_ratio:.2f}")
        lines.append(f"Calmar Ratio: {p.calmar_ratio:.2f}")
        lines.append(f"Omega Ratio: {p.omega_ratio:.2f}")
        lines.append(f"VaR (95%): {p.var_95:.2%}")
        lines.append(f"CVaR (95%): {p.cvar_95:.2%}")
        if p.alpha != 0 or p.beta != 0:
            lines.append(f"Alpha: {p.alpha:.4f}")
            lines.append(f"Beta: {p.beta:.4f}")
        lines.append("")

        # Drawdown
        lines.append("DRAWDOWN ANALYSIS")
        lines.append("-" * 40)
        d = report.drawdown
        lines.append(f"Max Drawdown: {d.max_drawdown:.2%}")
        lines.append(f"Max Drawdown Duration: {d.max_drawdown_duration}")
        lines.append(f"Average Drawdown: {d.average_drawdown:.2%}")
        lines.append(f"Current Drawdown: {d.current_drawdown:.2%}")
        lines.append(f"Recovery Factor: {d.recovery_factor:.2f}")
        lines.append(f"Ulcer Index: {d.ulcer_index:.4f}")
        lines.append("")

        # Статистика трейдів
        lines.append("TRADE STATISTICS")
        lines.append("-" * 40)
        t = report.trades
        lines.append(f"Total Trades: {t.total_trades}")
        lines.append(f"Winning Trades: {t.winning_trades}")
        lines.append(f"Losing Trades: {t.losing_trades}")
        lines.append(f"Win Rate: {t.win_rate:.2%}")
        lines.append(f"Average Win: ${t.average_win:,.2f}")
        lines.append(f"Average Loss: ${t.average_loss:,.2f}")
        lines.append(f"Largest Win: ${t.largest_win:,.2f}")
        lines.append(f"Largest Loss: ${t.largest_loss:,.2f}")
        lines.append(f"Profit Factor: {t.profit_factor:.2f}")
        lines.append(f"Payoff Ratio: {t.payoff_ratio:.2f}")
        lines.append(f"Expectancy: ${t.expectancy:,.2f}")
        lines.append(f"Max Consecutive Wins: {t.max_consecutive_wins}")
        lines.append(f"Max Consecutive Losses: {t.max_consecutive_losses}")
        lines.append("")

        # Місячна таблиця
        if report.monthly_returns:
            lines.append("MONTHLY RETURNS")
            lines.append("-" * 40)
            current_year = None
            for mr in report.monthly_returns:
                if current_year != mr.year:
                    if current_year is not None:
                        lines.append("")
                    current_year = mr.year
                    lines.append(f"\n{mr.year}:")
                month_name = datetime(2000, mr.month, 1).strftime("%b")
                lines.append(f"  {month_name}: {mr.return_value:+.2%}")

        lines.append("")
        lines.append("=" * 60)
        lines.append(f"Report generated at: {report.generated_at.isoformat()}")

        return "\n".join(lines)

    def _format_markdown(self, report: BacktestReport) -> str:
        """Форматування в Markdown"""
        lines = []
        lines.append(f"# Backtest Report: {report.strategy_name}")
        lines.append("")

        lines.append("## Overview")
        lines.append(f"- **Period:** {report.start_date.date()} to {report.end_date.date()}")
        lines.append(f"- **Initial Capital:** ${report.initial_capital:,.2f}")
        lines.append(f"- **Final Capital:** ${report.final_capital:,.2f}")
        lines.append(f"- **Total Return:** {report.performance.total_return:.2%}")
        lines.append("")

        lines.append("## Performance Metrics")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        p = report.performance
        lines.append(f"| Annualized Return | {p.annualized_return:.2%} |")
        lines.append(f"| Volatility | {p.volatility:.2%} |")
        lines.append(f"| Sharpe Ratio | {p.sharpe_ratio:.2f} |")
        lines.append(f"| Sortino Ratio | {p.sortino_ratio:.2f} |")
        lines.append(f"| Calmar Ratio | {p.calmar_ratio:.2f} |")
        lines.append(f"| Max Drawdown | {report.drawdown.max_drawdown:.2%} |")
        lines.append("")

        lines.append("## Trade Statistics")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        t = report.trades
        lines.append(f"| Total Trades | {t.total_trades} |")
        lines.append(f"| Win Rate | {t.win_rate:.2%} |")
        lines.append(f"| Profit Factor | {t.profit_factor:.2f} |")
        lines.append(f"| Expectancy | ${t.expectancy:,.2f} |")
        lines.append("")

        lines.append(f"*Report generated at: {report.generated_at.isoformat()}*")

        return "\n".join(lines)

    def _format_json(self, report: BacktestReport) -> str:
        """Форматування в JSON"""
        import json

        def serialize(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, timedelta):
                return str(obj)
            elif hasattr(obj, "__dict__"):
                return {k: serialize(v) for k, v in obj.__dict__.items()}
            elif isinstance(obj, list):
                return [serialize(i) for i in obj]
            elif isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            return obj

        return json.dumps(serialize(report), indent=2)

    def get_summary(self, report: BacktestReport) -> Dict:
        """
        Отримання короткого саммарі

        Args:
            report: Звіт

        Returns:
            Словник з ключовими метриками
        """
        return {
            "strategy": report.strategy_name,
            "period": f"{report.start_date.date()} - {report.end_date.date()}",
            "total_return": f"{report.performance.total_return:.2%}",
            "annualized_return": f"{report.performance.annualized_return:.2%}",
            "sharpe_ratio": f"{report.performance.sharpe_ratio:.2f}",
            "max_drawdown": f"{report.drawdown.max_drawdown:.2%}",
            "total_trades": report.trades.total_trades,
            "win_rate": f"{report.trades.win_rate:.2%}",
            "profit_factor": f"{report.trades.profit_factor:.2f}",
        }
