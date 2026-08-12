# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the synthetic panel generator and the CLI entry point."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import numpy as np
import pytest

from research.systemic_risk.cli import main
from research.systemic_risk.synthetic import (
    SyntheticPanelConfig,
    generate_panel,
)


class TestSynthetic:
    def test_default_panel_shape_and_keys(self) -> None:
        panels, labels = generate_panel()
        cfg = SyntheticPanelConfig()
        assert len(panels) == cfg.n_days
        assert len(labels) == cfg.n_banks
        for k, v in panels.items():
            assert v.shape == (cfg.n_banks, cfg.n_banks)
            assert v.dtype == np.float64

    def test_panel_satisfies_firewall_gates_2_to_7(self) -> None:
        panels, _ = generate_panel(SyntheticPanelConfig(n_banks=12, n_days=10))
        for d, m in panels.items():
            # No NaN/Inf, no negatives, zero diagonal, at least one non-zero.
            assert np.all(np.isfinite(m))
            assert np.all(m >= 0)
            assert np.all(np.diagonal(m) == 0.0)
            assert np.any(m != 0.0)

    def test_seed_reproducibility(self) -> None:
        cfg = SyntheticPanelConfig(seed=12345, n_banks=10, n_days=5)
        p_a, _ = generate_panel(cfg)
        p_b, _ = generate_panel(cfg)
        for d in p_a:
            assert np.array_equal(p_a[d], p_b[d])

    def test_invalid_n_banks(self) -> None:
        with pytest.raises(ValueError, match="n_banks"):
            generate_panel(SyntheticPanelConfig(n_banks=2))

    def test_invalid_density(self) -> None:
        with pytest.raises(ValueError, match="density"):
            generate_panel(SyntheticPanelConfig(density=1.5))


class TestCLI:
    def test_evaluate_synthetic_clean_run(self) -> None:
        # Capture JSON stdout and check structure.
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main(
                [
                    "evaluate",
                    "--claim-id",
                    "CLAIM_TEST",
                    "--data",
                    "synthetic",
                    "--seed",
                    "42",
                    "--n-banks",
                    "8",
                    "--n-days",
                    "5",
                ]
            )
        assert rc == 0
        report = json.loads(buf.getvalue())
        assert report["claim_id"] == "CLAIM_TEST"
        assert report["data_source"] == "synthetic"
        assert report["n_banks"] == 8
        assert report["n_days"] == 5
        # Without provenance the firewall fails G8 → STOP, tier stays IDEA.
        assert report["last_action"] == "STOP"
        assert report["tier_name"] == "IDEA"
        # Gate log should have all 8 gates reported.
        assert len(report["firewall_gate_log"]) == 8

    def test_help_returns_nonzero_when_no_subcommand(self) -> None:
        with pytest.raises(SystemExit):
            # argparse exits with a non-zero code when required subcommand
            # is missing.
            main([])

    def test_unknown_data_source_rejected(self) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "evaluate",
                    "--claim-id",
                    "X",
                    "--data",
                    "real",  # not in allowed choices
                ]
            )
