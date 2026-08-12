# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utility helpers for GeoSyncHydro Unified System v2."""

from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import torch
from sklearn.preprocessing import StandardScaler


def setup_logging(log_dir: str, log_file: str) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
    )
    logging.info("Logging initialized at %s", log_path)


def save_checkpoint(
    save_dir: str,
    name: str,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: torch.optim.lr_scheduler._LRScheduler | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    os.makedirs(save_dir, exist_ok=True)
    obj: dict[str, Any] = {"model": model.state_dict()}
    if optimizer:
        obj["optimizer"] = optimizer.state_dict()
    if scheduler:
        obj["scheduler"] = scheduler.state_dict()  # type: ignore[no-untyped-call]
    if extra:
        obj["extra"] = extra
    path = os.path.join(save_dir, name)
    torch.save(obj, path)
    logging.info("Checkpoint saved: %s", path)
    return path


def load_checkpoint(
    path: str,
    model: torch.nn.Module | None = None,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler: torch.optim.lr_scheduler._LRScheduler | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=True)
    if model:
        model.load_state_dict(obj["model"], strict=False)
    if optimizer and "optimizer" in obj:
        optimizer.load_state_dict(obj["optimizer"])
    if scheduler and "scheduler" in obj:
        scheduler.load_state_dict(obj["scheduler"])
    return obj


class DataImputer:
    def impute(self, arr: np.ndarray) -> np.ndarray:
        if arr is None or arr.size == 0:
            return arr
        arr = np.array(arr, dtype=float)
        for j in range(arr.shape[1]):
            col = arr[:, j]
            if np.isnan(col).any():
                med = np.nanmedian(col)
                col[np.isnan(col)] = med
                arr[:, j] = col
        return arr


class AnomalyDetector:
    def zscore(self, arr: np.ndarray) -> float:
        if arr is None or arr.size == 0:
            return 0.0
        arr = np.array(arr, dtype=float)
        z = np.abs((arr - np.nanmean(arr, axis=0)) / (np.nanstd(arr, axis=0) + 1e-8))
        return float(np.nanmax(z)) if not np.isnan(z).all() else 0.0


def preprocess_window(raw_window: np.ndarray) -> torch.Tensor:
    T, S, F = raw_window.shape
    X = raw_window.reshape(T * S, F)
    X = StandardScaler().fit_transform(X)
    X = X.reshape(1, T, S, F)
    return torch.tensor(X, dtype=torch.float32)
