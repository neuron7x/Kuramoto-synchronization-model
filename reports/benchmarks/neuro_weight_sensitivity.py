"""Weight sensitivity analysis for the neuro optimizer objective.

This script performs a grid sweep across balance/performance/stability weights,
computes the mean and variance of the objective over a fixed synthetic sequence,
and writes results to CSV plus an SVG heatmap in reports/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import sys
from importlib import util

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

_neuro_path = REPO_ROOT / "src" / "tradepulse" / "core" / "neuro" / "neuro_optimizer.py"
spec = util.spec_from_file_location("neuro_optimizer", _neuro_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Unable to load neuro optimizer module from {_neuro_path}")
_neuro_module = util.module_from_spec(spec)
sys.modules[spec.name] = _neuro_module
spec.loader.exec_module(_neuro_module)

BalanceMetrics = _neuro_module.BalanceMetrics
NeuroOptimizer = _neuro_module.NeuroOptimizer
OptimizationConfig = _neuro_module.OptimizationConfig


@dataclass(frozen=True)
class SweepConfig:
    """Configuration for the weight sweep."""

    seed: int = 42
    series_length: int = 50
    sharpe_mean: float = 1.2
    sharpe_std: float = 0.4
    grid_step: float = 0.1


def _synthetic_state() -> Dict[str, float]:
    return {
        "dopamine_level": 0.6,
        "serotonin_level": 0.3,
        "gaba_inhibition": 0.4,
        "na_arousal": 1.1,
        "ach_attention": 0.7,
    }


def _generate_weight_grid(step: float) -> Iterable[Tuple[float, float, float]]:
    weights = np.round(np.arange(step, 1.0, step), 2)
    for balance_weight in weights:
        for performance_weight in weights:
            stability_weight = np.round(1.0 - balance_weight - performance_weight, 2)
            if stability_weight < 0:
                continue
            yield balance_weight, performance_weight, stability_weight


def _compute_objective_series(
    weights: Tuple[float, float, float],
    performance_series: np.ndarray,
    balance: BalanceMetrics,
    state: Dict[str, float],
) -> List[float]:
    balance_weight, performance_weight, stability_weight = weights
    config = OptimizationConfig(
        balance_weight=balance_weight,
        performance_weight=performance_weight,
        stability_weight=stability_weight,
    )
    optimizer = NeuroOptimizer(config)
    objectives: List[float] = []
    for performance in performance_series:
        objective = optimizer._calculate_objective(float(performance), balance, state)
        optimizer._performance_history.append(objective)
        objectives.append(objective)
    return objectives


def _interp_color(value: float, vmin: float, vmax: float) -> str:
    if vmax <= vmin:
        ratio = 0.0
    else:
        ratio = (value - vmin) / (vmax - vmin)
    ratio = max(0.0, min(1.0, ratio))
    start = (247, 251, 255)  # light blue
    end = (8, 48, 107)  # deep blue
    rgb = tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _render_heatmap_svg(
    values: Dict[Tuple[float, float], float],
    balance_values: List[float],
    performance_values: List[float],
    title: str,
    x_label: str,
    y_label: str,
    vmin: float,
    vmax: float,
    cell_size: int = 36,
    margin_left: int = 90,
    margin_top: int = 50,
    margin_right: int = 30,
    margin_bottom: int = 60,
) -> str:
    width = margin_left + len(performance_values) * cell_size + margin_right
    height = margin_top + len(balance_values) * cell_size + margin_bottom
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        f'<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2:.1f}" y="24" text-anchor="middle" font-size="16" font-family="Arial">{title}</text>',
    ]

    for row_index, balance_weight in enumerate(reversed(balance_values)):
        y = margin_top + row_index * cell_size
        for col_index, performance_weight in enumerate(performance_values):
            x = margin_left + col_index * cell_size
            value = values.get((balance_weight, performance_weight))
            if value is None:
                fill = "#f0f0f0"
            else:
                fill = _interp_color(value, vmin, vmax)
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
                f'stroke="#ffffff" fill="{fill}"/>'
            )

    # Axis labels
    svg_parts.append(
        f'<text x="{margin_left + (len(performance_values) * cell_size) / 2:.1f}" '
        f'y="{height - 16}" text-anchor="middle" font-size="12" font-family="Arial">{x_label}</text>'
    )
    svg_parts.append(
        f'<text x="18" y="{margin_top + (len(balance_values) * cell_size) / 2:.1f}" '
        f'text-anchor="middle" font-size="12" font-family="Arial" transform="rotate(-90 18,{margin_top + (len(balance_values) * cell_size) / 2:.1f})">'
        f'{y_label}</text>'
    )

    # Ticks
    for col_index, performance_weight in enumerate(performance_values):
        x = margin_left + col_index * cell_size + cell_size / 2
        svg_parts.append(
            f'<text x="{x}" y="{height - 36}" text-anchor="middle" font-size="10" font-family="Arial">'
            f'{performance_weight:.2f}</text>'
        )
    for row_index, balance_weight in enumerate(reversed(balance_values)):
        y = margin_top + row_index * cell_size + cell_size / 2 + 4
        svg_parts.append(
            f'<text x="{margin_left - 8}" y="{y}" text-anchor="end" font-size="10" font-family="Arial">'
            f'{balance_weight:.2f}</text>'
        )

    # Legend
    legend_x = margin_left + len(performance_values) * cell_size + 8
    legend_y = margin_top
    legend_height = len(balance_values) * cell_size
    for i in range(legend_height):
        value = vmax - (vmax - vmin) * (i / max(1, legend_height - 1))
        color = _interp_color(value, vmin, vmax)
        svg_parts.append(
            f'<rect x="{legend_x}" y="{legend_y + i}" width="12" height="1" fill="{color}"/>'
        )
    svg_parts.append(
        f'<text x="{legend_x + 18}" y="{legend_y + 8}" font-size="10" font-family="Arial">{vmax:.3f}</text>'
    )
    svg_parts.append(
        f'<text x="{legend_x + 18}" y="{legend_y + legend_height}" font-size="10" font-family="Arial">{vmin:.3f}</text>'
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def run_sweep(config: SweepConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    performance_series = rng.normal(
        loc=config.sharpe_mean,
        scale=config.sharpe_std,
        size=config.series_length,
    )

    state = _synthetic_state()
    base_optimizer = NeuroOptimizer(OptimizationConfig())
    balance = base_optimizer._calculate_balance_metrics(state)

    rows = []
    for weights in _generate_weight_grid(config.grid_step):
        objectives = _compute_objective_series(weights, performance_series, balance, state)
        rows.append(
            {
                "balance_weight": weights[0],
                "performance_weight": weights[1],
                "stability_weight": weights[2],
                "mean_objective": float(np.mean(objectives)),
                "variance_objective": float(np.var(objectives)),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["balance_weight", "performance_weight", "stability_weight"]
    )


def main() -> None:
    sweep_config = SweepConfig()
    df = run_sweep(sweep_config)

    csv_path = REPO_ROOT / "reports" / "neuro_weight_sensitivity.csv"
    mean_svg_path = REPO_ROOT / "reports" / "neuro_weight_sensitivity_mean.svg"
    variance_svg_path = REPO_ROOT / "reports" / "neuro_weight_sensitivity_variance.svg"
    markdown_path = REPO_ROOT / "reports" / "neuro_weight_sensitivity_summary.md"

    csv_path.write_text(df.to_csv(index=False), encoding="utf-8")

    markdown_lines = [
        "# Neuro Objective Weight Sensitivity (Fixed Seed)",
        "",
        "| balance_weight | performance_weight | stability_weight | mean_objective | variance_objective |",
        "| --- | --- | --- | --- | --- |",
    ]
    for _, row in df.iterrows():
        markdown_lines.append(
            "| "
            + " | ".join(
                [
                    f"{row['balance_weight']:.2f}",
                    f"{row['performance_weight']:.2f}",
                    f"{row['stability_weight']:.2f}",
                    f"{row['mean_objective']:.4f}",
                    f"{row['variance_objective']:.6f}",
                ]
            )
            + " |"
        )
    markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")

    balance_values = sorted(df["balance_weight"].unique().tolist())
    performance_values = sorted(df["performance_weight"].unique().tolist())

    mean_values = {
        (row["balance_weight"], row["performance_weight"]): row["mean_objective"]
        for _, row in df.iterrows()
    }
    variance_values = {
        (row["balance_weight"], row["performance_weight"]): row["variance_objective"]
        for _, row in df.iterrows()
    }

    mean_svg = _render_heatmap_svg(
        mean_values,
        balance_values,
        performance_values,
        title="Mean Objective (Fixed Seed)",
        x_label="performance_weight",
        y_label="balance_weight",
        vmin=float(df["mean_objective"].min()),
        vmax=float(df["mean_objective"].max()),
    )
    variance_svg = _render_heatmap_svg(
        variance_values,
        balance_values,
        performance_values,
        title="Objective Variance (Fixed Seed)",
        x_label="performance_weight",
        y_label="balance_weight",
        vmin=float(df["variance_objective"].min()),
        vmax=float(df["variance_objective"].max()),
    )

    mean_svg_path.write_text(mean_svg, encoding="utf-8")
    variance_svg_path.write_text(variance_svg, encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {markdown_path}")
    print(f"Wrote {mean_svg_path}")
    print(f"Wrote {variance_svg_path}")


if __name__ == "__main__":
    main()
