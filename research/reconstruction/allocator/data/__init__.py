# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Frozen demo fixture for the allocator pipeline (X-10R-1 PR #5).

This package ships a single TSV — ``mfi_demo.tsv`` — with a small
synthetic ECB-MFI-shaped registry (25 banks across 5 EU+EEA
countries) plus illustrative ``total_assets`` values. It is
*deliberately not real* — the purpose is to exercise the full
allocator pipeline (load → SizeWeightedPrior → CountryToBankAllocator
→ BankLevelGate5Audit) on a stable, license-clean fixture.

Real datasets (ECB MFI + EBA transparency + BankFocus) ship in
later epic PRs with their own license footprint.
"""

from pathlib import Path

DATA_DIR: Path = Path(__file__).resolve().parent

MFI_DEMO_TSV: Path = DATA_DIR / "mfi_demo.tsv"
"""Frozen demo TSV — 25 banks × 5 countries, illustrative
total_assets. Use ``load_mfi_registry(MFI_DEMO_TSV)`` to ingest."""


__all__ = ["DATA_DIR", "MFI_DEMO_TSV"]
