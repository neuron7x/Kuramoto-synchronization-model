"""Utility plotting functions for analysing VLPO filtering."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..core.entropy import compute_shannon_entropy


def _upper_tail_mean(values: np.ndarray, *, alpha: float = 0.05) -> float:
    cutoff = max(int((1.0 - alpha) * len(values)), 1)
    sorted_values = np.sort(values)
    tail = sorted_values[-cutoff:]
    return float(np.mean(tail))


def plot_entropy_and_correlation(
    pre_df: pd.DataFrame,
    post_df: pd.DataFrame,
    *,
    target_col: str,
    output_path: str = "filter_entropy_corr.png",
) -> None:
    """Plot entropy and correlation metrics before/after filtering."""

    features = [col for col in pre_df.columns if col != target_col]
    pre_entropy = [compute_shannon_entropy(pre_df[col]) for col in features]
    post_entropy = [compute_shannon_entropy(post_df[col]) for col in features]

    pre_corr = [pre_df[col].corr(pre_df[target_col]) for col in features]
    post_corr = [post_df[col].corr(post_df[target_col]) for col in features]

    fig, (ax_entropy, ax_corr) = plt.subplots(1, 2, figsize=(12, 5))
    ax_entropy.bar(np.arange(len(features)) - 0.15, pre_entropy, width=0.3, label="pre")
    ax_entropy.bar(
        np.arange(len(features)) + 0.15, post_entropy, width=0.3, label="post"
    )
    ax_entropy.set_title("Feature entropy")
    ax_entropy.legend()

    ax_corr.bar(np.arange(len(features)) - 0.15, pre_corr, width=0.3, label="pre")
    ax_corr.bar(np.arange(len(features)) + 0.15, post_corr, width=0.3, label="post")
    ax_corr.set_title("Correlation vs target")
    ax_corr.legend()

    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def plot_metrics(
    pre_target: np.ndarray,
    post_target: np.ndarray,
    *,
    output_path: str = "filter_metrics.png",
) -> None:
    """Plot SNR and upper tail mean metrics."""

    pre_snr = float(np.mean(pre_target) / max(np.std(pre_target), 1e-12))
    post_snr = float(np.mean(post_target) / max(np.std(post_target), 1e-12))

    pre_tail = _upper_tail_mean(pre_target)
    post_tail = _upper_tail_mean(post_target)

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(
        ["pre_snr", "post_snr", "pre_tail", "post_tail"],
        [pre_snr, post_snr, pre_tail, post_tail],
    )
    ax.bar_label(bars, fmt="%.4f")
    ax.set_title("VLPO filter metrics")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


__all__ = ["plot_entropy_and_correlation", "plot_metrics"]
