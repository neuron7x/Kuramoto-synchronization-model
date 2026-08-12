# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G9, G10 — risk_concentration_v2 filters noise + blocks Lehman headlines."""

from __future__ import annotations

import pandas as pd
import pytest

from tools.disha_artifact.risk_concentration_v2 import (
    EXPECTED_HONEST_HEADLINE_AT_BIS_LEHMAN,
    EXPECTED_NOISE_NODES_AT_BIS_LEHMAN,
    article_grade_countries_in_order,
    article_risk_score,
    excluded_low_mass_or_short_sample,
    filter_risk_concentration,
    lehman_pair_correlations_block_headline,
)


def _bis_like_table() -> pd.DataFrame:
    rows: list[tuple[str, float, int]] = [
        ("GB", 9_006_227.5, 11),
        ("US", 5_247_551.25, 11),
        ("DE", 4_428_127.0, 11),
        ("FR", 3_725_457.25, 11),
        ("LU", 1_687_000.75, 11),
        ("IE", 1_991_685.25, 11),
        ("NL", 2_116_424.0, 11),
        ("BE", 1_363_850.0, 11),
        ("CL", 31_051.0, 11),  # low mass — must be filtered
        ("MO", 18_182.5, 11),  # low mass
        ("JE", 699_868.5, 11),
        ("IM", 116_404.75, 11),
        ("TW", 151_879.25, 11),
        ("ES", 1_040_336.0, 0),  # zero out-strength → effective_n=0 → short sample
    ]
    df_rows: list[dict[str, float | int | str]] = []
    for cn, mass, eff in rows:
        df_rows.append(
            {
                "country": cn,
                "total_strength_lehman": float(mass),
                "binary_degree_lehman": 4,
                "delta_mean_abs_corr_changes_sensitivity": 0.3,
                "mean_abs_corr_changes_sensitivity": 0.5,
                "effective_change_observations": int(eff),
            }
        )
    return pd.DataFrame(df_rows)


def test_g9_filter_drops_low_mass_noise_nodes() -> None:
    """CL/MO must be excluded because total_strength < 100K."""
    df = filter_risk_concentration(_bis_like_table())
    excluded = set(excluded_low_mass_or_short_sample(df))
    # Mass-driven exclusions
    assert "CL" in excluded
    assert "MO" in excluded
    # ES excluded by short sample (effective_n=0)
    assert "ES" in excluded
    # JE at 700K, IM at 116K, TW at 152K — all above 100K threshold,
    # so they pass mass filter; the spec keeps them as borderline-but-grade.
    grade_set = set(article_grade_countries_in_order(df))
    assert "GB" in grade_set
    assert "DE" in grade_set
    assert "FR" in grade_set
    assert "LU" in grade_set
    assert "US" in grade_set


def test_g9_expected_lists_consistent() -> None:
    """The hard-coded BIS Lehman lists must reflect what the audit found."""
    assert "CL" in EXPECTED_NOISE_NODES_AT_BIS_LEHMAN
    assert "GB" in EXPECTED_HONEST_HEADLINE_AT_BIS_LEHMAN
    assert "DE" in EXPECTED_HONEST_HEADLINE_AT_BIS_LEHMAN


def test_g10_lehman_pairs_blocked_from_headline() -> None:
    pairs = pd.DataFrame(
        {
            "period": ["lehman", "sensitivity_2007Q1_2009Q4", "normal"],
            "country_i": ["A", "B", "C"],
            "country_j": ["X", "Y", "Z"],
            "pearson_r": [0.999, 0.9, 0.5],
            "headline_allowed": [True, True, True],
        }
    )
    out = lehman_pair_correlations_block_headline(pairs)
    assert not out.loc[out.period == "lehman", "headline_allowed"].any()
    assert out.loc[out.period == "sensitivity_2007Q1_2009Q4", "headline_allowed"].all()


def test_filter_rejects_missing_columns() -> None:
    bad = pd.DataFrame({"country": ["A"]})
    with pytest.raises(ValueError, match="missing columns"):
        filter_risk_concentration(bad)


def test_article_risk_score_is_finite() -> None:
    df = filter_risk_concentration(_bis_like_table())
    scores = article_risk_score(df)
    assert scores.notna().all()
