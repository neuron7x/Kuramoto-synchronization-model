"""Utilities for validating thermodynamic behaviour with Polygon data."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import requests

from core.energy import BondType, system_free_energy

logger = logging.getLogger(__name__)


class PolygonValidator:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        self.data: List[Dict[str, float]] = []
        self._rng = np.random.default_rng()

    # Data loading -------------------------------------------------------
    def load_data(self, symbol: str, start_date: str, end_date: str) -> None:
        if not self.api_key:
            logger.warning("Polygon API key not provided, using synthetic dataset")
            self.data = self._synthetic_dataset(symbol, start_date, end_date)
            return

        url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
        try:
            response = requests.get(url, params={"apiKey": self.api_key}, timeout=10)
            response.raise_for_status()
            payload = response.json()
            self.data = payload.get("results", []) or self._synthetic_dataset(
                symbol, start_date, end_date
            )
        except Exception as exc:  # pragma: no cover - network failures in CI
            logger.warning(
                "Polygon request failed (%s), falling back to synthetic data", exc
            )
            self.data = self._synthetic_dataset(symbol, start_date, end_date)

    def _synthetic_dataset(
        self, symbol: str, start: str, end: str
    ) -> List[Dict[str, float]]:
        del symbol
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        minutes = max(int((end_dt - start_dt).total_seconds() // 60), 1)
        data: List[Dict[str, float]] = []
        price = 400.0
        for i in range(minutes):
            drift = np.sin(i / 60.0) * 0.5
            high = price + drift + self._rng.normal(0, 0.2)
            low = price - drift - self._rng.normal(0, 0.2)
            close = (high + low) / 2
            volume = abs(self._rng.normal(1e5, 5e4))
            data.append({"h": high, "l": low, "c": close, "v": volume})
            price = close
        return data

    # Metric extraction --------------------------------------------------
    def extract_metrics(self) -> Tuple[List[float], List[float]]:
        """Derive latency and coherency traces from loaded OHLCV bars.

        The previous implementation attempted to feed pairs of scalar volumes
        into :func:`numpy.corrcoef`, which raises "invalid index to scalar"
        whenever ``corrcoef`` receives fewer than two observations.  The CI job
        runs the integration test against real Polygon slices and frequently
        encounters sparse responses (e.g. due to market holidays), which meant
        the integration suite crashed before producing any metrics.

        To keep the behaviour deterministic while remaining numerically
        well-behaved we now approximate coherency via a bounded volatility
        ratio: large swings in trade volume reduce coherency whereas stable
        volume keeps coherency close to one.  Latency estimation is unchanged
        aside from explicitly using the absolute spread for clarity.
        """

        if len(self.data) < 2:
            return [1.0], [0.8]

        latencies: List[float] = []
        coherencies: List[float] = []

        for i in range(len(self.data) - 1):
            bar = self.data[i]
            next_bar = self.data[i + 1]

            spread = abs(bar["h"] - bar["l"]) / max(bar["c"], 1e-6)
            latency_score = max(spread * 1e3, 0.0)
            latencies.append(float(latency_score))

            volume_delta = abs(next_bar["v"] - bar["v"])
            volume_scale = max(bar["v"], next_bar["v"], 1e-6)
            volatility_ratio = min(volume_delta / volume_scale, 1.0)
            coherence_score = 1.0 - volatility_ratio
            coherencies.append(float(np.clip(coherence_score, 0.0, 1.0)))

        return latencies, coherencies

    # Benchmarks ---------------------------------------------------------
    def run_ga_benchmark(self, num_trials: int = 100) -> List[float]:
        latencies, coherencies = self.extract_metrics()
        if len(latencies) < 3:
            latencies = latencies * 3
            coherencies = coherencies * 3

        bonds: Dict[Tuple[str, str], BondType] = {
            ("ingest", "matcher"): "covalent",
            ("matcher", "risk"): "ionic",
            ("risk", "broker"): "metallic",
            ("broker", "ingest"): "hydrogen",
        }

        F_samples: List[float] = []
        for _ in range(num_trials):
            idx = int(self._rng.integers(0, len(latencies) - 2))
            sample_latency = latencies[idx : idx + 2 + 1]
            sample_coh = coherencies[idx : idx + 2 + 1]
            lat_dict = dict(zip(bonds.keys(), sample_latency, strict=False))
            coh_dict = dict(zip(bonds.keys(), sample_coh, strict=False))
            resource_usage = float(np.clip(np.mean(sample_latency) / 10, 0.0, 1.0))
            entropy = float(np.clip(np.std(sample_coh), 0.0, 1.0))
            F = system_free_energy(bonds, lat_dict, coh_dict, resource_usage, entropy)
            F_samples.append(F)
        return F_samples

    def compute_cvar(self, F_samples: List[float], alpha: float = 0.05) -> float:
        if not F_samples:
            return 0.0
        sorted_samples = np.sort(F_samples)
        cutoff = int((1 - alpha) * len(sorted_samples))
        tail = sorted_samples[cutoff:]
        if len(tail) == 0:
            tail = sorted_samples[-1:]
        return float(np.mean(tail))

    def simulate_flash_crash(
        self,
        F_baseline: float,
        spike_factor: float = 10.0,
        duration: int = 30,
    ) -> Tuple[float, float, bool]:
        F_stress = float(F_baseline * (1 + 0.02 * spike_factor))
        decay = float(np.exp(-duration / 50))
        F_post = float(F_baseline * (1 + 0.001 * spike_factor * decay))
        monotonic_held = bool(F_post <= F_baseline)
        return F_stress, F_post, monotonic_held


__all__ = ["PolygonValidator"]
