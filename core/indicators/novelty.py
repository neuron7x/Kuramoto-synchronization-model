# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Novelty score helpers supporting FHMC integration tests."""

from __future__ import annotations

import numpy as np


def kl_div(p: np.ndarray, q: np.ndarray) -> float:
    p = np.clip(p.astype(float), 1e-8, 1.0)
    q = np.clip(q.astype(float), 1e-8, 1.0)
    p /= p.sum()
    q /= q.sum()
    return float((p * np.log(p / q)).sum())


def novelty_score(z_now: np.ndarray, z_ref: np.ndarray) -> float:
    a = z_now / (np.linalg.norm(z_now) + 1e-8)
    b = z_ref / (np.linalg.norm(z_ref) + 1e-8)
    cosine = float(np.dot(a, b))
    return 1.0 - cosine
