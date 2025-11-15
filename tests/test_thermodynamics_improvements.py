"""Tests for thermodynamics implementation improvements.

This module validates the enhanced thermodynamic model including:
- Entropy term scaling and sign
- Adaptive temperature computation
- Heat capacity and thermal dynamics
- Free energy calculation accuracy
"""

import pytest
import numpy as np

from core.energy import (
    K_BOLTZMANN_EFFECTIVE,
    SYSTEM_TEMPERATURE_BASE_K,
    TEMPERATURE_SCALE_FACTOR,
    SYSTEM_HEAT_CAPACITY,
    bond_internal_energy,
    compute_adaptive_temperature,
    heat_dissipation_rate,
    system_free_energy,
    thermal_stability_metric,
)


class TestEntropyScaling:
    """Test that entropy contributes meaningfully to free energy."""

    def test_entropy_term_magnitude(self):
        """Entropy term should be comparable to bond energies."""
        bonds = {("A", "B"): "covalent"}
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        resource_usage = 0.4
        entropy = 0.5

        # Calculate free energy components
        F_with_entropy = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature=1.0
        )
        F_no_entropy = system_free_energy(
            bonds, latencies, coherency, resource_usage, 0.0, temperature=1.0
        )

        entropy_contribution = abs(F_no_entropy - F_with_entropy)

        # Entropy term should be order 1e-19 (after ENERGY_SCALE)
        # This is comparable to bond energies after scaling
        assert entropy_contribution > 1e-20, "Entropy term too small"
        assert entropy_contribution < 1e-17, "Entropy term too large"

    def test_entropy_reduces_free_energy(self):
        """Higher entropy should reduce free energy (correct sign)."""
        bonds = {("A", "B"): "covalent", ("B", "C"): "ionic"}
        latencies = {("A", "B"): 0.5, ("B", "C"): 0.3}
        coherency = {("A", "B"): 0.8, ("B", "C"): 0.9}
        resource_usage = 0.4

        F_low_entropy = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy=0.1, temperature=1.0
        )
        F_high_entropy = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy=0.8, temperature=1.0
        )

        assert F_high_entropy < F_low_entropy, "High entropy should reduce free energy"

    def test_temperature_affects_entropy(self):
        """Higher temperature should amplify entropy effect."""
        bonds = {("A", "B"): "covalent"}
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        resource_usage = 0.4
        entropy = 0.5

        F_cold = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature=0.5
        )
        F_hot = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature=2.0
        )

        # At higher T, entropy effect is stronger (more negative contribution)
        assert F_hot < F_cold, "Higher temperature should amplify entropy reduction"


class TestAdaptiveTemperature:
    """Test adaptive temperature computation."""

    def test_base_temperature_at_equilibrium(self):
        """Temperature should be at base when system is at equilibrium."""
        baseline_F = 1.0
        current_F = 1.0
        dF_dt = 0.0

        T = compute_adaptive_temperature(baseline_F, current_F, dF_dt)

        assert abs(T - SYSTEM_TEMPERATURE_BASE_K) < 1e-6, "Should be at base temp"

    def test_temperature_rises_with_stress(self):
        """Temperature should increase when F > baseline."""
        baseline_F = 1.0
        current_F = 1.5  # System under stress
        dF_dt = 0.0

        T = compute_adaptive_temperature(baseline_F, current_F, dF_dt)

        assert T > SYSTEM_TEMPERATURE_BASE_K, "Temperature should rise with stress"

    def test_temperature_rises_with_positive_derivative(self):
        """Temperature should increase when dF/dt > 0 (heating)."""
        baseline_F = 1.0
        current_F = 1.0
        dF_dt = 0.5  # Free energy increasing

        T = compute_adaptive_temperature(baseline_F, current_F, dF_dt)

        assert T > SYSTEM_TEMPERATURE_BASE_K, "Temperature should rise when heating"

    def test_temperature_clamping(self):
        """Temperature should be clamped to reasonable bounds."""
        baseline_F = 1.0
        
        # Extreme stress
        current_F = 100.0
        dF_dt = 50.0

        T = compute_adaptive_temperature(baseline_F, current_F, dF_dt)

        # Should be clamped to at most 10x base
        assert T <= 10.0 * SYSTEM_TEMPERATURE_BASE_K, "Temperature should be clamped"

    def test_temperature_never_negative(self):
        """Temperature should never be negative."""
        baseline_F = 1.0
        current_F = 0.5  # Below baseline
        dF_dt = -0.5  # Cooling

        T = compute_adaptive_temperature(baseline_F, current_F, dF_dt)

        assert T > 0.0, "Temperature must be positive"


class TestHeatDissipation:
    """Test heat dissipation rate calculations."""

    def test_dissipation_at_equilibrium(self):
        """No dissipation when at baseline."""
        current_F = 1.0
        baseline_F = 1.0

        rate = heat_dissipation_rate(current_F, baseline_F)

        assert abs(rate) < 1e-6, "No dissipation at equilibrium"

    def test_dissipation_above_baseline(self):
        """Positive dissipation when F > baseline (cooling)."""
        current_F = 1.5
        baseline_F = 1.0

        rate = heat_dissipation_rate(current_F, baseline_F)

        assert rate > 0.0, "Should dissipate when above baseline"

    def test_dissipation_below_baseline(self):
        """Negative dissipation when F < baseline (warming)."""
        current_F = 0.5
        baseline_F = 1.0

        rate = heat_dissipation_rate(current_F, baseline_F)

        assert rate < 0.0, "Should absorb heat when below baseline"

    def test_heat_capacity_effect(self):
        """Higher heat capacity should reduce dissipation rate."""
        current_F = 2.0
        baseline_F = 1.0

        rate_low_C = heat_dissipation_rate(current_F, baseline_F, heat_capacity=5.0)
        rate_high_C = heat_dissipation_rate(current_F, baseline_F, heat_capacity=20.0)

        assert rate_low_C > rate_high_C, "Low C should dissipate faster"


class TestThermalStability:
    """Test thermal stability metric."""

    def test_maximum_at_base_temperature(self):
        """Stability should be maximum at base temperature."""
        base_temp = 1.0
        stability = thermal_stability_metric(base_temp, base_temp=base_temp)

        assert stability == pytest.approx(1.0, abs=1e-6), "Max stability at base"

    def test_decreases_with_deviation(self):
        """Stability should decrease as T deviates from base."""
        base_temp = 1.0

        stability_base = thermal_stability_metric(1.0, base_temp=base_temp)
        stability_hot = thermal_stability_metric(2.0, base_temp=base_temp)
        stability_cold = thermal_stability_metric(0.5, base_temp=base_temp)

        assert stability_hot < stability_base, "Lower stability when hot"
        assert stability_cold < stability_base, "Lower stability when cold"

    def test_range_bounds(self):
        """Stability should always be in [0, 1]."""
        temperatures = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]

        for T in temperatures:
            stability = thermal_stability_metric(T, base_temp=1.0)
            assert 0.0 <= stability <= 1.0, f"Stability out of bounds at T={T}"

    def test_relative_stability(self):
        """Stability decreases with relative deviation from base."""
        base_temp = 1.0

        stability_2x = thermal_stability_metric(2.0, base_temp=base_temp)
        stability_half = thermal_stability_metric(0.5, base_temp=base_temp)

        # Both should be less than base, but not necessarily equal
        # (exponential decay is not symmetric in ratio space)
        assert stability_2x < 1.0, "Should be less than base"
        assert stability_half < 1.0, "Should be less than base"
        assert stability_2x > 0.0, "Should be positive"
        assert stability_half > 0.0, "Should be positive"


class TestResourceTerm:
    """Test quadratic resource usage model."""

    def test_quadratic_growth(self):
        """Resource term should grow quadratically at high usage."""
        bonds = {("A", "B"): "covalent"}
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        entropy = 0.5

        F_low = system_free_energy(bonds, latencies, coherency, 0.3, entropy)
        F_mid = system_free_energy(bonds, latencies, coherency, 0.6, entropy)
        F_high = system_free_energy(bonds, latencies, coherency, 0.9, entropy)

        # Differences should increase (quadratic behavior)
        diff1 = F_mid - F_low
        diff2 = F_high - F_mid

        assert diff2 > diff1, "Resource cost should accelerate at high usage"


class TestDimensionlessUnits:
    """Test that dimensionless units are properly configured."""

    def test_boltzmann_constant(self):
        """K_BOLTZMANN_EFFECTIVE should be dimensionless (order 1)."""
        assert K_BOLTZMANN_EFFECTIVE == pytest.approx(1.0), "Should be dimensionless"

    def test_base_temperature(self):
        """Base temperature should be in effective units (order 1)."""
        assert SYSTEM_TEMPERATURE_BASE_K == pytest.approx(1.0), "Should be dimensionless"

    def test_temperature_scale_factor(self):
        """Temperature scale factor should be reasonable."""
        assert 0.01 <= TEMPERATURE_SCALE_FACTOR <= 1.0, "Scale factor reasonable"

    def test_heat_capacity(self):
        """Heat capacity should be reasonable."""
        assert 1.0 <= SYSTEM_HEAT_CAPACITY <= 100.0, "Heat capacity reasonable"


class TestBondEnergies:
    """Test bond internal energy calculations."""

    def test_low_latency_favored(self):
        """Lower latency should result in lower energy."""
        latencies_low = {("A", "B"): 0.1}
        latencies_high = {("A", "B"): 0.9}
        coherency = {("A", "B"): 0.8}

        E_low = bond_internal_energy("A", "B", "covalent", latencies_low, coherency)
        E_high = bond_internal_energy("A", "B", "covalent", latencies_high, coherency)

        assert E_low < E_high, "Low latency should have lower energy"

    def test_high_coherency_favored(self):
        """Higher coherency should result in lower energy."""
        latencies = {("A", "B"): 0.5}
        coherency_low = {("A", "B"): 0.3}
        coherency_high = {("A", "B"): 0.9}

        E_low = bond_internal_energy("A", "B", "covalent", latencies, coherency_low)
        E_high = bond_internal_energy("A", "B", "covalent", latencies, coherency_high)

        assert E_high < E_low, "High coherency should have lower energy"


class TestIntegration:
    """Integration tests for complete thermodynamic model."""

    def test_free_energy_decreases_with_optimization(self):
        """Optimizing latency and coherency should reduce free energy."""
        bonds = {("A", "B"): "covalent", ("B", "C"): "ionic"}

        # Poor configuration
        latencies_poor = {("A", "B"): 0.9, ("B", "C"): 0.8}
        coherency_poor = {("A", "B"): 0.3, ("B", "C"): 0.4}

        # Optimized configuration
        latencies_opt = {("A", "B"): 0.2, ("B", "C"): 0.1}
        coherency_opt = {("A", "B"): 0.9, ("B", "C"): 0.95}

        resource_usage = 0.4
        entropy = 0.5

        F_poor = system_free_energy(
            bonds, latencies_poor, coherency_poor, resource_usage, entropy
        )
        F_opt = system_free_energy(
            bonds, latencies_opt, coherency_opt, resource_usage, entropy
        )

        assert F_opt < F_poor, "Optimization should reduce free energy"

    def test_temperature_stress_feedback(self):
        """Temperature should rise under stress and affect optimization."""
        bonds = {("A", "B"): "covalent"}
        latencies = {("A", "B"): 0.5}
        coherency = {("A", "B"): 0.8}
        resource_usage = 0.4
        entropy = 0.5

        # Normal temperature
        F_normal = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature=1.0
        )

        # High temperature (system under stress)
        F_stress = system_free_energy(
            bonds, latencies, coherency, resource_usage, entropy, temperature=2.0
        )

        # Under stress, entropy effect is stronger
        assert F_stress < F_normal, "High temperature enhances entropy effect"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
