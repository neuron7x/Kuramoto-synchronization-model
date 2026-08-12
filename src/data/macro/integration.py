# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Helpers to align macro features with market datasets."""

from __future__ import annotations

from typing import Literal

import pandas as pd

__all__ = ["integrate_macro_features"]


def integrate_macro_features(
    market_data: pd.DataFrame,
    macro_features: pd.DataFrame,
    *,
    on: str = "timestamp",
    macro_time_column: str = "period_end",
    allow_future_leakage: bool = False,
    direction: Literal["backward", "forward"] = "backward",
) -> pd.DataFrame:
    """Merge macroeconomic features into the supplied market data frame.

    Parameters
    ----------
    market_data:
        Data frame containing the existing market data.  ``on`` must be present.
    macro_features:
        Engineered macro feature frame produced by :class:`MacroFeatureBuilder`.
    on:
        Name of the timestamp column in ``market_data`` used for alignment.
    macro_time_column:
        Column in ``macro_features`` used as the merge key.
    allow_future_leakage:
        When ``False`` (default) uses a backward-looking merge ensuring only
        information released on or before the market timestamp is used.
    direction:
        Direction parameter forwarded to :func:`pandas.merge_asof`.
    """

    if market_data.empty:
        return macro_features.copy()
    if macro_features.empty:
        return market_data.copy()

    use_indicator_grouping = (
        "indicator" in market_data.columns and "indicator" in macro_features.columns
    )

    if use_indicator_grouping:
        market = market_data.sort_values(["indicator", on]).reset_index(drop=True)
        macro = macro_features.sort_values(
            ["indicator", macro_time_column]
        ).reset_index(drop=True)
    else:
        market = market_data.sort_values(on).reset_index(drop=True)
        macro = macro_features.sort_values(macro_time_column).reset_index(drop=True)

    merged = pd.merge_asof(
        market,
        macro,
        left_on=on,
        right_on=macro_time_column,
        direction=direction,
        by="indicator" if use_indicator_grouping else None,
    )
    if not allow_future_leakage:
        timing_column = None
        if "available_at" in merged.columns:
            timing_column = "available_at"
        elif "release_date" in merged.columns:
            timing_column = "release_date"

        if timing_column is not None:
            macro_columns = [
                col
                for col in merged.columns
                if col not in market.columns
                or col
                in {"release_date", "available_at", macro_time_column, "indicator"}
            ]
            mask = merged[timing_column].notna() & (merged[timing_column] > merged[on])
            merged.loc[mask, macro_columns] = pd.NA
    return merged
