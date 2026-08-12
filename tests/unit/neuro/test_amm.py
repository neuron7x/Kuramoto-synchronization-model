# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from core.neuro.amm import AdaptiveMarketMind, AMMConfig


def test_precision_penalized_by_entropy_and_desync() -> None:
    cfg = AMMConfig(alpha=0.05, beta=1.0, lambda_sync=0.5, eta_ricci=0.3, pi_max=100.0, pi_min=1e-6)
    rng = np.random.default_rng(1)

    amm = AdaptiveMarketMind(cfg, use_internal_entropy=False, R_bar=0.5)
    for _ in range(200):
        amm.update(float(rng.normal(0.0, 0.05)), R_t=0.5, kappa_t=0.0, H_t=0.1)

    baseline = amm.update(0.001, R_t=0.5, kappa_t=0.0, H_t=0.1)["amm_precision"]
    stressed = amm.update(0.001, R_t=0.2, kappa_t=-0.5, H_t=1.5)["amm_precision"]
    assert stressed < baseline

    amm_internal = AdaptiveMarketMind(cfg, use_internal_entropy=True, R_bar=0.5)
    for _ in range(200):
        amm_internal.update(float(rng.normal(0.0, 0.05)), R_t=0.5, kappa_t=0.0, H_t=0.0)

    internal_baseline = amm_internal.update(0.001, R_t=0.5, kappa_t=0.0, H_t=0.1)["amm_precision"]
    internal_stressed = amm_internal.update(0.001, R_t=0.5, kappa_t=0.0, H_t=1.5)["amm_precision"]
    assert internal_stressed < internal_baseline


def test_bursts_trigger_after_shock() -> None:
    cfg = AMMConfig()
    amm = AdaptiveMarketMind(cfg)
    pulses: list[float] = []
    for i in range(400):
        x = 0.0005 if i < 300 else (0.02 if i % 2 == 0 else -0.02)
        out = amm.update(x, R_t=0.7, kappa_t=0.1)
        pulses.append(out["amm_pulse"])
    q_hi = np.quantile(np.asarray(pulses[-128:], dtype=np.float32), 0.8)
    assert pulses[-1] >= q_hi * 0.8


def test_async_interface_matches_sync_output() -> None:
    cfg = AMMConfig()

    async def run() -> tuple[dict, dict, dict]:
        amm_sync = AdaptiveMarketMind(cfg)
        amm_async = AdaptiveMarketMind(cfg)
        amm_offload = AdaptiveMarketMind(cfg)
        sync_out = amm_sync.update(0.001, 0.6, 0.1, None)
        async_out = await amm_async.aupdate(0.001, 0.6, 0.1, None)
        offload_out = await amm_offload.aupdate(0.001, 0.6, 0.1, None, offload=True)
        return sync_out, async_out, offload_out

    sync_out, async_out, offload_out = asyncio.run(run())
    for key in ("amm_pulse", "amm_precision", "amm_valence", "pred", "pe", "entropy"):
        for result in (async_out, offload_out):
            assert key in result and isinstance(result[key], float)
            assert pytest.approx(sync_out[key], rel=1e-5, abs=1e-5) == result[key]


def test_batch_matches_stream_updates() -> None:
    cfg = AMMConfig()
    rng = np.random.default_rng(4)
    x = rng.normal(0.0, 0.01, 64).astype(np.float32)
    R = rng.uniform(0.3, 0.7, 64).astype(np.float32)
    kappa = rng.normal(0.0, 0.2, 64).astype(np.float32)

    amm = AdaptiveMarketMind(cfg)
    seq = {k: [] for k in ("amm_pulse", "amm_precision", "amm_valence", "pred", "pe", "entropy")}
    for i in range(len(x)):
        out = amm.update(float(x[i]), float(R[i]), float(kappa[i]), None)
        for key in seq:
            seq[key].append(out[key])

    batched = AdaptiveMarketMind.batch(cfg, x, R, kappa, None)
    for key in seq:
        assert np.allclose(batched[key], np.asarray(seq[key], dtype=np.float32), atol=1e-6)
