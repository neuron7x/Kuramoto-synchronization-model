# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for stakeholder asset generation hygiene."""

from __future__ import annotations

import csv

from scripts import generate_stakeholder_assets as gen


def test_build_entries_contains_no_tbd_tokens() -> None:
    entries = gen.build_entries()
    gen.assert_no_placeholders(entries)
    for entry in entries:
        serialized = " ".join(
            [
                entry.name,
                entry.role,
                entry.interests,
                entry.expectations,
                entry.channels,
                entry.frequency,
                entry.power,
            ]
        )
        assert "TBD" not in serialized
        assert "TODO" not in serialized


def test_written_matrix_contains_no_tbd_tokens(tmp_path) -> None:
    entries = [
        gen.StakeholderEntry(
            name="Data Protection Officer",
            role="DPIA coordination",
            interests="Regulatory compliance",
            influence=4,
            expectations="Sign regulatory responses",
            channels="Regulatory channels",
            frequency="Pre-launch",
            power="High",
            interest_level=4,
            sources=[gen.SourceRef("pattern-A", "test")],
        )
    ]
    gen.assert_no_placeholders(entries)

    source_lines = ["## A", "pattern-A"]
    section_index = gen.build_section_index(source_lines)

    matrix_path = tmp_path / "matrix.csv"
    gen.write_matrix(entries, source_lines, section_index, matrix_path)

    with matrix_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    assert rows
    for row in rows:
        packed = " ".join(str(value) for value in row.values())
        assert "TBD" not in packed
        assert "TODO" not in packed
