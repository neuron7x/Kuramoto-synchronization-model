# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Causal guard using Transfer Entropy for GeoSync Neuro-Architecture.

This module implements Transfer Entropy calculation for detecting causal
relationships between market variables, with optional statsmodels integration.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

if TYPE_CHECKING:
    from pandas import DataFrame

__all__ = ["CausalGuard", "CausalResult"]

logger = logging.getLogger(__name__)

# Try to import statsmodels for Granger causality tests
try:
    from statsmodels.tsa.stattools import grangercausalitytests

    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    logger.warning(
        "statsmodels not available - CausalGuard will use histogram-based TE only. "
        "Install with: pip install 'geosync[neuro_advanced]'"
    )


class CausalResult:
    """Result from causal analysis.

    Attributes
    ----------
    TE_pass : bool
        Whether the causal test passed
    """

    def __init__(self, TE_pass: bool):
        self.TE_pass = TE_pass


class CausalGuard:
    """Transfer Entropy and causality testing.

    Detects causal relationships between a target variable and potential
    drivers using Transfer Entropy (histogram-based) and optionally
    Granger causality tests.

    Parameters
    ----------
    max_lag : int, optional
        Maximum lag to test for causality, by default 5
    n_bins : int, optional
        Number of bins for histogram-based TE, by default 10
    te_threshold : float, optional
        Minimum TE value to pass test, by default 0.01
    granger_alpha : float, optional
        Significance level for Granger test, by default 0.05
    """

    def __init__(
        self,
        max_lag: int = 5,
        n_bins: int = 10,
        te_threshold: float = 0.01,
        granger_alpha: float = 0.05,
    ):
        self.max_lag = max_lag
        self.n_bins = n_bins
        self.te_threshold = te_threshold
        self.granger_alpha = granger_alpha

    def fit_transform(self, df: DataFrame, target: str) -> dict[str, bool]:
        """Test causality from features to target.

        Parameters
        ----------
        df : DataFrame
            Data with target and potential driver columns
        target : str
            Name of target column

        Returns
        -------
        dict
            Dictionary with key 'TE_pass': bool
        """
        if target not in df.columns:
            raise ValueError(f"Target '{target}' not found in DataFrame columns")

        if len(df) < self.max_lag * 3:
            logger.warning(
                f"Insufficient data for CausalGuard: got {len(df)}, "
                f"need at least {self.max_lag * 3}. Returning TE_pass=False"
            )
            return {"TE_pass": False}

        if not is_numeric_dtype(df[target]):
            raise ValueError("Target series must be numeric for causal analysis")

        # Get target series
        target_series = df[target].astype(float)

        # Get potential drivers (all other columns)
        driver_frame = df.drop(columns=[target])
        numeric_drivers = driver_frame.select_dtypes(include=[np.number])
        drivers = list(numeric_drivers.columns)

        if not drivers:
            logger.warning("No numeric driver variables found. Returning TE_pass=False")
            return {"TE_pass": False}

        # Compute TE from each numeric driver to target
        te_values = []
        for driver_col in drivers:
            te = self._transfer_entropy(numeric_drivers[driver_col], target_series)
            te_values.append(te)

        # Check if any driver passes threshold
        max_te = max(te_values) if te_values else 0.0

        # Optionally run Granger test for confirmation
        granger_pass = False
        if HAS_STATSMODELS and max_te > self.te_threshold:
            granger_pass = self._granger_test(df, target, drivers)

        # Pass if TE threshold met (and Granger confirms if available)
        if HAS_STATSMODELS:
            TE_pass = max_te > self.te_threshold and granger_pass
        else:
            TE_pass = max_te > self.te_threshold

        return {"TE_pass": TE_pass}

    def _transfer_entropy(self, source: pd.Series, target: pd.Series) -> float:
        """Compute Transfer Entropy from source to target.

        TE(X→Y) = H(Y_t | Y_t-1) - H(Y_t | Y_t-1, X_t-1)

        Uses histogram-based estimation.
        """
        # Ensure no NaN values
        source = source.ffill().bfill()
        target = target.ffill().bfill()

        # Create lagged versions
        target_t = target.values[1:]
        target_t_1 = target.values[:-1]
        source_t_1 = source.values[:-1]

        # Discretize into bins
        target_t_binned = self._discretize(target_t)
        target_t_1_binned = self._discretize(target_t_1)
        source_t_1_binned = self._discretize(source_t_1)

        # Compute conditional entropies for TE
        H_Y_t_Y_t_1 = self._conditional_entropy(target_t_binned, target_t_1_binned)
        H_Y_t_Y_t_1_X_t_1 = self._conditional_entropy_2(
            target_t_binned, target_t_1_binned, source_t_1_binned
        )

        # TE = I(Y_t; X_t-1 | Y_t-1) = H(Y_t | Y_t-1) - H(Y_t | Y_t-1, X_t-1)
        te = H_Y_t_Y_t_1 - H_Y_t_Y_t_1_X_t_1

        return float(max(te, 0.0))  # TE should be non-negative

    def _discretize(self, x: np.ndarray) -> np.ndarray:
        """Discretize continuous values into bins."""
        bins = np.linspace(x.min(), x.max() + 1e-10, self.n_bins + 1)
        return np.digitize(x, bins) - 1

    def _entropy(self, x: np.ndarray) -> float:
        """Compute Shannon entropy H(X)."""
        _, counts = np.unique(x, return_counts=True)
        probs = counts / len(x)
        return float(-np.sum(probs * np.log2(probs + 1e-10)))

    def _conditional_entropy(self, y: np.ndarray, x: np.ndarray) -> float:
        """Compute conditional entropy H(Y|X)."""
        # H(Y|X) = H(Y,X) - H(X)
        joint = self._joint_entropy(y, x)
        marginal = self._entropy(x)
        return joint - marginal

    def _conditional_entropy_2(self, y: np.ndarray, x1: np.ndarray, x2: np.ndarray) -> float:
        """Compute conditional entropy H(Y|X1,X2)."""
        # H(Y|X1,X2) = H(Y,X1,X2) - H(X1,X2)
        joint_3 = self._joint_entropy_3(y, x1, x2)
        joint_2 = self._joint_entropy(x1, x2)
        return joint_3 - joint_2

    def _joint_entropy(self, x: np.ndarray, y: np.ndarray) -> float:
        """Compute joint entropy H(X,Y)."""
        xy = np.column_stack([x, y])
        unique_rows, counts = np.unique(xy, axis=0, return_counts=True)
        probs = counts / len(xy)
        return float(-np.sum(probs * np.log2(probs + 1e-10)))

    def _joint_entropy_3(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> float:
        """Compute joint entropy H(X,Y,Z)."""
        xyz = np.column_stack([x, y, z])
        unique_rows, counts = np.unique(xyz, axis=0, return_counts=True)
        probs = counts / len(xyz)
        return float(-np.sum(probs * np.log2(probs + 1e-10)))

    def _granger_test(self, df: DataFrame, target: str, drivers: list[str]) -> bool:
        """Run Granger causality tests.

        Returns True if any driver Granger-causes the target.
        """
        for driver in drivers:
            try:
                # Create test data
                test_data = df[[target, driver]].dropna()

                if len(test_data) < self.max_lag * 3:
                    continue

                # Run Granger test
                result = grangercausalitytests(test_data, maxlag=self.max_lag, verbose=False)

                # Check if any lag is significant
                for lag in range(1, self.max_lag + 1):
                    f_test = result[lag][0]["ssr_ftest"]
                    p_value = f_test[1]

                    if p_value < self.granger_alpha:
                        return True

            except Exception as e:
                logger.debug(f"Granger test failed for {driver}: {e}")
                continue

        return False
