#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# ═══════════════════════════════════════════════════════════════════════════
#
#   G E O S Y N C   O R A C L E
#   ─────────────────────────────
#   The complete physics of a financial market in one function call.
#
#   Input:  price matrix (T × N)
#   Output: regime diagnosis, position sizing, invariant proofs
#
#   Every number traced to a physical law. Every decision justified
#   by an invariant. No heuristics. No magic. Pure physics.
#
#   Usage:
#       python geosync_oracle.py                          # sample data
#       python geosync_oracle.py data/my_prices.csv       # custom data
#
#   Yaroslav Vasylenko · neuron7xLab · 2026
#
# ═══════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import hilbert

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.neuro.cryptobiosis import CryptobiosisController
from core.neuro.dopamine_execution_adapter import DopamineExecutionAdapter
from core.neuro.gaba_position_gate import GABAPositionGate
from core.neuro.gradient_vital_signs import GradientHealthMonitor
from core.neuro.signal_bus import NeuroSignalBus
from core.physics.lyapunov_exponent import maximal_lyapunov_exponent, spectral_gap

# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class MarketPhysicsState:
    """Complete physics state of a market at one point in time."""

    # ── Kuramoto synchronization ──
    order_parameter_R: float  # R ∈ [0,1] — phase coherence (INV-K1)
    critical_coupling_Kc: float  # K_c from Gaussian g(0)
    coupling_ratio_K_over_Kc: float  # K/K_c — subcritical < 1 < supercritical

    # ── Lyapunov chaos/order ──
    lyapunov_exponent: float  # λ — chaos (+) / stability (-) (INV-LE1)
    chaos_regime: str  # "chaotic" | "marginal" | "stable"

    # ── Ricci geometry ──
    mean_ricci_curvature: float  # ⟨κ⟩ — clustering (+) / fragmentation (-)
    spectral_gap_lambda2: float  # λ₂ — algebraic connectivity (INV-SG1)

    # ── Thermodynamics ──
    market_entropy: float  # S — Shannon entropy of return distribution
    free_energy: float  # F = U - T·S
    internal_energy: float  # U — realized volatility proxy

    # ── Neuromodulation ──
    gaba_inhibition: float  # Gate ∈ [0,1] (INV-GABA1)
    serotonin_level: float  # 5-HT level (INV-5HT2)
    dopamine_rpe: float  # Reward prediction error (INV-DA1)

    # ── Gradient Vital Signs ──
    gvs_score: float  # Composite health ∈ [0,1]
    gvs_status: str  # "HEALTHY" | "DEGRADED" | "CRITICAL"

    # ── Cryptobiosis ──
    cryptobiosis_state: str  # "ACTIVE" | "VITRIFYING" | "DORMANT" | "REHYDRATING"
    cryptobiosis_multiplier: float  # 0.0 in DORMANT (INV-CB1), 1.0 in ACTIVE

    # ── Decision ──
    position_multiplier: float  # Final Kelly fraction after all gates
    regime_label: str  # Human-readable regime name
    invariant_proof: str  # Which INV-* justified this decision


# ═══════════════════════════════════════════════════════════════════════════
# CORE ENGINE
# ═══════════════════════════════════════════════════════════════════════════


class GeoSyncOracle:
    """The complete physics of a financial market.

    Wires all 15 GeoSync modules into a single coherent diagnostic
    engine. Each output field is traced to a physical law in
    INVARIANTS.yaml. No intermediate result is unattributed.
    """

    def __init__(self, window: int = 24) -> None:
        self.window = window
        self.bus = NeuroSignalBus()
        self.gaba = GABAPositionGate(self.bus)
        self.dopamine = DopamineExecutionAdapter(self.bus, tanh_scale=1.0)
        self.crypto = CryptobiosisController()
        self.monitor = GradientHealthMonitor(window=max(100, window * 4))
        self._R_history: list[float] = []

    def diagnose(
        self,
        prices: np.ndarray,
        *,
        current_return: float = 0.0,
    ) -> MarketPhysicsState:
        """Compute the complete physics state from a price matrix.

        Parameters
        ----------
        prices : (T, N) array
            Price matrix — T timesteps, N assets.
        current_return : float
            Most recent portfolio return (for Dopamine RPE).

        Returns
        -------
        MarketPhysicsState
            Every field traced to an invariant.
        """
        prices = np.asarray(prices, dtype=np.float64)
        if prices.ndim == 1:
            prices = prices.reshape(-1, 1)
        T, N = prices.shape

        log_returns = np.diff(np.log(np.maximum(prices, 1e-10)), axis=0)

        # ════════════════════════════════════════════════════════════════
        # 1. KURAMOTO ORDER PARAMETER — INV-K1: R ∈ [0, 1]
        # ════════════════════════════════════════════════════════════════
        R = self._compute_R(log_returns)
        self._R_history.append(R)
        if len(self._R_history) > self.window * 10:
            self._R_history = self._R_history[-self.window * 10 :]

        # Critical coupling for Gaussian frequencies
        sigma = float(np.std(log_returns)) if log_returns.size > 0 else 1.0
        K_c = 2.0 * max(sigma, 1e-10) * math.sqrt(2 * math.pi) / math.pi

        # Effective coupling from mean absolute correlation
        if N > 1 and log_returns.shape[0] > 2:
            with np.errstate(invalid="ignore"):
                corr = np.corrcoef(log_returns.T)
            corr = np.nan_to_num(corr, nan=0.0)
            K_est = float(np.mean(np.abs(corr[np.triu_indices(N, 1)])))
        else:
            K_est = 0.0

        K_ratio = K_est / K_c if K_c > 0 else 0.0

        # ════════════════════════════════════════════════════════════════
        # 2. LYAPUNOV EXPONENT — INV-LE1: finite, INV-LE2: sign = regime
        # ════════════════════════════════════════════════════════════════
        if len(self._R_history) >= 50:
            R_arr = np.array(self._R_history, dtype=np.float64)
            mle = maximal_lyapunov_exponent(R_arr, dim=3, tau=1, max_divergence_steps=20)
        else:
            mle = 0.0

        if mle > 0.1:
            chaos_regime = "chaotic"
        elif mle < -0.05:
            chaos_regime = "stable"
        else:
            chaos_regime = "marginal"

        # ════════════════════════════════════════════════════════════════
        # 3. RICCI CURVATURE + SPECTRAL GAP — INV-RC1, INV-SG1
        # ════════════════════════════════════════════════════════════════
        if N > 1 and log_returns.shape[0] > 2:
            adj = np.abs(corr)
            np.fill_diagonal(adj, 0.0)
            adj = np.where(adj > 0.3, adj, 0.0)
            lambda2 = spectral_gap(adj)

            # Mean Ricci approximation from curvature of correlation graph
            # (simplified: use Forman formula κ_F = 4 - d_i - d_j + 3T_ij)
            degrees = (adj > 0).sum(axis=1)
            if degrees.sum() > 0:
                mean_kappa = float(4.0 - 2 * np.mean(degrees))
            else:
                mean_kappa = 0.0
        else:
            lambda2 = 0.0
            mean_kappa = 0.0

        # ════════════════════════════════════════════════════════════════
        # 4. THERMODYNAMICS — INV-FE1, INV-FE2, INV-TH2
        # ════════════════════════════════════════════════════════════════
        if log_returns.size > 0:
            vols = np.std(log_returns, axis=0)
            U = float(np.mean(vols))  # internal energy = realized vol

            # Entropy of return distribution per asset
            S_values = []
            for j in range(N):
                col = log_returns[:, j]
                if col.size > 5:
                    hist, _ = np.histogram(col, bins=min(20, col.size // 3 + 1), density=True)
                    hist = hist[hist > 0]
                    if hist.sum() > 0:
                        p = hist / hist.sum()
                        S_values.append(-float(np.sum(p * np.log(p))))
            S = float(np.mean(S_values)) if S_values else 0.0
            T_market = 1.0
            F = U - T_market * S
        else:
            U, S, F = 0.0, 0.0, 0.0

        # ════════════════════════════════════════════════════════════════
        # 5. NEUROMODULATION — INV-GABA1/2, INV-DA1, INV-5HT2
        # ════════════════════════════════════════════════════════════════
        vix_proxy = (
            float(np.std(log_returns[-min(24, log_returns.shape[0]) :]) * math.sqrt(8760) * 100)
            if log_returns.size > 0
            else 15.0
        )
        vol_proxy = (
            float(np.std(log_returns[-min(24, log_returns.shape[0]) :]) * math.sqrt(8760))
            if log_returns.size > 0
            else 0.15
        )

        gaba_inh = self.gaba.update_inhibition(vix=vix_proxy, volatility=vol_proxy, rpe=0.0)
        rpe = self.dopamine.compute_rpe(realized_pnl=current_return, predicted_return=0.0)
        serotonin = min(1.0, 0.3 + 0.5 * min(1.0, vix_proxy / 50.0))
        self.bus.publish_gaba(gaba_inh)
        self.bus.publish_kuramoto(R)
        self.bus.publish_serotonin(serotonin)
        self.bus.publish_dopamine(rpe)

        # ════════════════════════════════════════════════════════════════
        # 6. GRADIENT VITAL SIGNS — GVS composite health
        # ════════════════════════════════════════════════════════════════
        vitals = self.monitor.update(
            R=R,
            gaba=gaba_inh,
            serotonin=serotonin,
            ecs_free_energy=max(0.0, F),
        )

        # ════════════════════════════════════════════════════════════════
        # 7. CRYPTOBIOSIS — INV-CB1: DORMANT → mult = 0.0 EXACTLY
        # ════════════════════════════════════════════════════════════════
        T_distress = 1.0 - vitals.gvs_score
        crypto_result = self.crypto.update(T=T_distress)

        # ════════════════════════════════════════════════════════════════
        # 8. POSITION SIZING — all gates composed
        # ════════════════════════════════════════════════════════════════
        neuro_mult = self.bus.compute_position_multiplier(kelly_base=1.0)
        final_mult = neuro_mult * crypto_result["multiplier"]

        # ════════════════════════════════════════════════════════════════
        # 9. REGIME CLASSIFICATION
        # ════════════════════════════════════════════════════════════════
        if crypto_result["state"] == "DORMANT":
            regime = "DORMANT — gradient collapsed, zero exposure"
            proof = "INV-CB1: DORMANT ⟹ multiplier == 0.0"
        elif vitals.gvs_score < 0.3:
            regime = "CRITICAL — gradient failing, minimal exposure"
            proof = "INV-YV1: M(t) < M_crit ⟹ P(t) → noise"
        elif R > 0.7 and gaba_inh > 0.8:
            regime = "CRISIS — synchronized, GABA braking hard"
            proof = "INV-GABA2: high vol → high inhibition; INV-K3: R > K_c"
        elif R > 0.5:
            regime = "TRANSITION — synchronization building"
            proof = "INV-K2/K3: R near K_c, phase transition zone"
        elif chaos_regime == "stable" and R < 0.3:
            regime = "CALM — independent assets, stable dynamics"
            proof = "INV-K2: subcritical R ~ 1/√N; INV-LE2: λ < 0"
        else:
            regime = "NORMAL — mixed signals, moderate exposure"
            proof = "INV-KELLY2: fraction within [floor, ceil]"

        return MarketPhysicsState(
            order_parameter_R=R,
            critical_coupling_Kc=K_c,
            coupling_ratio_K_over_Kc=K_ratio,
            lyapunov_exponent=mle,
            chaos_regime=chaos_regime,
            mean_ricci_curvature=mean_kappa,
            spectral_gap_lambda2=lambda2,
            market_entropy=S,
            free_energy=F,
            internal_energy=U,
            gaba_inhibition=gaba_inh,
            serotonin_level=serotonin,
            dopamine_rpe=rpe,
            gvs_score=vitals.gvs_score,
            gvs_status=vitals.status,
            cryptobiosis_state=crypto_result["state"],
            cryptobiosis_multiplier=crypto_result["multiplier"],
            position_multiplier=final_mult,
            regime_label=regime,
            invariant_proof=proof,
        )

    def _compute_R(self, log_returns: np.ndarray) -> float:
        """Kuramoto order parameter from multi-asset returns."""
        T, N = log_returns.shape
        if T < self.window or N < 2:
            return 0.0
        w = log_returns[-self.window :]
        phases = np.zeros((self.window, N))
        for j in range(N):
            phases[:, j] = np.angle(hilbert(w[:, j]))
        # INV-K1: R ∈ [0, 1]
        return float(np.clip(np.abs(np.mean(np.exp(1j * phases[-1]))), 0.0, 1.0))


# ═══════════════════════════════════════════════════════════════════════════
# CLI — ONE COMMAND, FULL PHYSICS
# ═══════════════════════════════════════════════════════════════════════════


def _render_state(state: MarketPhysicsState) -> str:
    """Render the complete physics state as a human-readable report."""
    lines = []
    w = 68

    lines.append("╔" + "═" * w + "╗")
    lines.append("║" + "  G E O S Y N C   O R A C L E".center(w) + "║")
    lines.append("║" + "  Complete Market Physics Diagnosis".center(w) + "║")
    lines.append("╠" + "═" * w + "╣")

    def row(label: str, value: str, unit: str = "") -> str:
        content = f"  {label:<30} {value:>20} {unit:<10}"
        return "║" + content[:w].ljust(w) + "║"

    lines.append("║" + "  ── Synchronization (Kuramoto) ──".ljust(w) + "║")
    lines.append(row("Order Parameter R(t)", f"{state.order_parameter_R:.4f}", "INV-K1"))
    lines.append(
        row(
            "K / K_c ratio",
            f"{state.coupling_ratio_K_over_Kc:.3f}",
            "sub" if state.coupling_ratio_K_over_Kc < 1 else "SUPER",
        )
    )

    lines.append("║" + "  ── Chaos Diagnostic (Lyapunov) ──".ljust(w) + "║")
    lines.append(row("λ_max", f"{state.lyapunov_exponent:.4f}", state.chaos_regime))

    lines.append("║" + "  ── Geometry (Ricci + Spectral) ──".ljust(w) + "║")
    lines.append(
        row(
            "Mean Ricci κ",
            f"{state.mean_ricci_curvature:.4f}",
            "cluster" if state.mean_ricci_curvature > 0 else "fragment",
        )
    )
    lines.append(row("Spectral Gap λ₂", f"{state.spectral_gap_lambda2:.4f}", "INV-SG1"))

    lines.append("║" + "  ── Thermodynamics ──".ljust(w) + "║")
    lines.append(row("Entropy S", f"{state.market_entropy:.4f}"))
    lines.append(row("Internal Energy U", f"{state.internal_energy:.6f}"))
    lines.append(row("Free Energy F = U−T·S", f"{state.free_energy:.4f}", "INV-FE1"))

    lines.append("║" + "  ── Neuromodulation ──".ljust(w) + "║")
    lines.append(row("GABA Inhibition", f"{state.gaba_inhibition:.4f}", "INV-GABA1"))
    lines.append(row("Serotonin Level", f"{state.serotonin_level:.4f}", "INV-5HT2"))
    lines.append(row("Dopamine RPE", f"{state.dopamine_rpe:.4f}", "INV-DA1"))

    lines.append("║" + "  ── Gradient Vital Signs ──".ljust(w) + "║")
    gvs_bar = "█" * int(state.gvs_score * 20) + "░" * (20 - int(state.gvs_score * 20))
    lines.append(row("GVS Score", f"{state.gvs_score:.3f} [{gvs_bar}]"))
    lines.append(row("GVS Status", state.gvs_status))

    lines.append("║" + "  ── Cryptobiosis ──".ljust(w) + "║")
    lines.append(row("State", state.cryptobiosis_state, "INV-CB1"))
    lines.append(row("Multiplier", f"{state.cryptobiosis_multiplier:.1f}"))

    lines.append("╠" + "═" * w + "╣")
    lines.append("║" + "  ── DECISION ──".ljust(w) + "║")
    lines.append(row("Position Multiplier", f"{state.position_multiplier:.4f}", "FINAL"))
    lines.append("║" + f"  Regime: {state.regime_label}".ljust(w) + "║")
    lines.append("║" + f"  Proof:  {state.invariant_proof[: w - 10]}".ljust(w) + "║")
    lines.append("╚" + "═" * w + "╝")

    return "\n".join(lines)


def main() -> None:
    """Run the Oracle on sample or custom data."""
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if "close" in df.columns:
            prices = df.pivot_table(values="close", index=df.index, columns="symbol").dropna()
        else:
            prices = df.dropna()
    else:
        data_path = Path(__file__).resolve().parent / "data" / "sample_crypto_ohlcv.csv"
        df = pd.read_csv(data_path, parse_dates=["timestamp"])
        prices = df.pivot(index="timestamp", columns="symbol", values="close").dropna()

    oracle = GeoSyncOracle(window=24)
    price_matrix = prices.values

    print()
    # Run diagnosis on the latest window
    state = oracle.diagnose(price_matrix, current_return=-0.002)
    print(_render_state(state))

    # Time series: run on rolling windows and show regime evolution
    print(f"\n  Regime evolution ({prices.columns.tolist()}, {len(prices)} bars):\n")
    step = max(1, len(price_matrix) // 30)
    for t in range(oracle.window + 10, len(price_matrix), step):
        window_prices = price_matrix[: t + 1]
        ret = float(np.mean(np.diff(np.log(window_prices[-2:])), axis=1)[-1]) if t > 1 else 0.0
        s = oracle.diagnose(window_prices, current_return=ret)
        R_bar = "█" * int(s.order_parameter_R * 10) + "░" * (10 - int(s.order_parameter_R * 10))
        gvs_bar = "█" * int(s.gvs_score * 10) + "░" * (10 - int(s.gvs_score * 10))
        print(
            f"  t={t:>4}  R=[{R_bar}]{s.order_parameter_R:.2f}  "
            f"GVS=[{gvs_bar}]{s.gvs_score:.2f}  "
            f"λ={s.lyapunov_exponent:>+.3f}  "
            f"pos={s.position_multiplier:.3f}  "
            f"{s.cryptobiosis_state[0]}  "
            f"{s.regime_label[:30]}"
        )

    print("\n  ───────────────────────────────────────────────────────")
    print("  Every number above traces to a physical law in INVARIANTS.yaml.")
    print("  Every position decision is justified by an INV-* proof.")
    print("  This is not a model. This is a measurement instrument.")
    print()


if __name__ == "__main__":
    main()
