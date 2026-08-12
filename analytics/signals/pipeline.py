# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signal feature pipelines and walk-forward model selection utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Iterator, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest.time_splits import WalkForwardSplitter
from core.metrics import regression as regression_metrics
from core.strategies.objectives import sharpe_ratio


@dataclass(slots=True)
class FeaturePipelineConfig:
    """Configuration for the :class:`SignalFeaturePipeline`."""

    price_col: str = "close"
    high_col: str = "high"
    low_col: str = "low"
    volume_col: str = "volume"
    bid_col: str = "bid_volume"
    ask_col: str = "ask_volume"
    signed_volume_col: str = "signed_volume"
    technical_windows: Sequence[int] = (5, 20, 60)
    rsi_window: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    volatility_window: int = 20
    microstructure_window: int = 50


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def _rsi(series: pd.Series, window: int) -> pd.Series:
    diff = series.diff()
    gain = diff.clip(lower=0.0)
    loss = -diff.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _rolling_microstructure(
    returns: pd.Series,
    signed_volume: pd.Series,
    window: int,
    func: Callable[[np.ndarray, np.ndarray], float],
) -> pd.Series:
    if window <= 1:
        return pd.Series(np.nan, index=returns.index)
    values = np.column_stack((returns.to_numpy(), signed_volume.to_numpy()))
    result = np.full(len(values), np.nan, dtype=float)
    for idx in range(window - 1, len(values)):
        window_slice = values[idx - window + 1 : idx + 1]
        r = window_slice[:, 0]
        q = window_slice[:, 1]
        if np.isnan(r).all() or np.isnan(q).all():
            continue
        mask = np.isfinite(r) & np.isfinite(q)
        if not np.any(mask):
            continue
        result[idx] = func(r[mask], q[mask])
    return pd.Series(result, index=returns.index)


def _kyles_lambda_window(returns: np.ndarray, signed_volume: np.ndarray) -> float:
    if returns.size == 0 or signed_volume.size == 0:
        return np.nan
    q = signed_volume - np.mean(signed_volume)
    r = returns - np.mean(returns)
    denom = np.dot(q, q)
    if denom <= 0.0:
        return 0.0
    return float(np.dot(q, r) / denom)


def _hasbrouck_window(returns: np.ndarray, signed_volume: np.ndarray) -> float:
    if returns.size == 0 or signed_volume.size == 0:
        return np.nan
    transformed = np.sign(signed_volume) * np.sqrt(np.abs(signed_volume))
    transformed = transformed - np.mean(transformed)
    r = returns - np.mean(returns)
    denom = np.dot(transformed, transformed)
    if denom <= 0.0:
        return 0.0
    return float(np.dot(transformed, r) / denom)


class SignalFeaturePipeline:
    """Build technical analysis and microstructure features for signals."""

    def __init__(self, config: FeaturePipelineConfig) -> None:
        self.config = config

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config
        clean_frame = self._sanitize_frame(frame)
        if clean_frame.empty:
            return pd.DataFrame(index=clean_frame.index)

        price = clean_frame[cfg.price_col].astype(float)
        high = clean_frame.get(cfg.high_col, price)
        low = clean_frame.get(cfg.low_col, price)
        volume = clean_frame.get(cfg.volume_col)
        bid_volume = clean_frame.get(cfg.bid_col)
        ask_volume = clean_frame.get(cfg.ask_col)
        signed_volume = clean_frame.get(cfg.signed_volume_col)

        features = pd.DataFrame(index=clean_frame.index)
        returns = price.pct_change()
        features["return_1"] = returns

        for window in cfg.technical_windows:
            rolling = price.rolling(window=window, min_periods=window)
            features[f"sma_{window}"] = rolling.mean()
            features[f"volatility_{window}"] = returns.rolling(
                window=window, min_periods=window
            ).std()
            features[f"ema_{window}"] = price.ewm(
                span=window, adjust=False, min_periods=window
            ).mean()

        features["rsi"] = _rsi(price, cfg.rsi_window)
        fast_ema = price.ewm(span=cfg.macd_fast, adjust=False, min_periods=1).mean()
        slow_ema = price.ewm(span=cfg.macd_slow, adjust=False, min_periods=1).mean()
        features["macd_ema_fast"] = fast_ema
        features["macd_ema_slow"] = slow_ema
        features["macd"] = fast_ema - slow_ema
        features["macd_signal"] = (
            features["macd"].ewm(span=cfg.macd_signal, adjust=False, min_periods=1).mean()
        )
        features["macd_histogram"] = features["macd"] - features["macd_signal"]
        features["price_range"] = (high - low).astype(float)

        if volume is not None:
            volume = volume.astype(float)
            features["log_volume"] = np.log(volume.replace(0.0, np.nan))
            rolling_mean = volume.rolling(
                window=cfg.volatility_window, min_periods=cfg.volatility_window
            ).mean()
            rolling_std = volume.rolling(
                window=cfg.volatility_window, min_periods=cfg.volatility_window
            ).std()
            rolling_std_safe = rolling_std.mask(rolling_std == 0.0, np.nan)
            volume_z = (volume - rolling_mean) / rolling_std_safe
            zero_std_mask = rolling_std == 0.0
            volume_z = volume_z.mask(zero_std_mask, 0.0)
            features["volume_z"] = volume_z

        if bid_volume is not None and ask_volume is not None:
            bid = bid_volume.astype(float)
            ask = ask_volume.astype(float)
            denom = bid + ask
            queue_imbalance = np.where(denom == 0.0, 0.0, (bid - ask) / denom)
            features["queue_imbalance"] = queue_imbalance

        if signed_volume is not None:
            signed_volume = signed_volume.astype(float)
            window = cfg.microstructure_window
            features[f"kyles_lambda_{window}"] = _rolling_microstructure(
                returns, signed_volume, window, _kyles_lambda_window
            )
            features[f"hasbrouck_{window}"] = _rolling_microstructure(
                returns, signed_volume, window, _hasbrouck_window
            )
            features["signed_volume_ema"] = signed_volume.ewm(
                span=window, adjust=False, min_periods=window
            ).mean()

        return features

    def _sanitize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config
        _require_columns(frame, [cfg.price_col])
        if frame.empty:
            return frame.copy()

        working = frame.copy()
        working = working.sort_index()

        price = pd.to_numeric(working[cfg.price_col], errors="coerce")
        price = price.replace([np.inf, -np.inf], np.nan)
        valid_price = price.notna() & np.isfinite(price) & (price > 0)
        working = working.loc[valid_price].copy()
        price = price.loc[valid_price]

        if not working.empty:
            dedupe_mask = ~working.index.duplicated(keep="last")
            if not dedupe_mask.all():
                working = working.loc[dedupe_mask].copy()
                price = price.loc[dedupe_mask]

        working.loc[:, cfg.price_col] = price.astype(float)

        optional_numeric = {
            cfg.high_col,
            cfg.low_col,
            cfg.volume_col,
            cfg.bid_col,
            cfg.ask_col,
            cfg.signed_volume_col,
        }
        for column in optional_numeric:
            if column in working.columns:
                numeric = pd.to_numeric(working[column], errors="coerce")
                numeric = numeric.replace([np.inf, -np.inf], np.nan)
                working.loc[:, column] = numeric.astype(float)

        return working


@dataclass(slots=True)
class LeakageGate:
    """Enforce look-ahead leakage rules for feature matrices."""

    lag: int = 0
    dropna: bool = True

    def apply(self, features: pd.DataFrame, target: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
        aligned_features = features.shift(self.lag) if self.lag else features.copy()
        combined = aligned_features.join(target.rename("__target__"), how="inner")
        combined.replace([np.inf, -np.inf], np.nan, inplace=True)
        if self.dropna:
            combined.dropna(inplace=True)
        target_series = combined.pop("__target__")
        return combined, target_series


@dataclass(slots=True)
class ModelCandidate:
    """Container describing a model option for selection."""

    name: str
    factory: Callable[[], "RegressorLike"]


class RegressorLike:
    """Minimal protocol for regression estimators."""

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RegressorLike":  # pragma: no cover - protocol
        raise NotImplementedError

    def predict(self, X: np.ndarray) -> np.ndarray:  # pragma: no cover - protocol
        raise NotImplementedError


class _OLSRegressor(RegressorLike):
    """Simple Ordinary Least Squares fallback when sklearn is unavailable."""

    def __init__(self, l2: float = 1e-6) -> None:
        self._coef: np.ndarray | None = None
        self._intercept: float = 0.0
        self._l2 = float(l2)

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_OLSRegressor":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2:
            raise ValueError("X must be two-dimensional")
        X_aug = np.hstack([X, np.ones((X.shape[0], 1))])
        reg = self._l2 * np.eye(X_aug.shape[1])
        reg[-1, -1] = 0.0
        beta = np.linalg.pinv(X_aug.T @ X_aug + reg) @ X_aug.T @ y
        self._coef = beta[:-1]
        self._intercept = beta[-1]
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._coef is None:
            raise RuntimeError("Model has not been fitted")
        X = np.asarray(X, dtype=float)
        return X @ self._coef + self._intercept


def make_default_candidates() -> list[ModelCandidate]:
    """Return default model candidates with graceful optional imports."""

    candidates: list[ModelCandidate] = [ModelCandidate("ols", lambda: _OLSRegressor())]

    try:  # pragma: no cover - optional dependency
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model import Ridge

        candidates.append(ModelCandidate("ridge", lambda: Ridge(alpha=1.0)))
        candidates.append(
            ModelCandidate(
                "random_forest",
                lambda: RandomForestRegressor(n_estimators=200, max_depth=6, random_state=42),
            )
        )
    except Exception:  # pragma: no cover - handled gracefully
        pass

    try:  # pragma: no cover - optional dependency
        import lightgbm as lgb

        candidates.append(
            ModelCandidate(
                "lightgbm",
                lambda: lgb.LGBMRegressor(
                    n_estimators=400,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                ),
            )
        )
    except Exception:  # pragma: no cover
        pass

    try:  # pragma: no cover - optional dependency
        import xgboost as xgb

        candidates.append(
            ModelCandidate(
                "xgboost",
                lambda: xgb.XGBRegressor(
                    n_estimators=400,
                    learning_rate=0.05,
                    max_depth=5,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    objective="reg:squarederror",
                ),
            )
        )
    except Exception:  # pragma: no cover
        pass

    return candidates


@dataclass(slots=True)
class SplitPerformance:
    """Per-split evaluation snapshot."""

    split: int
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    metrics: Mapping[str, float]
    regression: Mapping[str, float]


@dataclass(slots=True)
class SignalModelEvaluation:
    """Aggregated evaluation report for a model candidate."""

    name: str
    aggregate_metrics: Mapping[str, float]
    split_details: Sequence[SplitPerformance]
    regression_report: pd.DataFrame

    def best_metric(self, key: str) -> float:
        return float(self.aggregate_metrics.get(key, float("nan")))


def _hit_rate(predictions: np.ndarray, realised: np.ndarray) -> float:
    sign_pred = np.sign(predictions)
    sign_real = np.sign(realised)
    mask = sign_pred != 0
    if not np.any(mask):
        return 0.0
    hits = sign_pred[mask] == sign_real[mask]
    return float(np.mean(hits))


def _sortino_ratio(returns: np.ndarray, risk_free: float = 0.0) -> float:
    excess = returns - risk_free
    downside = excess[excess < 0.0]
    downside_std = np.sqrt(np.mean(np.square(downside))) if downside.size else 0.0
    if downside_std == 0.0:
        return 0.0
    return float(np.mean(excess) / downside_std)


def _pnl_attribution(strategy_returns: np.ndarray, positions: np.ndarray) -> dict[str, float]:
    total = float(np.sum(strategy_returns))
    long_mask = positions > 0
    short_mask = positions < 0
    long_contrib = float(np.sum(strategy_returns[long_mask])) if np.any(long_mask) else 0.0
    short_contrib = float(np.sum(strategy_returns[short_mask])) if np.any(short_mask) else 0.0
    gross = float(np.sum(np.abs(strategy_returns)))
    return {
        "total_pnl": total,
        "long_contribution": long_contrib,
        "short_contribution": short_contrib,
        "gross_exposure": gross,
    }


def _performance_budget(strategy_returns: np.ndarray, positions: np.ndarray) -> dict[str, float]:
    exposure = np.abs(positions)
    active = exposure > 0
    if not np.any(active):
        return {"active_fraction": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    wins = strategy_returns[active & (strategy_returns > 0)]
    losses = strategy_returns[active & (strategy_returns <= 0)]
    return {
        "active_fraction": float(np.mean(active)),
        "avg_win": float(np.mean(wins)) if wins.size else 0.0,
        "avg_loss": float(np.mean(losses)) if losses.size else 0.0,
    }


def _evaluate_predictions(
    pred: np.ndarray, realised: np.ndarray
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    positions = np.sign(pred)
    strategy_returns = positions * realised
    hit = _hit_rate(pred, realised)
    sharpe = sharpe_ratio(strategy_returns)
    sortino = _sortino_ratio(strategy_returns)
    pnl = _pnl_attribution(strategy_returns, positions)
    budget = _performance_budget(strategy_returns, positions)
    metrics = {
        "hit_rate": hit,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
    }
    metrics.update(pnl)
    metrics.update(budget)
    return metrics, pnl, budget


def build_supervised_learning_frame(
    frame: pd.DataFrame,
    *,
    config: FeaturePipelineConfig | None = None,
    gate: LeakageGate | None = None,
    horizon: int = 1,
) -> tuple[pd.DataFrame, pd.Series]:
    """Return features and forward return target ready for modelling."""

    cfg = config or FeaturePipelineConfig()
    pipeline = SignalFeaturePipeline(cfg)
    features = pipeline.transform(frame)
    price = frame[cfg.price_col].astype(float)
    target = price.pct_change(periods=horizon).shift(-horizon)
    target.name = f"forward_return_{horizon}"
    gate = gate or LeakageGate(lag=0, dropna=True)
    return gate.apply(features, target)


class SignalModelSelector:
    """Perform walk-forward evaluation across model candidates."""

    def __init__(
        self,
        splitter: WalkForwardSplitter,
        *,
        candidates: Sequence[ModelCandidate] | None = None,
    ) -> None:
        self.splitter = splitter
        self.candidates = list(candidates) if candidates is not None else make_default_candidates()

    def _iter_splits(self, data: pd.DataFrame) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        yield from self.splitter.split(data)

    def evaluate(self, features: pd.DataFrame, target: pd.Series) -> list[SignalModelEvaluation]:
        if not isinstance(features, pd.DataFrame):
            raise TypeError("features must be a pandas DataFrame")
        if not isinstance(target, pd.Series):
            raise TypeError("target must be a pandas Series")
        frame = features.copy()
        frame["__target__"] = target
        evaluations: list[SignalModelEvaluation] = []
        for candidate in self.candidates:
            split_details: list[SplitPerformance] = []
            regression_rows = []
            aggregate_store: dict[str, list[float]] = {}
            for split_idx, (train_idx, test_idx) in enumerate(self._iter_splits(frame)):
                train = frame.iloc[train_idx]
                test = frame.iloc[test_idx]
                train = train.replace([np.inf, -np.inf], np.nan).dropna()
                test = test.replace([np.inf, -np.inf], np.nan).dropna()
                if train.empty or test.empty:
                    continue
                X_train = train.drop(columns="__target__").to_numpy(dtype=float)
                y_train = train["__target__"].to_numpy(dtype=float)
                X_test = test.drop(columns="__target__").to_numpy(dtype=float)
                y_test = test["__target__"].to_numpy(dtype=float)
                if X_train.size == 0 or X_test.size == 0:
                    continue
                model = candidate.factory()
                model.fit(X_train, y_train)
                predictions = model.predict(X_test)
                metrics, pnl, _ = _evaluate_predictions(predictions, y_test)
                for key, value in metrics.items():
                    aggregate_store.setdefault(key, []).append(float(value))
                start = test.index.min()
                end = test.index.max()
                regression = {
                    "mae": regression_metrics.mean_absolute_error(y_test, predictions),
                    "mse": regression_metrics.mean_squared_error(y_test, predictions),
                    "rmse": regression_metrics.root_mean_squared_error(y_test, predictions),
                    "r2": regression_metrics.r2_score(y_test, predictions),
                }
                regression_rows.append({"split": split_idx, **regression})
                split_details.append(
                    SplitPerformance(
                        split=split_idx,
                        start=pd.to_datetime(start) if start is not None else None,
                        end=pd.to_datetime(end) if end is not None else None,
                        metrics=dict(metrics),
                        regression=dict(regression),
                    )
                )
            aggregate_metrics = {
                key: float(np.mean(values)) for key, values in aggregate_store.items() if values
            }
            regression_report = pd.DataFrame(regression_rows)
            evaluations.append(
                SignalModelEvaluation(
                    name=candidate.name,
                    aggregate_metrics=aggregate_metrics,
                    split_details=split_details,
                    regression_report=regression_report,
                )
            )
        return evaluations


__all__ = [
    "FeaturePipelineConfig",
    "LeakageGate",
    "ModelCandidate",
    "SignalFeaturePipeline",
    "SignalModelEvaluation",
    "SignalModelSelector",
    "SplitPerformance",
    "build_supervised_learning_frame",
    "make_default_candidates",
]
