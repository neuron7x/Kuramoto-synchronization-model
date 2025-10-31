from __future__ import annotations

import argparse
from typing import Dict, Iterable, Tuple, Literal, TypedDict
import math

import numpy as np

from runtime.monotonic_gate import assert_monotonic_invariant

BondType = Literal["covalent", "ionic", "metallic", "vdw", "hydrogen"]


class BondParams(TypedDict):
    base_energy: float
    latency_weight: float
    coherency_weight: float
    stability_bonus: float


BOND_LIBRARY: Dict[BondType, BondParams] = {
    "covalent": {"base_energy": 1.0, "latency_weight": 4.0, "coherency_weight": 2.0, "stability_bonus": 1.5},
    "ionic": {"base_energy": 1.4, "latency_weight": 2.5, "coherency_weight": 4.0, "stability_bonus": 1.2},
    "metallic": {"base_energy": 0.7, "latency_weight": 1.0, "coherency_weight": 1.5, "stability_bonus": 2.5},
    "vdw": {"base_energy": 0.25, "latency_weight": 0.6, "coherency_weight": 0.8, "stability_bonus": 0.2},
    "hydrogen": {"base_energy": 0.5, "latency_weight": 1.8, "coherency_weight": 3.5, "stability_bonus": 3.2},
}

K_BOLTZMANN_EFFECTIVE = 1.38e-23
SYSTEM_TEMPERATURE_K = 300.0

# We operate on dimensionless, normalised energy units.  The raw contributions
# coming from bond, resource and entropy terms are scaled down to match
# physically plausible magnitudes (≈10⁻¹⁸ J) which keeps numerical derivatives
# stable even when control loops run at sub-millisecond cadence.
ENERGY_SCALE = 1e-18


def _bond_energy(
    src: str,
    dst: str,
    kind: BondType,
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
) -> float:
    params = BOND_LIBRARY[kind]

    latency = float(latencies.get((src, dst), 1.0))
    coherence = float(coherency.get((src, dst), 0.0))

    latency = max(latency, 0.0)
    coherence = float(np.clip(coherence, 0.0, 1.0))

    latency_cost = params["latency_weight"] * math.log(1.0 + latency)
    incoherence_cost = params["coherency_weight"] * (1.0 - coherence) ** 2
    stability_gain = params["stability_bonus"] * coherence

    return params["base_energy"] + latency_cost + incoherence_cost - stability_gain


def system_free_energy(
    bonds: Dict[Tuple[str, str], BondType],
    latencies: Dict[Tuple[str, str], float],
    coherency: Dict[Tuple[str, str], float],
    resource_usage: float,
    entropy: float,
) -> float:
    internal_energy = 0.0
    for (src, dst), kind in bonds.items():
        internal_energy += _bond_energy(src, dst, kind, latencies, coherency)

    resource_term = 2.0 * float(np.clip(resource_usage, 0.0, 1.0))
    entropy_term = (K_BOLTZMANN_EFFECTIVE * SYSTEM_TEMPERATURE_K) * max(entropy, 0.0)

    free_energy = internal_energy + resource_term + entropy_term
    return ENERGY_SCALE * free_energy


def delta_free_energy(F_prev: float, F_now: float, dt_seconds: float) -> float:
    if dt_seconds <= 0:
        return 0.0
    return (F_now - F_prev) / dt_seconds


def compute_baseline_free_energy(samples: int = 10, alpha: float = 0.05) -> float:
    if samples <= 0:
        raise ValueError("samples must be positive")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in the interval (0, 1]")

    bonds: Dict[Tuple[str, str], BondType] = {
        ("ingest", "matcher"): "covalent",
        ("matcher", "risk"): "ionic",
        ("risk", "broker"): "metallic",
        ("broker", "audit"): "hydrogen",
    }
    base_latencies: Dict[Tuple[str, str], float] = {
        ("ingest", "matcher"): 0.42,
        ("matcher", "risk"): 0.75,
        ("risk", "broker"): 0.18,
        ("broker", "audit"): 1.05,
    }
    base_coherency: Dict[Tuple[str, str], float] = {
        edge: 0.82 for edge in bonds
    }

    ema: float | None = None
    resource_usage = 0.58
    entropy = 0.37

    for idx in range(samples):
        scale = 1.0 + 0.01 * math.sin(idx)
        latencies = {edge: value * scale for edge, value in base_latencies.items()}
        coherency = {
            edge: float(np.clip(base_coherency[edge] - 0.001 * idx, 0.0, 1.0)) for edge in bonds
        }
        sample = system_free_energy(bonds, latencies, coherency, resource_usage, entropy)
        if ema is None:
            ema = sample
        else:
            ema = alpha * sample + (1.0 - alpha) * ema

    return float(ema if ema is not None else 0.0)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Thermodynamic energy utilities")
    parser.add_argument("--baseline", action="store_true", help="Compute the baseline free energy EMA")
    parser.add_argument("--samples", type=int, default=10, help="Number of samples for the baseline EMA")
    parser.add_argument("--alpha", type=float, default=0.05, help="EMA smoothing factor")
    parser.add_argument(
        "--verify-invariant",
        action="store_true",
        help="Verify F_new ≤ F_old + ε using the monotonic gate",
    )
    parser.add_argument("--F-old", type=float, dest="F_old", help="Previous free energy value")
    parser.add_argument("--F-new", type=float, dest="F_new", help="Candidate free energy value")
    parser.add_argument(
        "--baseline-ema",
        type=float,
        dest="baseline_ema",
        help="Baseline EMA used to derive ε",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    executed = False
    if args.baseline:
        baseline = compute_baseline_free_energy(samples=args.samples, alpha=args.alpha)
        print(f"baseline_F={baseline:.12e}")
        executed = True

    if args.verify_invariant:
        if args.F_old is None or args.F_new is None or args.baseline_ema is None:
            parser.error("--verify-invariant requires --F-old, --F-new and --baseline-ema")
        result = assert_monotonic_invariant(
            args.F_old,
            args.F_new,
            baseline_ema=args.baseline_ema,
        )
        print(
            "invariant_hold=1 delta_F="
            f"{result.delta_F:.12e} epsilon={result.epsilon_spike:.12e}"
        )
        executed = True

    if not executed:
        parser.print_help()


__all__ = [
    "BondType",
    "BondParams",
    "BOND_LIBRARY",
    "K_BOLTZMANN_EFFECTIVE",
    "SYSTEM_TEMPERATURE_K",
    "ENERGY_SCALE",
    "system_free_energy",
    "delta_free_energy",
    "compute_baseline_free_energy",
    "main",
]


if __name__ == "__main__":
    main()
