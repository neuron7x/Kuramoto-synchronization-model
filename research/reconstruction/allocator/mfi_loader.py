# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""TSV / CSV loader for the ECB-MFI-style bank registry shape.

Per X-10R-1 PR #4 (epic #638), the registry layer needs a real-data
ingestion path. ECB Monetary Financial Institutions list is published
as a CSV/TSV with one row per bank, columns including (at minimum):

    bank_id     unique identifier (LEI or ECB MFI ID)
    country     ISO 3166-1 alpha-2 code

…and optionally:

    name              human-readable bank name (informational)
    total_assets      EUR-denominated bank-size signal (used by
                      SizeWeightedPrior when the consumer wants
                      EBA-style size weights from the same TSV)

This loader is **format-aware** but **data-agnostic**: it parses the
TSV/CSV shape into the canonical `bank_country_map` tuple and
optional `bank_weights` mapping, no hardcoded data. A subsequent
PR plugs the actual ECB MFI download path into this loader; that
PR will live under `research/reconstruction/allocator/data/` (or
similar) and is out of scope here. This PR ships only the loader
contract + a tiny unit-test fixture.

The loader is intentionally pure-stdlib (csv module). No pandas,
no external deps. Fail-closed at every parsing step: blank rows,
missing columns, non-finite assets ⇒ ValueError with line number.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from research.reconstruction.allocator.registry import (
    registry_to_bank_country_map,
)

DialectName = Literal["tsv", "csv"]


@dataclass(frozen=True)
class MFIRegistryLoad:
    """Result of loading an MFI-style file.

    Attributes
    ----------
    bank_country_map:
        Canonical deterministic ``(bank_id, country)`` tuple.
    bank_weights:
        Mapping ``{bank_id -> total_assets}`` for rows that carried
        a positive ``total_assets`` value. Empty dict if the file
        had no assets column or every value was missing/zero.
    n_rows:
        Total non-empty rows seen.
    n_with_assets:
        Rows that contributed to ``bank_weights``.
    """

    bank_country_map: tuple[tuple[str, str], ...]
    bank_weights: dict[str, float]
    n_rows: int
    n_with_assets: int


_DIALECTS = {"tsv": "\t", "csv": ","}


def load_mfi_registry(
    source: str | Path,
    *,
    dialect: DialectName = "tsv",
    bank_id_column: str = "bank_id",
    country_column: str = "country",
    total_assets_column: str | None = "total_assets",
) -> MFIRegistryLoad:
    """Parse an ECB-MFI-style TSV/CSV into the allocator's canonical
    registry + optional size weights.

    Parameters
    ----------
    source:
        Either a path to the TSV/CSV file OR an in-memory string of
        the file contents (auto-detected: a string with a newline is
        treated as in-memory contents).
    dialect:
        ``"tsv"`` (default; tab-separated) or ``"csv"`` (comma-separated).
    bank_id_column / country_column:
        Names of the columns carrying the bank identifier and the ISO
        country code, respectively. Defaulted to ECB-MFI conventions.
    total_assets_column:
        Optional. If the file has this column AND the value is a
        positive finite number, the row contributes to ``bank_weights``.
        Set to ``None`` to skip size-weight extraction entirely.

    Returns
    -------
    MFIRegistryLoad with the canonical map + assembled weights.
    """
    if dialect not in _DIALECTS:
        raise ValueError(f"unknown dialect {dialect!r}; expected 'tsv' or 'csv'")
    delimiter = _DIALECTS[dialect]

    # Treat strings containing a newline as in-memory contents; everything
    # else as a path. This matches stdlib `csv` ergonomics.
    text: str
    if isinstance(source, str) and "\n" in source:
        text = source
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"MFI source file not found: {path}")
        text = path.read_text(encoding="utf-8")

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise ValueError("MFI file has no header row")
    if bank_id_column not in reader.fieldnames:
        raise ValueError(
            f"MFI file is missing required column {bank_id_column!r}; "
            f"available: {reader.fieldnames}"
        )
    if country_column not in reader.fieldnames:
        raise ValueError(
            f"MFI file is missing required column {country_column!r}; "
            f"available: {reader.fieldnames}"
        )

    registry: dict[str, list[str]] = {}
    weights: dict[str, float] = {}
    n_rows = 0
    n_with_assets = 0
    for line_idx, row in enumerate(reader, start=2):
        # All-empty / blank rows: skip silently (common in spreadsheet exports).
        if not any((v or "").strip() for v in row.values()):
            continue
        n_rows += 1
        bank_id = (row.get(bank_id_column) or "").strip()
        country = (row.get(country_column) or "").strip()
        if not bank_id:
            raise ValueError(f"MFI file line {line_idx}: empty {bank_id_column!r}")
        if not country:
            raise ValueError(
                f"MFI file line {line_idx}: empty {country_column!r} for bank {bank_id!r}"
            )
        registry.setdefault(country, []).append(bank_id)

        if total_assets_column and total_assets_column in (reader.fieldnames or []):
            raw = (row.get(total_assets_column) or "").strip()
            if raw:
                try:
                    val = float(raw)
                except ValueError as e:
                    raise ValueError(
                        f"MFI file line {line_idx}: cannot parse "
                        f"{total_assets_column!r}={raw!r} as float for "
                        f"bank {bank_id!r}"
                    ) from e
                if not (val == val) or val == float("inf") or val == float("-inf"):
                    raise ValueError(
                        f"MFI file line {line_idx}: non-finite "
                        f"{total_assets_column!r}={raw!r} for bank {bank_id!r}"
                    )
                if val < 0:
                    raise ValueError(
                        f"MFI file line {line_idx}: negative "
                        f"{total_assets_column!r}={val} for bank {bank_id!r}"
                    )
                if val > 0:
                    weights[bank_id] = val
                    n_with_assets += 1

    if not registry:
        raise ValueError("MFI file produced an empty registry (no rows parsed)")

    bcm = registry_to_bank_country_map(registry)
    return MFIRegistryLoad(
        bank_country_map=bcm,
        bank_weights=weights,
        n_rows=n_rows,
        n_with_assets=n_with_assets,
    )
