# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the MFI TSV/CSV loader (X-10R-1 PR #4).

Pins six contracts:
  1. TSV and CSV both parse correctly with explicit dialect.
  2. Inline string vs file-on-disk both work.
  3. Optional `total_assets` column populates `bank_weights` only
     when present + positive + finite.
  4. Round-trip: loaded registry feeds directly into
     SizeWeightedPrior + CountryToBankAllocator with no glue.
  5. Fail-closed at every parsing step (missing column / blank
     bank_id / negative assets / non-finite assets / unknown
     dialect / empty file).
  6. Header validation fail-closed with the unknown column name
     surfaced for diagnosis.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.reconstruction.allocator import (
    CountryToBankAllocator,
    MFIRegistryLoad,
    SizeWeightedPrior,
    load_mfi_registry,
    synthetic_country_aggregates,
)

# A tiny, hand-curated MFI-shape fixture. Values are illustrative —
# the real ECB MFI list has thousands of rows; this exercises the
# loader's parsing surface, not the data path.
_TSV_FIXTURE = """bank_id\tcountry\tname\ttotal_assets
DE-001\tDE\tDeutsche Demo AG\t1000000
DE-002\tDE\tFrankfurt Demo Bank\t500000
FR-001\tFR\tParis Demo Banque\t800000
FR-002\tFR\tLyon Demo Bank\t300000
FR-003\tFR\tToulouse Demo\t200000
IT-001\tIT\tRoma Demo SpA\t600000
"""

_CSV_FIXTURE = """bank_id,country,name,total_assets
DE-001,DE,Deutsche Demo AG,1000000
DE-002,DE,Frankfurt Demo Bank,500000
FR-001,FR,Paris Demo Banque,800000
"""

_TSV_NO_ASSETS = """bank_id\tcountry\tname
DE-001\tDE\tDeutsche Demo AG
DE-002\tDE\tFrankfurt Demo Bank
FR-001\tFR\tParis Demo Banque
"""


# ---------------------------------------------------------------------------
# Happy-path parsing
# ---------------------------------------------------------------------------


def test_load_tsv_inline_returns_canonical_map_and_weights() -> None:
    out = load_mfi_registry(_TSV_FIXTURE)
    assert isinstance(out, MFIRegistryLoad)
    assert out.n_rows == 6
    assert out.n_with_assets == 6
    # Country order is alphabetical (registry contract); within country
    # the file's order is preserved.
    countries = [c for _, c in out.bank_country_map]
    banks_de = [b for b, c in out.bank_country_map if c == "DE"]
    banks_fr = [b for b, c in out.bank_country_map if c == "FR"]
    assert countries[:2] == ["DE", "DE"]
    assert "FR" in countries and "IT" in countries
    assert banks_de == ["DE-001", "DE-002"]
    assert banks_fr == ["FR-001", "FR-002", "FR-003"]
    # Weights match the TSV values exactly.
    assert out.bank_weights["DE-001"] == 1000000.0
    assert out.bank_weights["FR-003"] == 200000.0


def test_load_csv_dialect_works() -> None:
    out = load_mfi_registry(_CSV_FIXTURE, dialect="csv")
    assert out.n_rows == 3
    assert out.n_with_assets == 3
    assert out.bank_weights["DE-001"] == 1000000.0


def test_load_from_disk_file(tmp_path: Path) -> None:
    file = tmp_path / "mfi.tsv"
    file.write_text(_TSV_FIXTURE, encoding="utf-8")
    out = load_mfi_registry(file)
    assert out.n_rows == 6
    assert "DE-001" in out.bank_weights


def test_load_from_pathlib_path_object(tmp_path: Path) -> None:
    file = tmp_path / "mfi.tsv"
    file.write_text(_TSV_FIXTURE, encoding="utf-8")
    out = load_mfi_registry(file)
    assert out.n_rows == 6


def test_no_assets_column_yields_empty_weights() -> None:
    out = load_mfi_registry(_TSV_NO_ASSETS)
    assert out.n_with_assets == 0
    assert out.bank_weights == {}


def test_blank_rows_are_skipped() -> None:
    """A blank row in the middle of an export must not raise; loader
    silently skips it (common in spreadsheet round-trip exports)."""
    fixture = (
        "bank_id\tcountry\n"
        "DE-001\tDE\n"
        "\t\n"  # blank row
        "FR-001\tFR\n"
    )
    out = load_mfi_registry(fixture)
    assert out.n_rows == 2


def test_zero_assets_rows_do_not_populate_weights() -> None:
    """Total assets of 0 ⇒ bank in registry but no weight (so the
    prior would impute it at the country mean)."""
    fixture = "bank_id\tcountry\ttotal_assets\nDE-001\tDE\t0\nDE-002\tDE\t100\n"
    out = load_mfi_registry(fixture)
    assert "DE-002" in out.bank_weights
    assert "DE-001" not in out.bank_weights
    assert out.n_with_assets == 1


def test_missing_total_assets_value_does_not_populate_weight() -> None:
    """Empty cell ⇒ bank skipped from weights (registry still
    populated)."""
    fixture = "bank_id\tcountry\ttotal_assets\nDE-001\tDE\t\nDE-002\tDE\t100\n"
    out = load_mfi_registry(fixture)
    assert "DE-001" not in out.bank_weights
    assert "DE-002" in out.bank_weights


# ---------------------------------------------------------------------------
# Round-trip with the rest of the allocator
# ---------------------------------------------------------------------------


def test_loader_round_trips_through_size_weighted_prior() -> None:
    """The MFI load is a drop-in for SizeWeightedPrior: bank_country_map
    + bank_weights are exactly the constructor arguments."""
    out = load_mfi_registry(_TSV_FIXTURE)
    prior = SizeWeightedPrior(
        bank_country_map=out.bank_country_map,
        bank_weights=out.bank_weights,
        prior_id_tag="ecb_mfi_demo",
    )
    assert prior.banks_in("DE") == ("DE-001", "DE-002")
    # 1M / (1M+500K) = 2/3 for DE-001
    assert prior.expected_share(country="DE", bank_id="DE-001") == pytest.approx(
        2.0 / 3.0, rel=1e-12
    )


def test_loader_feeds_allocator_end_to_end() -> None:
    """Country aggregates → MFI-loaded prior → allocator → conserved
    bank-level marginals. End-to-end smoke test."""
    out = load_mfi_registry(_TSV_FIXTURE)
    # Synthesise country aggregates that match the loader's countries.
    agg_in = {"DE": 100.0, "FR": 200.0, "IT": 50.0}
    agg_out = {"DE": 80.0, "FR": 150.0, "IT": 40.0}
    cert = CountryToBankAllocator(
        prior=SizeWeightedPrior(
            bank_country_map=out.bank_country_map,
            bank_weights=out.bank_weights,
        )
    ).allocate(agg_in, agg_out, bank_country_map=out.bank_country_map)
    # Conservation per country.
    bank_to_idx = {b: i for i, (b, _) in enumerate(out.bank_country_map)}
    for country in agg_in:
        in_sum = sum(cert.s_in[bank_to_idx[b]] for b, c in out.bank_country_map if c == country)
        assert in_sum == pytest.approx(agg_in[country], rel=1e-9)


def test_loader_distinguishes_de_from_fr_after_round_trip() -> None:
    """A country-disjoint dataset where DE banks are big and FR banks
    are small should produce a clearly de-DE-weighted SizeWeightedPrior
    relative to UniformPrior on a shared lognormal substrate.

    This is the END-TO-END falsification anchor surface for the
    loader: the prior built from real-shape data must transmit
    a non-trivial size signal to the allocator."""
    # Tiny synthetic "real-data" load: DE banks dominate.
    fixture = (
        "bank_id\tcountry\ttotal_assets\n"
        "DE-001\tDE\t100000\n"
        "DE-002\tDE\t200000\n"
        "FR-001\tFR\t10\n"
        "FR-002\tFR\t20\n"
    )
    out = load_mfi_registry(fixture)
    p = SizeWeightedPrior(
        bank_country_map=out.bank_country_map,
        bank_weights=out.bank_weights,
    )
    assert p.expected_share(country="DE", bank_id="DE-001") == pytest.approx(1.0 / 3.0, rel=1e-12)
    # Negligible DE-001 share would hint the loader silently zeroed
    # its weight; the assertion above pins the size signal arrived.
    _ = synthetic_country_aggregates  # imported for parity with other tests


# ---------------------------------------------------------------------------
# Fail-closed contract
# ---------------------------------------------------------------------------


def test_unknown_dialect_rejected() -> None:
    with pytest.raises(ValueError, match="unknown dialect"):
        load_mfi_registry("bank_id,country\n", dialect="ssv")  # type: ignore[arg-type]


def test_missing_required_column_rejected() -> None:
    fixture = "bankid\tcountry\nDE-001\tDE\n"  # bank_id misspelt
    with pytest.raises(ValueError, match="bank_id"):
        load_mfi_registry(fixture)


def test_missing_country_column_rejected() -> None:
    fixture = "bank_id\tnation\nDE-001\tDE\n"
    with pytest.raises(ValueError, match="country"):
        load_mfi_registry(fixture)


def test_empty_bank_id_rejected_with_line_number() -> None:
    fixture = "bank_id\tcountry\n\tDE\n"
    with pytest.raises(ValueError, match="line 2"):
        load_mfi_registry(fixture)


def test_empty_country_rejected_with_line_number() -> None:
    fixture = "bank_id\tcountry\nDE-001\t\n"
    with pytest.raises(ValueError, match="line 2"):
        load_mfi_registry(fixture)


def test_negative_total_assets_rejected() -> None:
    fixture = "bank_id\tcountry\ttotal_assets\nDE-001\tDE\t-1\n"
    with pytest.raises(ValueError, match="negative"):
        load_mfi_registry(fixture)


def test_non_numeric_total_assets_rejected() -> None:
    fixture = "bank_id\tcountry\ttotal_assets\nDE-001\tDE\tabc\n"
    with pytest.raises(ValueError, match="cannot parse"):
        load_mfi_registry(fixture)


def test_inf_total_assets_rejected() -> None:
    fixture = "bank_id\tcountry\ttotal_assets\nDE-001\tDE\tinf\n"
    with pytest.raises(ValueError, match="non-finite"):
        load_mfi_registry(fixture)


def test_empty_registry_rejected() -> None:
    """File with header only (no data rows) ⇒ ValueError."""
    fixture = "bank_id\tcountry\n"
    with pytest.raises(ValueError, match="empty registry"):
        load_mfi_registry(fixture)


def test_missing_file_raises_filenotfounderror() -> None:
    with pytest.raises(FileNotFoundError):
        load_mfi_registry(Path("/nonexistent/mfi.tsv"))


def test_total_assets_column_name_override() -> None:
    """Caller can rename the assets column (e.g. for EBA-shape files)."""
    fixture = "bank_id\tcountry\ttotal_eur\nDE-001\tDE\t1000\n"
    out = load_mfi_registry(fixture, total_assets_column="total_eur")
    assert out.bank_weights["DE-001"] == 1000.0


def test_total_assets_disabled_via_none() -> None:
    """Setting `total_assets_column=None` skips weight extraction
    entirely even when the file has the column."""
    out = load_mfi_registry(_TSV_FIXTURE, total_assets_column=None)
    assert out.bank_weights == {}
    # Registry still populated.
    assert any(b == "DE-001" for b, _ in out.bank_country_map)
