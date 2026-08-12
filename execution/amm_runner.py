# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from prometheus_client import start_http_server

from analytics.amm_metrics import publish_metrics, timed_update
from core.neuro.amm import AdaptiveMarketMind, AMMConfig


class AMMRunner:
    def __init__(
        self,
        symbol: str,
        tf: str,
        cfg: AMMConfig | None = None,
        metrics_port: int = 9095,
    ):
        self.symbol = symbol
        self.tf = tf
        self.amm = AdaptiveMarketMind(cfg or AMMConfig())
        start_http_server(metrics_port)

    async def on_tick(self, x: float, R: float, kappa: float, H: float | None = None) -> dict:
        with timed_update(self.symbol, self.tf):
            out = await self.amm.aupdate(x, R, kappa, H, offload=False)
        publish_metrics(
            self.symbol,
            self.tf,
            out,
            k=self.amm.gain,
            theta=self.amm.threshold,
            q_hi=None,
        )
        return out

    async def run_stream(self, aiter_ticks):
        async for x, R, kappa, H in aiter_ticks:
            yield await self.on_tick(x, R, kappa, H)
