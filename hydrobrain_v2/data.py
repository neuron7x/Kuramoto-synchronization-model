"""Synthetic dataset generation and loading utilities for HydroBrain."""

from __future__ import annotations

import os

import numpy as np
import torch


def generate_yangtze_npz(
    save_path: str,
    N: int = 256,
    T: int = 64,
    S: int = 8,
    F: int = 5,
    seed: int = 42,
) -> str:
    rng = np.random.default_rng(seed)
    base_flow = rng.normal(25000.0, 4000.0, size=(S,))
    time = np.linspace(0, 4 * np.pi, T)
    seasonal = 0.3 * np.sin(time) + 0.1 * np.sin(2 * time + np.pi / 4)

    X = np.zeros((N, T, S, F), dtype=np.float32)
    y_flood = rng.integers(0, 3, size=(N,), dtype=np.int64)
    y_hydro = np.zeros((N, 2), dtype=np.float32)
    y_qual = np.zeros((N, 5), dtype=np.float32)

    for n in range(N):
        rain = np.zeros(T, dtype=np.float32)
        for _ in range(rng.integers(2, 5)):
            st = rng.integers(0, T - 16)
            dur = rng.integers(8, 24)
            inten = rng.exponential(0.4)
            for i in range(dur):
                if st + i < T:
                    rain[st + i] += float(inten * np.exp(-i / 6.0))
        for s in range(S):
            flow = base_flow[s] * (1 + 0.2 * seasonal) + rain * 2000 * (1 + s * 0.05)
            level = 8.0 + (flow - 15000.0) / 2500.0 + rng.normal(0, 0.3, size=T)
            temp = (
                15
                + 8 * np.sin(2 * np.pi * np.arange(T) / 24)
                + rng.normal(0, 1, size=T)
            )
            turb = np.maximum(5, rain * 100 + rng.exponential(20, size=T))
            dissolved_oxygen = 8 - 0.1 * level + rng.normal(0, 0.2, size=T)
            X[n, :, s, 0] = np.maximum(0, level)
            X[n, :, s, 1] = np.maximum(0, flow)
            X[n, :, s, 2] = temp
            X[n, :, s, 3] = turb
            X[n, :, s, 4] = dissolved_oxygen
        last = X[n, -1].mean(axis=0)
        y_hydro[n, 0] = last[0]
        y_hydro[n, 1] = np.clip(last[1], 10000.0, 50000.0)
        y_qual[n] = np.array(
            [7.2, max(2.0, last[4]), min(500.0, last[3]), 3.0, 1.0], dtype=np.float32
        )

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    np.savez(save_path, X=X, y_flood=y_flood, y_hydro=y_hydro, y_qual=y_qual)
    return save_path


def load_npz_dataset(
    path: str | None, cfg: dict, synth_ok: bool = True, N: int | None = None
):
    if (not path or not os.path.exists(path)) and synth_ok:
        path = "data/sample_yangtze.npz"
        generate_yangtze_npz(
            path,
            N=N or 256,
            T=cfg["data"].get("T", 64),
            S=cfg["model"]["num_stations"],
            F=cfg["model"]["num_features"],
        )
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Dataset NPZ not found: {path}")
    data = np.load(path)
    X = torch.tensor(data["X"]).float()
    yf = torch.tensor(data["y_flood"]).long()
    yh = torch.tensor(data["y_hydro"]).float()
    yq = torch.tensor(data["y_qual"]).float()
    return (X, yf, yh, yq), {"path": path}
