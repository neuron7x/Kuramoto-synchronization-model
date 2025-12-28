"""Quantum Neural Strategy module for TradePulse.

This standalone module provides a ready-to-train deep learning strategy that
combines LSTM+Attention and Transformer blocks. The resulting fused
representation feeds two prediction heads: a regression target for next-day
close price, and a classification head for BUY/HOLD/SELL decisions. The module
also exposes a backtester and CLI entry-point that integrates with Polygon
market data or CSV files containing OHLCV series.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import RobustScaler
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader, Dataset

# ============================
# Data utilities
# ============================

REQUIRED_COLS = ["date", "open", "high", "low", "close", "volume"]


def _check_df(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}. Required: {REQUIRED_COLS}")
    df = df.copy()
    if not np.issubdtype(df["date"].dtype, np.datetime64):
        df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    return df


def fetch_polygon_ohlcv(
    ticker: str, days: int = 500, end: Optional[pd.Timestamp] = None
) -> pd.DataFrame:
    """Fetch OHLCV candles from Polygon's REST API."""

    api_key = os.getenv("POLYGON_API_KEY")
    if api_key is None:
        raise RuntimeError("POLYGON_API_KEY env var not set.")

    try:
        from polygon import RESTClient  # type: ignore
    except Exception as exc:  # pragma: no cover - requires optional dependency
        raise ImportError(
            "Install polygon-api-client: pip install polygon-api-client"
        ) from exc

    client = RESTClient(api_key)
    if end is None:
        end = pd.Timestamp.today().normalize()
    start = end - pd.Timedelta(days=days)

    aggs = client.get_aggs(
        ticker=ticker, multiplier=1, timespan="day", from_=start, to=end
    )
    rows = []
    for agg in aggs:
        ts = pd.to_datetime(agg.timestamp, unit="ms")
        rows.append(
            {
                "date": ts,
                "open": float(agg.open),
                "high": float(agg.high),
                "low": float(agg.low),
                "close": float(agg.close),
                "volume": float(agg.volume),
            }
        )
    df = pd.DataFrame(rows)
    return _check_df(df)


# ============================
# Dataset
# ============================


class AdvancedTradingDataset(Dataset):
    """Sequence dataset returning (window, y_price, y_action).

    ``y_price`` is the next close price for regression.
    ``y_action`` encodes BUY/HOLD/SELL decisions derived from next-day returns.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        sequence_length: int = 30,
        augment: bool = True,
        buy_thr: float = 0.005,
        sell_thr: float = -0.005,
    ) -> None:
        if sequence_length <= 0:
            raise ValueError("sequence_length must be positive")

        self.seq_len = int(sequence_length)

        feats = df[["open", "high", "low", "close", "volume"]].values.astype(np.float32)
        self.scalers: Dict[str, RobustScaler] = {}
        scaled = []
        for idx, name in enumerate(["open", "high", "low", "close", "volume"]):
            scaler = RobustScaler()
            col = feats[:, [idx]]
            scaled.append(scaler.fit_transform(col))
            self.scalers[name] = scaler
        self.X = np.hstack(scaled).astype(np.float32)

        self.dates = df["date"].to_numpy()
        closes = df["close"].to_numpy().astype(np.float32)
        future_close = np.roll(closes, -1)
        self.y_price = future_close

        ret = (future_close - closes) / np.clip(closes, 1e-6, None)
        labels = np.zeros_like(ret, dtype=np.int64)
        labels[ret > buy_thr] = 1
        labels[ret < sell_thr] = 2
        self.y_action = labels
        self.augment = augment

        cut = len(self.X) - 1
        if cut <= 0:
            raise ValueError("dataset must contain at least two rows")

        self.X = self.X[:cut]
        self.y_price = self.y_price[:cut]
        self.y_action = self.y_action[:cut]
        self.dates = self.dates[:cut]

        self._length = int(cut - self.seq_len + 1)
        if self._length <= 0:
            raise ValueError(
                "sequence_length requires at least one future observation. "
                f"Got sequence_length={self.seq_len} with only {len(df)} rows."
            )

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, idx: int):
        if isinstance(idx, np.integer):
            idx = int(idx)
        elif not isinstance(idx, int):
            raise TypeError("index must be an integer")

        if idx < 0:
            idx += self._length
        if idx < 0 or idx >= self._length:
            raise IndexError(
                f"index {idx} out of range for dataset of length {self._length}"
            )

        seq = self.X[idx : idx + self.seq_len].copy()
        target_idx = idx + self.seq_len - 1
        y_price = self.y_price[target_idx]
        y_action = self.y_action[target_idx]

        if self.augment and np.random.rand() > 0.7:
            noise = np.random.normal(0, 0.01, seq.shape).astype(np.float32)
            seq += noise

        return (
            torch.tensor(seq, dtype=torch.float32),
            torch.tensor([y_price], dtype=torch.float32),
            torch.tensor(y_action, dtype=torch.long),
        )


# ============================
# Model
# ============================


class EnhancedTemporalLSTM(nn.Module):
    def __init__(
        self, input_size: int = 5, hidden_size: int = 128, num_layers: int = 3
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size,
            hidden_size,
            num_layers,
            batch_first=True,
            dropout=0.3,
            bidirectional=True,
        )
        self.attn = nn.MultiheadAttention(hidden_size * 2, 4, batch_first=True)
        self.norm = nn.LayerNorm(hidden_size * 2)
        self.drop = nn.Dropout(0.4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        attn_out, _ = self.attn(out, out, out)
        out = self.norm(out + attn_out)
        return self.drop(out[:, -1, :])


class AdaptiveFundamentalTransformer(nn.Module):
    def __init__(self, feature_size: int = 20, d_model: int = 64, nhead: int = 8):
        super().__init__()
        self.input_proj = nn.Linear(feature_size, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=128,
            batch_first=True,
            dropout=0.2,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=3)

    def forward(self, x_stats: torch.Tensor) -> torch.Tensor:
        if x_stats.dim() == 2:
            x_stats = x_stats.unsqueeze(1)
        z = self.input_proj(x_stats.mean(dim=1))
        z = self.encoder(z.unsqueeze(1)).squeeze(1)
        return z


class CrossDomainFusion(nn.Module):
    def __init__(
        self, temporal_dim: int = 256, fundamental_dim: int = 64, out_dim: int = 128
    ):
        super().__init__()
        self.t_proj = nn.Linear(temporal_dim, out_dim)
        self.f_proj = nn.Linear(fundamental_dim, out_dim)
        self.gate = nn.Sequential(nn.Linear(out_dim * 2, out_dim), nn.Sigmoid())
        self.res = nn.Linear(out_dim, out_dim)

    def forward(self, t: torch.Tensor, f: torch.Tensor) -> torch.Tensor:
        tp = self.t_proj(t)
        fp = self.f_proj(f)
        gate = self.gate(torch.cat([tp, fp], dim=-1))
        fused = gate * tp + (1 - gate) * fp
        return self.res(fused) + fused


class DecisionHeads(nn.Module):
    def __init__(self, in_dim: int = 128):
        super().__init__()
        self.reg = nn.Sequential(
            nn.Linear(in_dim, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1)
        )
        self.cls = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.LeakyReLU(0.1),
            nn.Dropout(0.3),
            nn.Linear(64, 3),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        price = self.reg(x)
        logits = self.cls(x)
        return price, logits


class QuantumNeuralModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.temporal = EnhancedTemporalLSTM()
        self.fundamental = AdaptiveFundamentalTransformer()
        self.fusion = CrossDomainFusion()
        self.heads = DecisionHeads()

    @staticmethod
    def _window_stats(x: torch.Tensor) -> torch.Tensor:
        mean = x.mean(dim=1, keepdim=True)
        std = x.std(dim=1, keepdim=True)
        mx = x.max(dim=1, keepdim=True)[0]
        mn = x.min(dim=1, keepdim=True)[0]
        return torch.cat([mean, std, mx, mn], dim=-1)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        temporal = self.temporal(x)
        stats = self._window_stats(x)
        fundamental = self.fundamental(stats)
        fused = self.fusion(temporal, fundamental)
        price, logits = self.heads(fused)
        return price, logits


# ============================
# Strategy wrapper
# ============================


@dataclass(slots=True)
class TrainConfig:
    epochs: int = 8
    seq_len: int = 30
    batch_size: int = 32
    lr_temporal: float = 1e-3
    lr_other: float = 5e-4
    wd: float = 1e-4
    cls_weight: float = 0.4
    device: str = "cuda" if torch.cuda.is_available() else "cpu"
    amp: bool = True


@dataclass(slots=True)
class EpochMetrics:
    """Container for epoch level metrics."""

    loss: float
    price_mae: float
    action_acc: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "loss": self.loss,
            "price_mae": self.price_mae,
            "action_acc": self.action_acc,
        }


class QuantumNeuralStrategy:
    """Drop-in strategy with fit/predict/backtest interface."""

    def __init__(self, cfg: TrainConfig = TrainConfig()) -> None:
        self.cfg = cfg
        self.device = torch.device(cfg.device)
        self.model = QuantumNeuralModel().to(self.device)
        params = [
            {"params": self.model.temporal.parameters(), "lr": cfg.lr_temporal},
            {
                "params": list(self.model.fundamental.parameters())
                + list(self.model.fusion.parameters())
                + list(self.model.heads.parameters()),
                "lr": cfg.lr_other,
            },
        ]
        self.opt = torch.optim.AdamW(params, weight_decay=cfg.wd)
        self.sched = ReduceLROnPlateau(self.opt, patience=4, factor=0.5)
        self.reg_loss = nn.HuberLoss()
        self.cls_loss = nn.CrossEntropyLoss()
        self.scalers: Optional[Dict[str, RobustScaler]] = None
        self._use_amp = self.device.type == "cuda" and cfg.amp
        self._scaler = torch.cuda.amp.GradScaler(enabled=self._use_amp)
        self._amp_ctx = lambda: (
            torch.autocast(device_type=self.device.type, dtype=torch.float16)
            if self._use_amp
            else nullcontext
        )
        self.history: List[Dict[str, float]] = []

    def fit(self, df: pd.DataFrame) -> None:
        df = _check_df(df)
        dataset = AdvancedTradingDataset(
            df, sequence_length=self.cfg.seq_len, augment=True
        )
        self.scalers = dataset.scalers

        split = int(len(dataset) * 0.8)
        idxs = np.arange(len(dataset))
        train_idx, val_idx = idxs[:split], idxs[split:]

        train_ds = torch.utils.data.Subset(dataset, train_idx)
        val_ds = torch.utils.data.Subset(dataset, val_idx)
        train_dl = DataLoader(
            train_ds, batch_size=self.cfg.batch_size, shuffle=True, drop_last=True
        )
        val_dl = DataLoader(
            val_ds, batch_size=self.cfg.batch_size, shuffle=False, drop_last=False
        )

        best_val = float("inf")
        patience = 8
        bad_epochs = 0
        for epoch in range(self.cfg.epochs):
            train_metrics = self._train_epoch(train_dl)
            val_metrics = self._validate(val_dl)
            self.sched.step(val_metrics.loss)
            self.history.append(
                {
                    "epoch": float(epoch),
                    "train_loss": train_metrics.loss,
                    "train_mae": train_metrics.price_mae,
                    "train_acc": train_metrics.action_acc,
                    "val_loss": val_metrics.loss,
                    "val_mae": val_metrics.price_mae,
                    "val_acc": val_metrics.action_acc,
                }
            )
            print(
                (
                    "[Epoch {epoch:02d}] "
                    "train_loss={train_loss:.6f} val_loss={val_loss:.6f} "
                    "train_mae={train_mae:.6f} val_mae={val_mae:.6f} "
                    "train_acc={train_acc:.4f} val_acc={val_acc:.4f}"
                ).format(
                    epoch=epoch,
                    train_loss=train_metrics.loss,
                    val_loss=val_metrics.loss,
                    train_mae=train_metrics.price_mae,
                    val_mae=val_metrics.price_mae,
                    train_acc=train_metrics.action_acc,
                    val_acc=val_metrics.action_acc,
                )
            )
            if val_metrics.loss < best_val:
                best_val = val_metrics.loss
                bad_epochs = 0
                self._save("artifacts/quantum_neural/best_model.pt")
            else:
                bad_epochs += 1
                if bad_epochs >= patience:
                    print("Early stopping")
                    break

    def _train_epoch(self, dl: DataLoader) -> EpochMetrics:
        self.model.train()
        total_loss = 0.0
        total_mae = 0.0
        total_correct = 0.0
        total_samples = 0
        for features, target_price, target_action in dl:
            features = features.to(self.device)
            target_price = target_price.to(self.device)
            target_action = target_action.to(self.device)

            self.opt.zero_grad(set_to_none=True)
            with self._amp_ctx():
                pred_price, logits = self.model(features)
                loss = self.reg_loss(
                    pred_price, target_price
                ) + self.cfg.cls_weight * self.cls_loss(logits, target_action)

            if self._use_amp:
                self._scaler.scale(loss).backward()
                self._scaler.unscale_(self.opt)
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self._scaler.step(self.opt)
                self._scaler.update()
            else:
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.opt.step()

            batch_size = features.size(0)
            total_loss += float(loss.detach().cpu()) * batch_size
            mae = torch.mean(torch.abs(pred_price - target_price)).detach().cpu().item()
            total_mae += mae * batch_size
            preds = torch.argmax(logits, dim=-1)
            correct = (preds == target_action).sum().detach().cpu().item()
            total_correct += correct
            total_samples += batch_size

        denom = max(1, total_samples)
        return EpochMetrics(
            loss=total_loss / denom,
            price_mae=total_mae / denom,
            action_acc=total_correct / denom,
        )

    @torch.no_grad()
    def _validate(self, dl: DataLoader) -> EpochMetrics:
        self.model.eval()
        total_loss = 0.0
        total_mae = 0.0
        total_correct = 0.0
        total_samples = 0
        for features, target_price, target_action in dl:
            features = features.to(self.device)
            target_price = target_price.to(self.device)
            target_action = target_action.to(self.device)
            pred_price, logits = self.model(features)
            loss = self.reg_loss(
                pred_price, target_price
            ) + self.cfg.cls_weight * self.cls_loss(logits, target_action)
            batch_size = features.size(0)
            total_loss += float(loss.detach().cpu()) * batch_size
            mae = torch.mean(torch.abs(pred_price - target_price)).detach().cpu().item()
            total_mae += mae * batch_size
            preds = torch.argmax(logits, dim=-1)
            correct = (preds == target_action).sum().detach().cpu().item()
            total_correct += correct
            total_samples += batch_size

        denom = max(1, total_samples)
        return EpochMetrics(
            loss=total_loss / denom,
            price_mae=total_mae / denom,
            action_acc=total_correct / denom,
        )

    @torch.inference_mode()
    def predict_window(self, df_window: pd.DataFrame) -> Dict[str, np.ndarray]:
        if self.scalers is None:
            raise RuntimeError("Call fit() before predict_window().")
        df_window = _check_df(df_window)
        if len(df_window) < self.cfg.seq_len:
            return {
                "actions": np.array([0.34, 0.33, 0.33]),
                "confidence": 0.0,
                "price_pred": float(df_window.iloc[-1]["close"]),
            }

        feats = df_window[["open", "high", "low", "close", "volume"]].values.astype(
            np.float32
        )
        cols = ["open", "high", "low", "close", "volume"]
        xs = []
        for idx, name in enumerate(cols):
            xs.append(self.scalers[name].transform(feats[:, [idx]]))
        X = np.hstack(xs).astype(np.float32)
        tensor = (
            torch.tensor(X[-self.cfg.seq_len :], dtype=torch.float32)
            .unsqueeze(0)
            .to(self.device)
        )

        self.model.eval()
        price, logits = self.model(tensor)
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
        confidence = float(probs.max())
        price_pred = float(price.cpu().numpy()[0, 0])
        return {"actions": probs, "confidence": confidence, "price_pred": price_pred}

    def _save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save(
            {
                "model": self.model.state_dict(),
                "cfg": self.cfg.__dict__,
                "history": self.history,
            },
            path,
        )

    def load(self, path: str) -> None:
        caller_device = torch.device(self.device)
        ckpt = torch.load(path, map_location=caller_device, weights_only=True)
        target_device = caller_device
        cfg_payload = ckpt.get("cfg")
        if cfg_payload is not None:
            self.cfg = TrainConfig(**cfg_payload)
            if target_device.type == "cuda" and not torch.cuda.is_available():
                target_device = torch.device("cpu")
            self.cfg.device = target_device.type
        if target_device.type == "cuda" and not torch.cuda.is_available():
            target_device = torch.device("cpu")
            self.cfg.device = target_device.type
        self.device = target_device
        self.model.to(self.device)
        self._use_amp = self.device.type == "cuda" and self.cfg.amp
        self._scaler = torch.cuda.amp.GradScaler(enabled=self._use_amp)
        self._amp_ctx = lambda: (
            torch.autocast(device_type=self.device.type, dtype=torch.float16)
            if self._use_amp
            else nullcontext
        )
        self.model.load_state_dict(ckpt["model"])
        self.history = ckpt.get("history", [])

    def export_history(self) -> List[Dict[str, float]]:
        """Return a copy of the collected training history."""

        return list(self.history)


# ============================
# Risk management & backtest
# ============================


@dataclass(slots=True)
class RiskConfig:
    initial_balance: float = 100_000.0
    max_position_fraction: float = 0.10
    base_risk_fraction: float = 0.02
    stop_base: float = 0.03


class QuantumRiskManager:
    def __init__(self, cfg: RiskConfig = RiskConfig()) -> None:
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        self.balance = self.cfg.initial_balance
        self.position = 0.0
        self.entry = 0.0
        self.trades: List[Dict] = []

    def position_size(self, price: float, confidence: float, daily_vol: float) -> float:
        base = self.balance * self.cfg.base_risk_fraction
        adj = 1.0 / (1.0 + 2.0 * daily_vol)
        boost = min(2.0, 1.0 + 2.5 * confidence)
        size = base * adj * boost
        return min(size, self.balance * self.cfg.max_position_fraction)

    def stop_loss_pct(self, daily_vol: float) -> float:
        return min(0.20, self.cfg.stop_base * (1.0 + daily_vol))


def backtest(df: pd.DataFrame, strat: QuantumNeuralStrategy) -> Dict[str, float]:
    df = _check_df(df)
    rm = QuantumRiskManager()
    rm.reset()

    portfolio_values: List[float] = []

    for idx in range(strat.cfg.seq_len, len(df) - 1):
        window = df.iloc[idx - strat.cfg.seq_len : idx + 1]
        pred = strat.predict_window(window)
        price = float(df.iloc[idx]["close"])
        next_price = float(df.iloc[idx + 1]["close"])
        probs = pred["actions"]
        action = int(np.argmax(probs))
        confidence = float(pred["confidence"])

        vol = float(df.iloc[max(1, idx - 30) : idx + 1]["close"].pct_change().std())
        vol = 0.0 if math.isnan(vol) else vol

        if action == 1 and rm.position == 0.0:
            size = rm.position_size(price, confidence, vol)
            if size > 0 and rm.balance >= size:
                rm.position = size / price
                rm.entry = price
                rm.balance -= size
                rm.trades.append(
                    {
                        "ts": df.iloc[idx]["date"],
                        "side": "BUY",
                        "price": price,
                        "size": size,
                    }
                )
        elif action == 2 and rm.position > 0.0:
            sell_val = rm.position * price
            pnl = (price - rm.entry) / max(1e-6, rm.entry)
            rm.balance += sell_val
            rm.trades.append(
                {"ts": df.iloc[idx]["date"], "side": "SELL", "price": price, "pnl": pnl}
            )
            rm.position = 0.0
            rm.entry = 0.0

        if rm.position > 0.0:
            stop_pct = rm.stop_loss_pct(vol)
            if next_price < rm.entry * (1 - stop_pct):
                sell_val = rm.position * next_price
                pnl = (next_price - rm.entry) / max(1e-6, rm.entry)
                rm.balance += sell_val
                rm.trades.append(
                    {
                        "ts": df.iloc[idx + 1]["date"],
                        "side": "STOP",
                        "price": next_price,
                        "pnl": pnl,
                    }
                )
                rm.position = 0.0
                rm.entry = 0.0

        portfolio_value = rm.balance + (
            rm.position * price if rm.position > 0.0 else 0.0
        )
        portfolio_values.append(portfolio_value)

    return _analyze_performance(portfolio_values, rm.trades)


def _analyze_performance(pvs: List[float], trades: List[Dict]) -> Dict[str, float]:
    if not pvs:
        return {"error": 1.0}
    arr = np.array(pvs, dtype=np.float64)
    rets = np.diff(arr) / arr[:-1]
    tot_ret = float((arr[-1] - arr[0]) / arr[0])
    sharpe = (
        float(np.mean(rets) / (np.std(rets) + 1e-9) * math.sqrt(252))
        if len(rets) > 2
        else 0.0
    )
    downside = rets[rets < 0]
    sortino = (
        float(np.mean(rets) / (np.std(downside) + 1e-9) * math.sqrt(252))
        if downside.size
        else 0.0
    )

    peak = np.maximum.accumulate(arr)
    drawdown = (arr - peak) / peak
    mdd = float(drawdown.min())

    wins = [trade for trade in trades if float(trade.get("pnl", 0.0)) > 0]
    win_rate = float(len(wins) / len(trades)) if trades else 0.0

    avg_profit = (
        float(np.mean([trade.get("pnl", 0.0) for trade in trades])) if trades else 0.0
    )
    losses = [
        abs(trade.get("pnl", 0.0)) for trade in trades if trade.get("pnl", 0.0) < 0
    ]
    profits = [trade.get("pnl", 0.0) for trade in trades if trade.get("pnl", 0.0) > 0]
    profit_factor = float(
        (sum(profits) / (sum(losses) + 1e-9)) if losses else float("inf")
    )

    calmar = float((tot_ret / abs(mdd)) if mdd != 0 else 0.0)

    return {
        "total_return": tot_ret,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "avg_profit_per_trade": avg_profit,
        "profit_factor": profit_factor,
        "total_trades": float(len(trades)),
        "final_balance": float(arr[-1]),
        "calmar_ratio": calmar,
    }


# ============================
# Public integration helpers
# ============================


def get_strategy(config: Optional[Dict] = None) -> QuantumNeuralStrategy:
    cfg = TrainConfig(**(config or {}))
    return QuantumNeuralStrategy(cfg)


# ============================
# CLI
# ============================


def _ensure_artifacts() -> None:
    os.makedirs("artifacts/quantum_neural", exist_ok=True)


def _load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "timestamp" in df.columns and "date" not in df.columns:
        df = df.rename(columns={"timestamp": "date"})
    return _check_df(df)


def _maybe_fetch_data(args: argparse.Namespace) -> pd.DataFrame:
    if args.csv:
        return _load_csv(args.csv)
    if args.ticker:
        return fetch_polygon_ohlcv(args.ticker, days=args.days)
    raise SystemExit("Provide --csv or --ticker.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quantum Neural Strategy for TradePulse"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--csv", type=str, help="Path to OHLCV CSV (date,open,high,low,close,volume)"
    )
    group.add_argument("--ticker", type=str, help="Polygon ticker e.g. X:BTCUSD")
    parser.add_argument("--days", type=int, default=500, help="Days for Polygon fetch")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--seq-len", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--save", action="store_true", help="Save best model + signals")
    args = parser.parse_args()

    _ensure_artifacts()
    df = _maybe_fetch_data(args)

    strategy = QuantumNeuralStrategy(
        TrainConfig(
            epochs=args.epochs, seq_len=args.seq_len, batch_size=args.batch_size
        )
    )
    print("\n[Train] starting...")
    strategy.fit(df)

    print("\n[Backtest]")
    metrics = backtest(df, strategy)
    print(json.dumps(metrics, indent=2, default=float))

    if args.save:
        signals: List[Dict] = []
        for idx in range(strategy.cfg.seq_len, len(df)):
            window = df.iloc[idx - strategy.cfg.seq_len : idx + 1]
            pred = strategy.predict_window(window)
            signals.append(
                {
                    "date": window.iloc[-1]["date"],
                    "price_pred": pred["price_pred"],
                    "buy_prob": float(pred["actions"][1]),
                    "sell_prob": float(pred["actions"][2]),
                    "hold_prob": float(pred["actions"][0]),
                    "confidence": pred["confidence"],
                }
            )
        sig_df = pd.DataFrame(signals)
        sig_df.to_csv("artifacts/quantum_neural/signals.csv", index=False)
        print("Saved artifacts to artifacts/quantum_neural/")


if __name__ == "__main__":
    main()
