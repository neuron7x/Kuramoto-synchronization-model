# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integrated neuro trading system built on top of DPA/AIC/NRE."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..motivation import FractalMotivationController, MotivationDecision
from .aic import AgencyControlNetwork
from .config import NeuroAdvancedConfig
from .dpa import DopaminePredictionNetwork
from .monitor import NeuroStateMonitor
from .nre import NeuroplasticReinforcementEngine
from .types import MarketContext, TradeOutcome, TradeResult

logger = logging.getLogger(__name__)


class MultiscaleFractalAnalyzer:
    """Extracts fractal and volatility features from price series."""

    async def analyze(self, prices: np.ndarray) -> Dict[str, Any]:
        prices = self._validate_prices(prices)
        returns = np.diff(np.log(prices))
        volatility = float(np.std(returns))
        trend = float(np.tanh((prices[-1] - prices[0]) / (np.std(prices) + 1e-9)))
        hurst = float(self._approx_hurst_rs(returns))
        fractal_dim = float(np.clip(2.0 - hurst, 1.0, 2.0))
        dynamics = self._compute_multiscale_dynamics(returns)
        regime = self._classify_regime(hurst, trend, volatility)
        persistence_index = float(
            np.clip(0.5 + (dynamics["scaling_exponent"] - 0.5) * 0.8, 0.0, 1.0)
        )
        return {
            "volatility": volatility,
            "trend_strength": trend,
            "hurst": hurst,
            "fractal_dim": fractal_dim,
            "regime": regime,
            "n": int(prices.size),
            "dynamics": dynamics,
            "persistence_index": persistence_index,
        }

    async def analyze_assets(
        self, asset_series: Mapping[str, Sequence[float]]
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        if not asset_series:
            raise ValueError("asset_series must contain at least one asset")

        tasks = [self.analyze(np.asarray(series, dtype=float)) for series in asset_series.values()]
        assets = list(asset_series.keys())
        results = await asyncio.gather(*tasks)
        per_asset = {asset: result for asset, result in zip(assets, results)}
        aggregated = self._aggregate_features(per_asset)
        return per_asset, aggregated

    def _validate_prices(self, prices: Sequence[float] | np.ndarray) -> np.ndarray:
        array = np.asarray(prices, dtype=float)
        if array.ndim != 1 or array.size < 20:
            raise ValueError("Expected a 1D array with at least 20 price points")
        if np.any(array <= 0.0):
            raise ValueError("Prices must be strictly positive for log-return analysis")
        return array

    def _approx_hurst_rs(self, returns: np.ndarray) -> float:
        if returns.size < 50:
            return 0.5
        mean_adjusted = returns - returns.mean()
        cumulative = np.cumsum(mean_adjusted)
        rs = (cumulative.max() - cumulative.min()) / (returns.std() + 1e-9)
        hurst = 0.5 + 0.1 * np.log(rs + 1e-9)
        return float(np.clip(hurst, 0.0, 1.0))

    def _compute_multiscale_dynamics(self, returns: np.ndarray) -> Dict[str, Any]:
        scales = np.asarray([1, 2, 4, 8], dtype=float)
        volatilities: List[float] = []
        realised_scales: List[float] = []
        for scale in scales:
            window = int(scale)
            segments = returns[: returns.size - (returns.size % window)]
            if segments.size < 2 * window:
                continue
            reshaped = segments.reshape(-1, window)
            aggregated = reshaped.sum(axis=1)
            vol = float(np.std(aggregated))
            if vol <= 0.0:
                continue
            volatilities.append(vol)
            realised_scales.append(scale)

        if len(volatilities) < 2:
            scaling_exponent = 0.5
            stability = 0.5
        else:
            log_scales = np.log(realised_scales)
            log_vols = np.log(volatilities)
            slope, intercept = np.polyfit(log_scales, log_vols, 1)
            scaling_exponent = float(np.clip(slope, -0.2, 1.2))
            deviation = abs(scaling_exponent - 0.5)
            stability = float(np.exp(-((deviation / 0.25) ** 2)))

        return {
            "scales": realised_scales,
            "volatility_by_scale": volatilities,
            "scaling_exponent": float(scaling_exponent),
            "stability": float(np.clip(stability, 0.0, 1.0)),
        }

    def _aggregate_features(self, features: Mapping[str, Dict[str, Any]]) -> Dict[str, Any]:
        if not features:
            raise ValueError("Cannot aggregate empty feature mapping")

        items = list(features.items())
        volatilities = np.asarray(
            [max(1e-12, item[1]["volatility"]) for item in items], dtype=float
        )
        weights = (
            volatilities / volatilities.sum()
            if float(volatilities.sum()) > 0
            else np.full_like(volatilities, 1.0 / len(items))
        )

        def _weighted(field: str) -> float:
            values = np.asarray([item[1][field] for item in items], dtype=float)
            return float(np.dot(values, weights))

        trend_strength = _weighted("trend_strength")
        volatility = _weighted("volatility")
        hurst = _weighted("hurst")
        fractal_dim = _weighted("fractal_dim")
        persistence_index = _weighted("persistence_index")

        scaling_values = np.asarray(
            [item[1]["dynamics"].get("scaling_exponent", 0.5) for item in items],
            dtype=float,
        )
        stability_values = np.asarray(
            [item[1]["dynamics"].get("stability", 0.5) for item in items], dtype=float
        )
        scaling = float(np.dot(scaling_values, weights))
        stability = float(np.dot(stability_values, weights))

        regimes = Counter(item[1]["regime"] for item in items)
        dominant_regime, dominant_count = regimes.most_common(1)[0]
        regime_confidence = float(dominant_count / len(items))

        volatility_dispersion = float(np.std([item[1]["volatility"] for item in items]))

        scale_values: Dict[float, List[float]] = defaultdict(list)
        for _, data in items:
            scales = data["dynamics"].get("scales", [])
            vols = data["dynamics"].get("volatility_by_scale", [])
            for scale, vol in zip(scales, vols):
                scale_values[float(scale)].append(float(vol))
        sorted_scales = sorted(scale_values.keys())
        aggregated_vol_by_scale = [
            float(np.mean(scale_values[scale])) if scale_values[scale] else 0.0
            for scale in sorted_scales
        ]

        return {
            "volatility": volatility,
            "trend_strength": trend_strength,
            "hurst": hurst,
            "fractal_dim": fractal_dim,
            "regime": dominant_regime,
            "regime_distribution": dict(regimes),
            "regime_confidence": regime_confidence,
            "n": int(sum(item[1]["n"] for item in items)),
            "asset_count": len(items),
            "volatility_dispersion": volatility_dispersion,
            "dynamics": {
                "scaling_exponent": scaling,
                "stability": stability,
                "scales": sorted_scales,
                "volatility_by_scale": aggregated_vol_by_scale,
            },
            "persistence_index": persistence_index,
            "fractal_scaling": scaling,
            "fractal_stability": stability,
        }

    def _classify_regime(self, hurst: float, trend: float, volatility: float) -> str:
        if abs(trend) > 0.35 and hurst > 0.55:
            return "trending"
        if hurst < 0.45 and volatility > 0.01:
            return "choppy"
        return "normal"


class CandidateGenerator:
    """Generates baseline trading candidates from fractal features."""

    def generate(
        self,
        asset_features: Mapping[str, Dict[str, Any]],
        aggregated_features: Dict[str, Any],
        base_strategies: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        strategies = base_strategies or ["fractal_momentum", "fractal_mean_reversion"]
        output: List[Dict[str, Any]] = []
        global_trend = float(aggregated_features.get("trend_strength", 0.0))
        global_volatility = float(aggregated_features.get("volatility", 0.0))
        global_scaling = float(aggregated_features.get("fractal_scaling", 0.5))
        global_stability = float(aggregated_features.get("fractal_stability", 0.5))

        for asset, features in asset_features.items():
            trend = float(features.get("trend_strength", global_trend))
            volatility = float(features.get("volatility", global_volatility))
            scaling = float(features.get("dynamics", {}).get("scaling_exponent", global_scaling))
            stability = float(features.get("dynamics", {}).get("stability", global_stability))

            persistence_bias = float(1.0 + (scaling - 0.5) * 0.6)
            stability_bias = float(0.8 + 0.4 * stability)
            volatility_factor = float(np.clip(0.45 + volatility * 10.0, 0.15, 2.0))
            risk_base = float(np.clip(volatility_factor * stability_bias, 0.15, 2.0))

            edge_trend = float(abs(trend)) * 0.03 * persistence_bias
            edge_mean_reversion = float(
                (1.0 - abs(trend)) * 0.02 * stability_bias
                + (
                    0.015
                    if features.get("regime", aggregated_features.get("regime")) == "choppy"
                    else 0.0
                )
            )

            if "fractal_momentum" in strategies:
                output.append(
                    {
                        "asset": asset,
                        "strategy": "fractal_momentum",
                        "side": "long" if trend >= 0 else "short",
                        "position_size": 1.0 if trend >= 0 else 0.8,
                        "risk_level": risk_base,
                        "confidence": 0.75,
                        "expected_edge": edge_trend,
                        "fractal_features": features,
                    }
                )
            if "fractal_mean_reversion" in strategies:
                output.append(
                    {
                        "asset": asset,
                        "strategy": "fractal_mean_reversion",
                        "side": "short" if trend >= 0 else "long",
                        "position_size": 0.9 if features["regime"] == "choppy" else 0.7,
                        "risk_level": float(np.clip(risk_base * 0.9, 0.15, 2.0)),
                        "confidence": 0.7,
                        "expected_edge": edge_mean_reversion,
                        "fractal_features": features,
                    }
                )
        return output


class NeuroRiskManager:
    """Applies safety limits and volatility-aware scaling."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._cfg = config

    async def apply(
        self,
        decision: Dict[str, Any],
        neuro_context: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        size = float(decision.get("position_size", 1.0))
        risk = float(decision.get("risk_level", 1.0))
        confidence = float(neuro_context.get("overall_confidence", 0.6))
        volatility = float(market_context.get("volatility", 0.0))

        damping = max(0.35, min(1.0, 0.95 / (1.0 + 5.0 * volatility))) * max(0.4, confidence)
        asset = decision.get("asset")
        asset_context = None
        if asset:
            asset_context = market_context.get("asset_contexts", {}).get(asset)
        damping *= self._fractal_damping_factor(market_context, asset_context)
        if (
            confidence < self._cfg.slo_gate_confidence_min
            and volatility > self._cfg.slo_gate_max_volatility
        ):
            damping *= self._cfg.slo_emergency_downscale

        bounds = self._cfg.policy_bounds
        new_size = float(np.clip(size * damping, bounds.min_position, bounds.max_position))
        new_risk = float(np.clip(risk, bounds.min_risk, bounds.max_risk))

        sl_dist = float(np.clip(2.5 * volatility, 0.003, 0.08))
        tp_dist = float(np.clip(4.0 * volatility, 0.006, 0.16))

        adjusted = dict(decision)
        adjusted["position_size"] = new_size
        adjusted["risk_level"] = new_risk
        adjusted.setdefault("risk_params", {})
        adjusted["risk_params"].update({"sl_dist": sl_dist, "tp_dist": tp_dist})
        return adjusted

    def _fractal_damping_factor(
        self, market_context: Dict[str, Any], asset_context: Optional[Dict[str, Any]]
    ) -> float:
        context = dict(market_context)
        if asset_context:
            context.update(asset_context)

        scaling = float(context.get("fractal_scaling", market_context.get("fractal_scaling", 0.5)))
        stability = float(
            np.clip(
                context.get("fractal_stability", market_context.get("fractal_stability", 0.5)),
                0.0,
                1.0,
            )
        )
        dimension = float(context.get("fractal_dim", market_context.get("fractal_dim", 1.5)))

        persistence = float(np.clip(1.0 + (scaling - 0.5) * 1.4, 0.6, 1.4))
        stability_factor = 0.6 + 0.4 * stability
        dimension_factor = float(np.clip(1.0 - 0.25 * abs(dimension - 1.5), 0.5, 1.1))

        return float(np.clip(persistence * stability_factor * dimension_factor, 0.5, 1.25))


class NeuroDecisionIntegrator:
    """Ranks modulated decisions using configurable weights."""

    def __init__(self, config: NeuroAdvancedConfig, nre: NeuroplasticReinforcementEngine):
        self._cfg = config
        self._nre = nre

    async def integrate(
        self,
        decisions: List[Dict[str, Any]],
        neuro_context: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        best: Dict[str, Any] | None = None
        best_score = float("-inf")
        weights = self._cfg.decision_weights

        for decision in decisions:
            modulation = decision.get("neuro_modulation", {})
            edge = float(decision.get("expected_edge", 0.0))
            size = float(decision.get("position_size", 0.0))
            inverse_risk = 1.0 / (float(decision.get("risk_level", 1.0)) + 1e-9)
            confidence = float(modulation.get("final_confidence", decision.get("confidence", 0.6)))
            context_pref = self._nre.context_preference(decision["strategy"], market_context)

            score = (
                weights.edge * edge
                + weights.size * size
                + weights.inverse_risk * inverse_risk
                + weights.confidence * confidence
                + weights.context_preference * context_pref
            )
            if score > best_score:
                best = decision
                best_score = score

        if best is None:
            return {}
        best["selection_score"] = float(best_score)
        return best


class EnhancedFractalNeuroeconomicCore:
    """Combines fractal analysis with the neurobiological subsystems."""

    def __init__(self, config: NeuroAdvancedConfig):
        self._cfg = config
        self._dpa = DopaminePredictionNetwork(config)
        self._aic = AgencyControlNetwork(config)
        self._nre = NeuroplasticReinforcementEngine(config)
        self._analyzer = MultiscaleFractalAnalyzer()
        self._candidate_generator = CandidateGenerator()
        self._risk_manager = NeuroRiskManager(config)
        self._integrator = NeuroDecisionIntegrator(config, self._nre)
        self._motivation = FractalMotivationController(
            actions=(
                "exploit",
                "explore",
                "deepen",
                "broaden",
                "stabilize",
                "pause_and_audit",
            ),
            exploration_coef=max(0.6, min(1.4, config.decision_weights.confidence + 0.5)),
        )

    @property
    def dopamine(self) -> DopaminePredictionNetwork:
        return self._dpa

    @property
    def agency(self) -> AgencyControlNetwork:
        return self._aic

    @property
    def neuroplasticity(self) -> NeuroplasticReinforcementEngine:
        return self._nre

    async def process_trading_decision(
        self, market_data: Dict[str, Any], portfolio: Dict[str, Any]
    ) -> Dict[str, Any]:
        asset_series = self._extract_price_series(market_data)
        if not asset_series:
            raise ValueError("market_data does not contain any price series")
        asset_features, fractal = await self._analyzer.analyze_assets(asset_series)
        assets = list(asset_series.keys())
        base_strategies = portfolio.get("strategies") or [
            "fractal_momentum",
            "fractal_mean_reversion",
        ]
        dynamics = fractal.get("dynamics", {})
        asset_contexts = {
            asset: {
                "fractal_scaling": data.get("dynamics", {}).get(
                    "scaling_exponent", fractal.get("fractal_scaling", 0.5)
                ),
                "fractal_stability": data.get("dynamics", {}).get(
                    "stability", fractal.get("fractal_stability", 0.5)
                ),
                "fractal_dim": data.get("fractal_dim", fractal.get("fractal_dim", 1.5)),
                "volatility": data.get("volatility", fractal.get("volatility", 0.0)),
                "trend_strength": data.get("trend_strength", fractal.get("trend_strength", 0.0)),
                "regime": data.get("regime", fractal.get("regime", "normal")),
            }
            for asset, data in asset_features.items()
        }
        market_context = {
            "volatility": fractal["volatility"],
            "trend_strength": fractal["trend_strength"],
            "regime": fractal["regime"],
            "fractal_scaling": dynamics.get("scaling_exponent", 0.5),
            "fractal_stability": dynamics.get("stability", 0.5),
            "fractal_dim": fractal["fractal_dim"],
            "asset_contexts": asset_contexts,
            "regime_distribution": fractal.get("regime_distribution", {}),
            "regime_confidence": fractal.get("regime_confidence", 0.0),
            "volatility_dispersion": fractal.get("volatility_dispersion", 0.0),
        }

        neuro_context = await self._build_neuro_context(
            assets, base_strategies, fractal, asset_features
        )
        motivation_state = self._motivation.recommend(
            state=[
                fractal["volatility"],
                fractal["trend_strength"],
                fractal["hurst"],
                fractal["fractal_dim"],
            ],
            signals={
                "PnL": float(portfolio.get("PnL", 0.0)),
                "risk_ok": bool(portfolio.get("risk_ok", True)),
                "compliance_ok": bool(portfolio.get("compliance_ok", True)),
                "hazard": portfolio.get("hazard", fractal["regime"] == "choppy"),
                "volatility": fractal["volatility"],
                "trend_strength": fractal["trend_strength"],
            },
        )
        candidates = self._candidate_generator.generate(asset_features, fractal, base_strategies)

        modulated: List[Dict[str, Any]] = []
        for candidate in candidates:
            asset = candidate["asset"]
            strategy = candidate["strategy"]
            dopamine_risk = neuro_context["dopamine_states"].get(f"{asset}_{strategy}", 1.0)
            size_mod = neuro_context["agency_modulator"]
            strategy_weight = float(self._nre.get_strategy_weight(strategy))

            adjusted = dict(candidate)
            adjusted["position_size"] = float(
                adjusted["position_size"] * size_mod * strategy_weight
            )
            adjusted["risk_level"] = float(
                np.clip(
                    adjusted["risk_level"] * dopamine_risk,
                    self._cfg.policy_bounds.min_risk,
                    self._cfg.policy_bounds.max_risk,
                )
            )
            adjusted["confidence"] = float(
                adjusted["confidence"] * neuro_context["overall_confidence"]
            )
            adjusted["neuro_modulation"] = {
                "dopamine_effect": float(dopamine_risk),
                "agency_effect": float(size_mod),
                "strategy_weight": strategy_weight,
                "final_confidence": adjusted["confidence"],
            }
            adjusted.setdefault("fractal_features", candidate.get("fractal_features", {}))
            adjusted = await self._risk_manager.apply(adjusted, neuro_context, market_context)
            self._apply_motivation_modulation(adjusted, motivation_state)
            modulated.append(adjusted)

        final_decision = await self._integrator.integrate(modulated, neuro_context, market_context)
        return {
            "final_decision": final_decision,
            "modulated_candidates": modulated,
            "neuro_context": neuro_context,
            "fractal_features": fractal,
            "asset_fractal_features": asset_features,
            "market_context": market_context,
            "motivation_state": motivation_state,
        }

    async def update_neuro_states(self, execution_results: Dict[str, Any]) -> None:
        trades = execution_results.get("trades", [])
        market_context = MarketContext(
            volatility=float(execution_results.get("volatility", 0.3)),
            trend_strength=float(execution_results.get("trend_strength", 0.0)),
            regime=execution_results.get("regime", "normal"),
        )
        learning_context = {
            "volatility": market_context.volatility,
            "regime": market_context.regime,
            "context_fit": execution_results.get("context_fit", 1.0),
        }

        realized_rewards: list[float] = []
        for trade_data in trades:
            trade = self._parse_trade(trade_data)
            self._dpa.update(
                trade.asset, trade.strategy, trade.pnl_percentage, trade.expected_reward
            )
            self._aic.update(trade, market_context)
            self._nre.reinforce(trade.strategy, trade, learning_context)
            realized_rewards.append(trade.pnl_percentage)
        if realized_rewards:
            self._motivation.register_outcome(float(np.mean(realized_rewards)))

    async def _build_neuro_context(
        self,
        assets: Iterable[str],
        strategies: Iterable[str],
        fractal: Dict[str, Any],
        asset_fractals: Mapping[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        dopamine_states: Dict[str, float] = {}
        for asset in assets:
            for strategy in strategies:
                dopamine_states[f"{asset}_{strategy}"] = self._dpa.get_risk_modulation(
                    asset, strategy
                )
        size_modulator = self._aic.size_modulator()
        return {
            "dopamine_states": dopamine_states,
            "agency_modulator": float(size_modulator),
            "overall_confidence": float(self._aic.state()["control_confidence"]),
            "market_volatility": float(fractal["volatility"]),
            "trend_strength": float(fractal["trend_strength"]),
            "regime": fractal["regime"],
            "fractal_scaling": float(
                fractal.get("dynamics", {}).get(
                    "scaling_exponent", fractal.get("fractal_scaling", 0.5)
                )
            ),
            "fractal_stability": float(
                fractal.get("dynamics", {}).get("stability", fractal.get("fractal_stability", 0.5))
            ),
            "persistence_index": float(fractal.get("persistence_index", 0.5)),
            "asset_fractal_features": dict(asset_fractals),
        }

    def _parse_trade(self, trade_data: Dict[str, Any]) -> TradeResult:
        outcome_value = trade_data.get("outcome")
        if not outcome_value:
            pnl = float(trade_data.get("pnl_percentage", 0.0))
            if pnl > 0:
                outcome_value = TradeOutcome.WIN.value
            elif pnl < 0:
                outcome_value = TradeOutcome.LOSS.value
            else:
                outcome_value = TradeOutcome.NEUTRAL.value
        return TradeResult(
            asset=trade_data.get("asset", "UNKNOWN"),
            strategy=trade_data.get("strategy", "default"),
            outcome=TradeOutcome(outcome_value),
            pnl_percentage=float(trade_data.get("pnl_percentage", 0.0)),
            signal_strength=float(trade_data.get("signal_strength", 0.6)),
            strategy_complexity=float(trade_data.get("strategy_complexity", 1.0)),
            loss_magnitude=(
                float(abs(trade_data.get("pnl_percentage", 0.0)))
                if trade_data.get("pnl_percentage", 0.0) < 0
                else 0.0
            ),
            expected_reward=float(trade_data.get("expected_reward", 0.0)),
            profit_magnitude=float(max(0.0, trade_data.get("pnl_percentage", 0.0))),
        )

    def _extract_price_series(self, market_data: Dict[str, Any]) -> Dict[str, np.ndarray]:
        series: Dict[str, np.ndarray] = {}
        if isinstance(market_data.get("prices"), list):
            series["ASSET"] = np.asarray(market_data["prices"], dtype=float)
        if isinstance(market_data.get("series"), dict):
            for name, values in market_data["series"].items():
                if isinstance(values, list) and len(values) >= 20:
                    series[name] = np.asarray(values, dtype=float)
        if isinstance(market_data.get("assets"), dict):
            for name, payload in market_data["assets"].items():
                prices = payload.get("prices") if isinstance(payload, dict) else None
                if isinstance(prices, list) and len(prices) >= 20:
                    series[name] = np.asarray(prices, dtype=float)
        return series

    def _apply_motivation_modulation(
        self, candidate: Dict[str, Any], motivation: MotivationDecision
    ) -> None:
        modulation = candidate.setdefault("neuro_modulation", {})
        modulation.update(
            {
                "motivation_signal": motivation.motivation_signal,
                "motivation_action": motivation.action,
                "motivation_scores": motivation.scores,
                "motivation_metrics": motivation.monitor_metrics,
                "intrinsic_reward": motivation.intrinsic_reward,
                "allostatic_load": motivation.allostatic_load,
            }
        )
        signal = motivation.motivation_signal
        if motivation.action == "exploit":
            candidate["expected_edge"] = float(candidate["expected_edge"] * (1.0 + 0.1 * signal))
        elif motivation.action == "explore":
            candidate["confidence"] = float(candidate["confidence"] * (1.0 + 0.05 * abs(signal)))
        elif motivation.action == "deepen":
            candidate["position_size"] = float(
                np.clip(
                    candidate["position_size"] * (1.0 + 0.08 * signal),
                    self._cfg.policy_bounds.min_position,
                    self._cfg.policy_bounds.max_position,
                )
            )
        elif motivation.action == "broaden":
            candidate["risk_level"] = float(
                np.clip(
                    candidate["risk_level"] * (1.0 - 0.1 * abs(signal)),
                    self._cfg.policy_bounds.min_risk,
                    self._cfg.policy_bounds.max_risk,
                )
            )
        elif motivation.action == "pause_and_audit":
            candidate["position_size"] = 0.0
            candidate["risk_level"] = float(self._cfg.policy_bounds.min_risk)
            candidate["confidence"] = float(candidate["confidence"] * 0.4)


class IntegratedNeuroTradingSystem:
    """Production oriented wrapper with monitoring and state persistence."""

    def __init__(self, config: Optional[NeuroAdvancedConfig] = None):
        self._cfg = config or NeuroAdvancedConfig()
        self._core = EnhancedFractalNeuroeconomicCore(self._cfg)
        self._monitor = NeuroStateMonitor(self._cfg) if self._cfg.monitoring_enabled else None
        self._last_update: Optional[str] = None

    async def process_trading_cycle(
        self, market_data: Dict[str, Any], portfolio_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = await self._core.process_trading_decision(market_data, portfolio_state)
        timestamp = datetime.now().isoformat()
        if self._monitor:
            self._monitor.record(
                "decision",
                {
                    "confidence": result["neuro_context"].get("overall_confidence", 0.0),
                    "volatility": result["fractal_features"].get("volatility", 0.0),
                },
            )
        self._last_update = timestamp
        return {
            "timestamp": self._last_update,
            **result,
            "system_health": self._health_snapshot(),
        }

    async def update_from_execution(self, execution_results: Dict[str, Any]) -> Dict[str, Any]:
        await self._core.update_neuro_states(execution_results)
        updates = {
            "dpa": self._core.dopamine.state(),
            "aic": self._core.agency.state(),
            "nre": self._core.neuroplasticity.state(),
        }
        alerts = self._alerts(updates)
        if self._monitor:
            self._monitor.record("execution", updates)
        return {"updates": updates, "alerts": alerts, "timestamp": self._last_update}

    def save_state(self, path: str) -> bool:
        try:
            state = self.full_state()
            with open(path, "w", encoding="utf-8") as file:
                json.dump(state, file, indent=2, ensure_ascii=False)
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to save neuro state: %s", exc)
            return False

    def load_state(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            if "dpa" in payload:
                dopamine_state = payload["dpa"]
                self._core.dopamine._expected = dopamine_state.get("expected_rewards", {})
                self._core.dopamine._dopamine_levels = dopamine_state.get("dopamine_levels", {})
            if "aic" in payload:
                agency_state = payload["aic"]
                self._core.agency._confidence = agency_state.get("control_confidence", 0.7)
                self._core.agency._insula_activation = agency_state.get("insula_activation", 0.0)
            if "nre" in payload:
                nre_state = payload["nre"]
                self._core.neuroplasticity._weights = defaultdict(
                    lambda: 0.5, nre_state.get("strategy_weights", {})
                )
                self._core.neuroplasticity._success_rate = defaultdict(
                    lambda: 0.5, nre_state.get("success_rates", {})
                )
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to load neuro state: %s", exc)
            return False

    def full_state(self) -> Dict[str, Any]:
        return {
            "dpa": self._core.dopamine.state(),
            "aic": self._core.agency.state(),
            "nre": self._core.neuroplasticity.state(),
            "config": self._cfg.model_dump(),
            "last_update": self._last_update,
            "health": self._health_snapshot(),
        }

    def _health_snapshot(self) -> Dict[str, str]:
        dpa_state = self._core.dopamine.state()
        aic_state = self._core.agency.state()
        nre_state = self._core.neuroplasticity.state()
        health = {
            "dpa": "healthy",
            "aic": "healthy",
            "nre": "healthy",
            "overall": "healthy",
        }

        thresholds = self._cfg.merged_alert_thresholds()
        if dpa_state.get("avg_dopamine_level", 0.5) > thresholds["dopamine_spike"]:
            health["dpa"] = "warning"
        if aic_state.get("control_confidence", 0.6) < thresholds["confidence_collapse"]:
            health["aic"] = "critical"
        elif aic_state.get("control_confidence", 0.6) < 0.4:
            health["aic"] = "warning"
        if nre_state.get("avg_strategy_weight", 0.5) < thresholds["strategy_stagnation"]:
            health["nre"] = "warning"

        if any(status == "critical" for status in health.values() if status != "healthy"):
            health["overall"] = "critical"
        elif any(status == "warning" for status in health.values() if status != "healthy"):
            health["overall"] = "warning"
        return health

    def _alerts(self, updates: Dict[str, Any]) -> List[Dict[str, Any]]:
        thresholds = self._cfg.merged_alert_thresholds()
        alerts: List[Dict[str, Any]] = []
        aic_conf = updates["aic"].get("control_confidence", 1.0)
        if aic_conf < thresholds["confidence_collapse"]:
            alerts.append(
                {
                    "type": "confidence_collapse",
                    "severity": "critical",
                    "message": f"Confidence={aic_conf:.2f}",
                }
            )
        dpa_level = updates["dpa"].get("avg_dopamine_level", 0.0)
        if dpa_level > thresholds["dopamine_spike"]:
            alerts.append(
                {
                    "type": "dopamine_spike",
                    "severity": "warning",
                    "message": "Elevated dopamine — watch optimism bias",
                }
            )
        avg_weight = updates["nre"].get("avg_strategy_weight", 1.0)
        if avg_weight < thresholds["strategy_stagnation"]:
            alerts.append(
                {
                    "type": "strategy_stagnation",
                    "severity": "warning",
                    "message": "Low average strategy weight — possible learning stagnation",
                }
            )
        return alerts


class ECANeuroTradingAdapter:
    """Metadata adapter for integration with external environments."""

    SPEC = {
        "version": "2.3",
        "module_name": "neuro_fractal_trading_hybrid",
        "components": {
            "dopamine_system": {"class": "DopaminePredictionNetwork"},
            "agency_control": {"class": "AgencyControlNetwork"},
            "neuroplasticity": {"class": "NeuroplasticReinforcementEngine"},
            "fractal_analyzer": {"class": "MultiscaleFractalAnalyzer"},
            "risk_manager": {"class": "NeuroRiskManager"},
            "decision_integrator": {"class": "NeuroDecisionIntegrator"},
        },
        "integration_points": {
            "decision_modulation": [
                "position_size",
                "risk_level",
                "strategy_selection",
            ],
            "learning_triggers": [
                "trade_execution",
                "portfolio_rebalance",
                "market_regime_change",
            ],
        },
        "monitoring": {
            "metrics": [
                "dopamine_levels",
                "confidence",
                "strategy_weights",
                "learning_efficiency",
            ],
            "alerts": ["confidence_collapse", "dopamine_spike", "strategy_stagnation"],
        },
    }

    @classmethod
    def get_neuro_trading_module(cls) -> Dict[str, Any]:
        return {
            "module_name": cls.SPEC["module_name"],
            "version": cls.SPEC["version"],
            "specification": cls.SPEC,
            "entry_point": EnhancedFractalNeuroeconomicCore,
            "dependencies": {
                "config": NeuroAdvancedConfig,
                "dpa": DopaminePredictionNetwork,
                "aic": AgencyControlNetwork,
                "nre": NeuroplasticReinforcementEngine,
            },
        }


__all__ = [
    "MultiscaleFractalAnalyzer",
    "CandidateGenerator",
    "NeuroRiskManager",
    "NeuroDecisionIntegrator",
    "EnhancedFractalNeuroeconomicCore",
    "IntegratedNeuroTradingSystem",
    "ECANeuroTradingAdapter",
    "MarketContext",
    "TradeOutcome",
    "TradeResult",
]
