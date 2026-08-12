# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Numerical calibration certificate — every exact law passes with quantified margin.

Passing a tolerance check is binary. A CALIBRATED system additionally reports HOW
FAR inside the bound it sits, with provenance: measured residual, threshold, and
the safety margin (orders of magnitude of headroom). A law that barely scrapes
its tolerance is fragile; a law with many orders of margin is calibrated. This
module computes the certificate from the REAL solvers and asserts every law is
not merely passing but calibrated with strictly positive margin — and emits the
certificate as a deterministic artifact.

A negative control proves the margin metric is real: a fabricated measurement at
the threshold has zero margin and a measurement past it has negative margin, both
of which the certificate flags as NOT calibrated.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import networkx as nx

from analytics.math_trading.kelly_criterion import kelly_from_edge_variance
from core.dro_ara.engine import derive_gamma
from core.indicators.gauss_bonnet import euler_characteristic, gauss_bonnet_residual
from core.kuramoto.ott_antonsen import OttAntonsenEngine
from core.physics.landauer import K_BOLTZMANN, bit_erasure_cost

import numpy as np

_CERT_PATH = Path("evidence/physics/calibration_certificate.json")


@dataclass(frozen=True)
class CalibrationRow:
    """One law's calibration record: measured residual, threshold, and margin."""

    law: str
    solver: str
    measured: float  # residual / deviation from the invariant (>= 0)
    threshold: float  # the tolerance the law must satisfy
    margin_decades: float  # log10(threshold / max(measured, tiny)) — headroom in decades

    @property
    def calibrated(self) -> bool:
        """Calibrated iff the measurement is strictly inside the threshold (margin > 0)."""
        return self.measured < self.threshold


def _margin_decades(measured: float, threshold: float) -> float:
    return math.log10(threshold / max(measured, 1e-300))


def _certificate() -> list[CalibrationRow]:
    """Build the calibration certificate from the real exact-law solvers."""
    rows: list[CalibrationRow] = []

    # Ott-Antonsen: |integrated R_inf - sqrt(1-2d/K)|, threshold 1e-9.
    delta, coupling = 0.5, 2.0
    r_inf = float(OttAntonsenEngine(K=coupling, delta=delta).integrate(T=200.0, dt=0.01, R0=0.05).R[-1])
    oa_res = abs(r_inf - math.sqrt(1.0 - (2.0 * delta) / coupling))
    rows.append(CalibrationRow("ott_antonsen_steady_state", "OttAntonsenEngine.integrate (RK4)", oa_res, 1e-9, _margin_decades(oa_res, 1e-9)))

    # Landauer: |cost/(k_B T ln2) - 1|, threshold 1e-12.
    temperature = 300.0
    floor = K_BOLTZMANN * temperature * math.log(2.0)
    land_res = abs(bit_erasure_cost(1.0, temperature) / floor - 1.0)
    rows.append(CalibrationRow("landauer_bit_floor", "bit_erasure_cost", land_res, 1e-12, _margin_decades(land_res, 1e-12)))

    # Kelly: |f* - mu/sigma^2|, threshold 1e-12.
    mu, sigma_sq = 0.002, 2.5e-3
    kelly_res = abs(kelly_from_edge_variance(mu, sigma_sq, fractional_kelly=1.0, max_fraction=10.0) - mu / sigma_sq)
    rows.append(CalibrationRow("kelly_optimal_fraction", "kelly_from_edge_variance", kelly_res, 1e-12, _margin_decades(kelly_res, 1e-12)))

    # DRO-ARA: |gamma - (2H+1)|, threshold 1e-5.
    series = np.cumsum(np.random.default_rng(7).normal(0.0, 1.0, 1024))
    gamma, hurst, _r2 = derive_gamma(series)
    dro_res = abs(gamma - (2.0 * hurst + 1.0))
    rows.append(CalibrationRow("dro_ara_gamma", "derive_gamma", dro_res, 1e-5, _margin_decades(dro_res, 1e-5)))

    # Gauss-Bonnet: |residual| (exact 0), threshold 1e-12 (any nonzero is a violation).
    gb_res = abs(float(gauss_bonnet_residual(nx.cycle_graph(6))))
    assert euler_characteristic(nx.cycle_graph(6)) == 0
    rows.append(CalibrationRow("gauss_bonnet_exact", "gauss_bonnet_residual (Fraction)", gb_res, 1e-12, _margin_decades(gb_res, 1e-12)))

    return rows


def test_every_exact_law_is_calibrated_with_positive_margin() -> None:
    """Positive witness: every exact law sits strictly inside its threshold; emit the cert.

    Not merely "passes" but "calibrated": the measured residual is below the
    threshold with a strictly positive margin, and the per-law headroom (decades)
    is recorded as a deterministic artifact.
    """
    rows = _certificate()
    assert len(rows) >= 5, f"calibration certificate too thin: {len(rows)} laws (need >= 5)"

    worst_margin = math.inf
    for row in rows:
        assert row.calibrated, (
            f"CALIBRATION VIOLATED: law '{row.law}' measured residual {row.measured:.3e} is NOT "
            f"strictly inside threshold {row.threshold:.1e} (margin_decades={row.margin_decades:.2f}). "
            f"solver={row.solver}. A law at or past its tolerance is not calibrated."
        )
        assert row.margin_decades > 0.0, (
            f"CALIBRATION VIOLATED: law '{row.law}' has non-positive margin "
            f"({row.margin_decades:.3f} decades); no headroom. solver={row.solver}."
        )
        worst_margin = min(worst_margin, row.margin_decades)

    # Emit the certificate (deterministic; sorted; rounded to keep it stable).
    payload = {
        "schema": "geosync.calibration_certificate.v1",
        "worst_margin_decades": round(worst_margin, 6),
        "rows": sorted(
            (
                {**asdict(r), "calibrated": r.calibrated, "margin_decades": round(r.margin_decades, 6)}
                for r in rows
            ),
            key=lambda d: str(d["law"]),
        ),
    }
    _CERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CERT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert _CERT_PATH.is_file()


def test_margin_metric_flags_uncalibrated_measurements() -> None:
    """Negative control: at-threshold (zero margin) and past-threshold (negative) are flagged.

    Proves the margin metric is real: a measurement exactly at the threshold is
    NOT calibrated (margin 0), and one past it has negative margin. If either were
    scored calibrated, the certificate would be vacuous.
    """
    threshold = 1e-9

    at_threshold = CalibrationRow("synthetic_at_bound", "synthetic", threshold, threshold, _margin_decades(threshold, threshold))
    assert not at_threshold.calibrated and at_threshold.margin_decades == 0.0, (
        f"CALIBRATION META VIOLATED: a measurement AT the threshold was scored calibrated "
        f"(margin={at_threshold.margin_decades}); zero headroom must not pass."
    )

    past_threshold = CalibrationRow("synthetic_past_bound", "synthetic", 10.0 * threshold, threshold, _margin_decades(10.0 * threshold, threshold))
    assert not past_threshold.calibrated and past_threshold.margin_decades < 0.0, (
        f"CALIBRATION META VIOLATED: a measurement PAST the threshold was scored calibrated "
        f"(margin={past_threshold.margin_decades}); a violation must have negative margin."
    )
