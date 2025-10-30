"""Tests for gen_synth_amm_data.py script."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import csv
from pathlib import Path

from scripts import gen_synth_amm_data


def test_generate_amm_data_returns_correct_shapes() -> None:
    """Test that generate_amm_data returns arrays of the correct shape."""
    n = 100
    x, R, kappa, H = gen_synth_amm_data.generate_amm_data(n=n, seed=42)

    assert len(x) == n
    assert len(R) == n
    assert len(kappa) == n
    assert len(H) == n


def test_generate_amm_data_is_deterministic() -> None:
    """Test that the same seed produces the same output."""
    n = 100
    seed = 42

    x1, R1, kappa1, H1 = gen_synth_amm_data.generate_amm_data(n=n, seed=seed)
    x2, R2, kappa2, H2 = gen_synth_amm_data.generate_amm_data(n=n, seed=seed)

    assert (x1 == x2).all()
    assert (R1 == R2).all()
    assert (kappa1 == kappa2).all()
    assert (H1 == H2).all()


def test_write_csv_creates_file(tmp_path: Path) -> None:
    """Test that write_csv creates a CSV file with the correct content."""
    output_path = tmp_path / "test_amm.csv"
    n = 50
    seed = 7

    result_path = gen_synth_amm_data.write_csv(output_path, n=n, seed=seed)

    assert result_path == output_path
    assert output_path.exists()

    # Verify CSV content
    with output_path.open("r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Check header
    assert rows[0] == ["x", "R", "kappa", "H"]

    # Check number of data rows
    assert len(rows) == n + 1  # +1 for header


def test_write_csv_creates_parent_directory(tmp_path: Path) -> None:
    """Test that write_csv creates parent directories if they don't exist."""
    output_path = tmp_path / "subdir" / "nested" / "test_amm.csv"
    n = 10

    gen_synth_amm_data.write_csv(output_path, n=n, seed=1)

    assert output_path.exists()
    assert output_path.parent.exists()


def test_parse_args_defaults() -> None:
    """Test that parse_args returns correct defaults."""
    args = gen_synth_amm_data.parse_args([])

    assert args.output == gen_synth_amm_data.DEFAULT_OUTPUT_PATH
    assert args.num_samples == gen_synth_amm_data.DEFAULT_NUM_SAMPLES
    assert args.seed == gen_synth_amm_data.DEFAULT_SEED
    assert args.verbose is False


def test_parse_args_custom_values() -> None:
    """Test that parse_args correctly parses custom arguments."""
    args = gen_synth_amm_data.parse_args(
        ["-o", "custom.csv", "-n", "1000", "-s", "42", "-v"]
    )

    assert args.output == Path("custom.csv")
    assert args.num_samples == 1000
    assert args.seed == 42
    assert args.verbose is True


def test_main_success(tmp_path: Path, capsys) -> None:
    """Test that main returns 0 on success and prints output path."""
    output_path = tmp_path / "test_output.csv"

    exit_code = gen_synth_amm_data.main(["-o", str(output_path), "-n", "10", "-s", "1"])

    assert exit_code == 0
    assert output_path.exists()

    captured = capsys.readouterr()
    assert str(output_path) in captured.out


def test_main_with_verbose_logging(tmp_path: Path) -> None:
    """Test that verbose flag is accepted without error."""
    output_path = tmp_path / "verbose_test.csv"

    exit_code = gen_synth_amm_data.main(
        ["-o", str(output_path), "-n", "10", "-s", "1", "-v"]
    )

    assert exit_code == 0
    assert output_path.exists()


def test_regime_transition() -> None:
    """Test that data exhibits regime transition at midpoint."""
    n = 200
    seed = 42

    x, R, kappa, H = gen_synth_amm_data.generate_amm_data(n=n, seed=seed)

    # First half should have different characteristics than second half
    first_half_R = R[: n // 2]
    second_half_R = R[n // 2 :]

    # R values should be higher in second half on average
    assert first_half_R.mean() < second_half_R.mean()

    # kappa should change sign between regimes
    first_half_kappa = kappa[: n // 2]
    second_half_kappa = kappa[n // 2 :]

    assert first_half_kappa.mean() > 0
    assert second_half_kappa.mean() < 0
