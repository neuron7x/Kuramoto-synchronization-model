from __future__ import annotations

import pytest

from core import energy


def test_compute_baseline_free_energy_is_positive():
    baseline = energy.compute_baseline_free_energy(samples=5, alpha=0.1)
    assert baseline > 0.0


def test_compute_baseline_free_energy_validates_inputs():
    with pytest.raises(ValueError):
        energy.compute_baseline_free_energy(samples=0)

    with pytest.raises(ValueError):
        energy.compute_baseline_free_energy(samples=5, alpha=0.0)


def test_energy_main_supports_baseline(capsys):
    energy.main(["--baseline", "--samples", "3", "--alpha", "0.1"])
    captured = capsys.readouterr()
    assert "baseline_F" in captured.out


def test_energy_main_verifies_invariant(capsys):
    F_old = 1.0e-6
    baseline_ema = 1.05e-6
    F_new = F_old + 0.5 * energy.compute_baseline_free_energy(samples=3, alpha=0.1)
    energy.main(
        [
            "--verify-invariant",
            "--F-old",
            f"{F_old}",
            "--F-new",
            f"{F_new}",
            "--baseline-ema",
            f"{baseline_ema}",
        ]
    )
    captured = capsys.readouterr()
    assert "invariant_hold=1" in captured.out
