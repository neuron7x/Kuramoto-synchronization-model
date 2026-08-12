# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""risk_concentration_v2 — strength-weighted, observation-filtered ranking.

Closes G9, G10:
* Removes {CL, MO, JE, IM, TW} when total_strength < min_total_strength
  AND/OR when sensitivity-window effective_n < threshold.
* Forces headline_allowed=False on every Lehman 4-quarter pair.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_HONEST_HEADLINE_OBS: int = 8
_HONEST_NEAR_PERFECT_R: float = 0.98


@dataclass(frozen=True)
class FilteredRow:
    country: str
    total_strength: float
    binary_degree: int
    delta_mean_abs_corr_changes_sensitivity: float
    effective_change_observations_sensitivity: int
    article_grade: bool
    headline_allowed: bool
    suspect_low_mass: bool
    suspect_short_sample: bool
    suspect_near_perfect: bool


def filter_risk_concentration(
    rc_df: pd.DataFrame,
    *,
    min_total_strength: float = 100_000.0,
    min_effective_n_sensitivity: int = _HONEST_HEADLINE_OBS,
) -> pd.DataFrame:
    """Filter / annotate the risk concentration table.

    Required input columns:
      country, total_strength_lehman, binary_degree_lehman,
      delta_mean_abs_corr_changes_sensitivity,
      mean_abs_corr_changes_sensitivity,
      effective_change_observations.
    """
    required = {
        "country",
        "total_strength_lehman",
        "binary_degree_lehman",
        "delta_mean_abs_corr_changes_sensitivity",
        "mean_abs_corr_changes_sensitivity",
        "effective_change_observations",
    }
    missing = required - set(rc_df.columns)
    if missing:
        raise ValueError(f"risk_concentration df missing columns: {sorted(missing)}")
    df = rc_df.copy()
    df["suspect_low_mass"] = df["total_strength_lehman"] < min_total_strength
    df["suspect_short_sample"] = df["effective_change_observations"] < min_effective_n_sensitivity
    df["suspect_near_perfect"] = (
        df["mean_abs_corr_changes_sensitivity"].abs() >= _HONEST_NEAR_PERFECT_R
    )
    df["article_grade"] = (
        ~df["suspect_low_mass"] & ~df["suspect_short_sample"] & ~df["suspect_near_perfect"]
    )
    df["headline_allowed"] = df["article_grade"]
    return df


def lehman_pair_correlations_block_headline(
    pairs_df: pd.DataFrame,
) -> pd.DataFrame:
    """Force headline_allowed=False on every Lehman-only 4-quarter pair.

    Required column ``period``. Adds/overwrites ``headline_allowed``.
    """
    if "period" not in pairs_df.columns:
        raise ValueError("pairs_df missing 'period' column")
    df = pairs_df.copy()
    if "headline_allowed" not in df.columns:
        df["headline_allowed"] = True
    df.loc[df["period"].astype(str).str.lower() == "lehman", "headline_allowed"] = False
    return df


def select_article_grade_rows(rc_df: pd.DataFrame) -> pd.DataFrame:
    return rc_df[rc_df["article_grade"]].copy().reset_index(drop=True)


def excluded_low_mass_or_short_sample(rc_df: pd.DataFrame) -> list[str]:
    """Countries dropped from headline by either filter."""
    mask = rc_df["suspect_low_mass"] | rc_df["suspect_short_sample"]
    return sorted(rc_df.loc[mask, "country"].astype(str).tolist())


def article_grade_countries_in_order(rc_df: pd.DataFrame) -> list[str]:
    """Sensitivity-window-Δ-sorted article-grade countries, descending."""
    grade = select_article_grade_rows(rc_df)
    if grade.empty:
        return []
    grade = grade.sort_values(
        ["delta_mean_abs_corr_changes_sensitivity", "total_strength_lehman"],
        ascending=[False, False],
    )
    return grade["country"].astype(str).tolist()


# Empirical lists kept for explicit checking (G9).
EXPECTED_NOISE_NODES_AT_BIS_LEHMAN: tuple[str, ...] = (
    "CL",
    "MO",
    "JE",
    "IM",
    "TW",
)
EXPECTED_HONEST_HEADLINE_AT_BIS_LEHMAN: tuple[str, ...] = (
    "GB",
    "DE",
    "FR",
    "LU",
    "US",
    "IE",
    "NL",
    "BE",
)


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if sd is None or float(sd) == 0.0 or pd.isna(sd):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / float(sd)


def article_risk_score(rc_df: pd.DataFrame) -> pd.Series:
    """Strength-weighted, penalty-aware risk score per country.

    score = z(Δ|r|_sens) + z(log_strength) + z(degree)
            − 2·short_sample_penalty − 2·low_mass_penalty
    """
    z_delta = _zscore(rc_df["delta_mean_abs_corr_changes_sensitivity"]).fillna(0.0)
    z_logmass = _zscore(np.log1p(rc_df["total_strength_lehman"].astype(float))).fillna(0.0)
    z_deg = _zscore(rc_df["binary_degree_lehman"].astype(float)).fillna(0.0)
    pen_obs = rc_df["suspect_short_sample"].astype(float)
    pen_mass = rc_df["suspect_low_mass"].astype(float)
    return z_delta + z_logmass + z_deg - 2.0 * pen_obs - 2.0 * pen_mass
