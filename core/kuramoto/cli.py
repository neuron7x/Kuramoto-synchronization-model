# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Command-line interface for the Kuramoto simulation engine.

Entry point: ``tp-kuramoto``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
import numpy as np

from .config import KuramotoConfig
from .engine import run_simulation
from .io import export_payload, load_adjacency_matrix, load_edge_list, parse_float_list


@click.group()
@click.version_option(version="1.1.0", prog_name="tp-kuramoto")
def cli() -> None:
    """GeoSync Kuramoto Simulation Engine.

    Coupling semantics:
      - Global topology (no adjacency input): K/N on all off-diagonal pairs.
      - Explicit adjacency topology: K scales the provided adjacency weights A_ij.

    Seed semantics:
      - Explicit --omega bypasses RNG for natural frequencies.
      - Explicit --theta0 bypasses RNG for initial phases.
    """


@cli.command()
@click.option(
    "--N",
    "n_oscillators",
    type=int,
    default=10,
    show_default=True,
    help="Number of coupled oscillators (≥ 2).",
)
@click.option(
    "--K",
    "coupling",
    type=float,
    default=1.0,
    show_default=True,
    help="Global coupling scale. Global mode uses K/N; adjacency mode uses K*A_ij.",
)
@click.option(
    "--dt", type=float, default=0.01, show_default=True, help="Integration time-step (> 0)."
)
@click.option(
    "--steps",
    type=int,
    default=1000,
    show_default=True,
    help="Number of RK4 integration steps (≥ 1).",
)
@click.option("--seed", type=int, default=None, help="Random seed for reproducibility.")
@click.option(
    "--omega", "omega_str", type=str, default=None, help="Comma-separated natural frequencies."
)
@click.option(
    "--theta0",
    "theta0_str",
    type=str,
    default=None,
    help="Comma-separated initial phases (radians).",
)
@click.option(
    "--adjacency-file",
    type=click.Path(exists=True, path_type=Path, dir_okay=False),
    default=None,
    help="Load NxN adjacency matrix from .json/.csv/.txt/.npy.",
)
@click.option(
    "--edge-list-file",
    type=click.Path(exists=True, path_type=Path, dir_okay=False),
    default=None,
    help="Load directed weighted edges from JSON file with {'edges': [...]} schema.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write JSON result to this file.",
)
@click.option(
    "--export",
    "export_mode",
    type=click.Choice(["summary", "full"], case_sensitive=False),
    default="full",
    show_default=True,
    help="Export summary-only metadata or full trajectories.",
)
@click.option("--quiet", is_flag=True, help="Emit machine-readable JSON only.")
def simulate(
    n_oscillators: int,
    coupling: float,
    dt: float,
    steps: int,
    seed: int | None,
    omega_str: str | None,
    theta0_str: str | None,
    adjacency_file: Path | None,
    edge_list_file: Path | None,
    output_path: Path | None,
    export_mode: str,
    quiet: bool,
) -> None:
    """Run a Kuramoto simulation and emit a contract-stable JSON payload.

    Export contract:
      - ``--export summary``: includes only ``schema_version``, ``summary``, ``config``.
      - ``--export full``: includes summary payload plus trajectories.
      - ``--quiet`` prints JSON to stdout; ``--output`` writes an equivalent JSON payload to file.
    """
    if adjacency_file is not None and edge_list_file is not None:
        raise click.ClickException(
            "Use only one topology source: --adjacency-file or --edge-list-file."
        )

    omega: np.ndarray | None = None
    theta0: np.ndarray | None = None
    adjacency: np.ndarray | None = None

    try:
        if omega_str is not None:
            omega = parse_float_list(omega_str, option_name="--omega")
        if theta0_str is not None:
            theta0 = parse_float_list(theta0_str, option_name="--theta0")
        if adjacency_file is not None:
            adjacency = load_adjacency_matrix(adjacency_file)
        elif edge_list_file is not None:
            adjacency = load_edge_list(edge_list_file, n_oscillators=n_oscillators)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        cfg = KuramotoConfig(
            N=n_oscillators,
            K=coupling,
            dt=dt,
            steps=steps,
            seed=seed,
            omega=omega,
            theta0=theta0,
            adjacency=adjacency,
            adjacency_kind="normalized_topology" if adjacency is not None else None,
        )
    except Exception as exc:
        raise click.ClickException(f"Configuration error: {exc}") from exc

    try:
        result = run_simulation(cfg)
    except Exception as exc:
        raise click.ClickException(f"Simulation error: {exc}") from exc

    include_trajectories = export_mode.lower() == "full"
    payload = export_payload(
        summary=result.summary,
        config=cfg.to_dict(),
        include_trajectories=include_trajectories,
        order_parameter=result.order_parameter,
        time=result.time,
        phases=result.phases,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if quiet:
        click.echo(json.dumps(payload, indent=2))
        return

    _print_summary(result.summary)
    if output_path is not None:
        click.echo(f"Saved {export_mode.lower()} payload to: {output_path}")


def _print_summary(summary: dict[str, Any]) -> None:
    click.echo("")
    click.echo("━" * 50)
    click.echo("  Kuramoto Simulation — Summary")
    click.echo("━" * 50)
    click.echo(f"  Oscillators (N)  : {summary['N']}")
    click.echo(f"  Coupling (K)     : {summary['K']:.4f}")
    click.echo(f"  Coupling mode    : {summary['coupling_mode']}")
    click.echo(f"  Time-step (dt)   : {summary['dt']:.6f}")
    click.echo(f"  Steps            : {summary['steps']}")
    click.echo(f"  Total time       : {summary['total_time']:.4f}")
    click.echo("─" * 50)
    click.echo(f"  Final R          : {summary['final_R']:.6f}")
    click.echo(f"  Mean R           : {summary['mean_R']:.6f}")
    click.echo(f"  Max  R           : {summary['max_R']:.6f}")
    click.echo(f"  Min  R           : {summary['min_R']:.6f}")
    click.echo(f"  Std  R           : {summary['std_R']:.6f}")
    click.echo("━" * 50)
    click.echo("")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
