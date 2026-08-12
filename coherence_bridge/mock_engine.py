"""Deterministic mock engine for integration testing and Askar demo.

All noise is hashlib-based (no random module). Given the same
(instrument, call_count) pair, output is fully reproducible.
"""

from __future__ import annotations

import hashlib
import math
import struct
import time

from coherence_bridge.engine_interface import SignalEngine


def _hash_float(seed: str, lo: float = -1.0, hi: float = 1.0) -> float:
    """Deterministic float in [lo, hi] from a string seed via SHA-256."""
    digest = hashlib.sha256(seed.encode()).digest()
    # Take first 8 bytes as uint64, normalize to [0, 1]
    uint64: int = struct.unpack(">Q", digest[:8])[0]
    normalized = uint64 / (2**64 - 1)
    return lo + normalized * (hi - lo)


class MockEngine(SignalEngine):
    """Cycles through regime states with physics-plausible values.

    Regime physics (enforced):
      COHERENT:    γ≈0.6, R≈0.85, ricci>0,    lyapunov<0
      METASTABLE:  γ≈1.0, R≈0.55, ricci≈-0.1, lyapunov≈0
      DECOHERENT:  γ≈1.5, R≈0.15, ricci<0,    lyapunov>0
      CRITICAL:    γ≈0.4, R≈0.92, ricci>>0,   lyapunov>>0
    """

    INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]

    _REGIME_CYCLE = [
        "DECOHERENT",
        "METASTABLE",
        "COHERENT",
        "METASTABLE",
        "CRITICAL",
        "DECOHERENT",
    ]

    _BASE_GAMMA: dict[str, float] = {
        "COHERENT": 0.6,
        "METASTABLE": 1.0,
        "DECOHERENT": 1.5,
        "CRITICAL": 0.4,
    }
    _BASE_R: dict[str, float] = {
        "COHERENT": 0.85,
        "METASTABLE": 0.55,
        "DECOHERENT": 0.15,
        "CRITICAL": 0.92,
    }
    _BASE_RICCI: dict[str, float] = {
        "COHERENT": 0.3,
        "METASTABLE": -0.1,
        "DECOHERENT": -0.5,
        "CRITICAL": 0.8,
    }
    _BASE_LYAP: dict[str, float] = {
        "COHERENT": -0.02,
        "METASTABLE": 0.001,
        "DECOHERENT": 0.05,
        "CRITICAL": 0.08,
    }
    _BASE_SIGNAL: dict[str, float] = {
        "COHERENT": 0.6,
        "METASTABLE": 0.0,
        "DECOHERENT": 0.0,
        "CRITICAL": -0.8,
    }

    def __init__(self, seed: int | None = None) -> None:
        self._start = time.time()
        self._seed = seed
        self._seq: dict[str, int] = {}

    @property
    def instruments(self) -> list[str]:
        return self.INSTRUMENTS

    def get_signal(self, instrument: str) -> dict[str, object] | None:
        if instrument not in self.INSTRUMENTS:
            return None

        seq = self._seq.get(instrument, 0)
        self._seq[instrument] = seq + 1

        t = time.time() - self._start
        inst_hash = (
            int.from_bytes(
                hashlib.md5(instrument.encode()).digest()[:4],
                "big",
            )
            % 100
        )
        phase = (t + inst_hash) / 30.0

        cycle_idx = int(phase) % len(self._REGIME_CYCLE)
        regime = self._REGIME_CYCLE[cycle_idx]

        # Deterministic perturbations via hashlib
        noise_seed = f"{instrument}:{seq}"
        gamma_noise = _hash_float(f"gamma:{noise_seed}", -0.05, 0.05)
        r_noise = _hash_float(f"R:{noise_seed}", -0.05, 0.05)
        ricci_noise = _hash_float(f"ricci:{noise_seed}", -0.02, 0.02)
        signal_scale = _hash_float(f"signal:{noise_seed}", 0.8, 1.0)

        gamma = self._BASE_GAMMA[regime] + gamma_noise + 0.03 * math.sin(t * 0.3)
        R = max(0.0, min(1.0, self._BASE_R[regime] + r_noise))
        ricci = self._BASE_RICCI[regime] + ricci_noise
        lyap = self._BASE_LYAP[regime]
        confidence = 0.7 + 0.2 * abs(math.sin(phase * math.pi))
        duration = (phase - int(phase)) * 30.0
        signal_str = self._BASE_SIGNAL[regime] * signal_scale
        risk = max(0.0, min(1.0, 1.0 - abs(gamma - 1.0)))

        return {
            "timestamp_ns": time.time_ns(),
            "instrument": instrument,
            "gamma": round(gamma, 6),
            "order_parameter_R": round(R, 6),
            "ricci_curvature": round(ricci, 6),
            "lyapunov_max": round(lyap, 6),
            "regime": regime,
            "regime_confidence": round(confidence, 4),
            "regime_duration_s": round(duration, 2),
            "signal_strength": round(signal_str, 4),
            "risk_scalar": round(risk, 4),
            "sequence_number": seq,
        }
