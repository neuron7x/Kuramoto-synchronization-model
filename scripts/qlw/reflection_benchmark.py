"""Benchmark PML reflection suppression."""

import numpy as np
import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.tradepulse_qlw.pde_solver import NewmarkWaveSolver


def measure(
    nx=128,
    nt=512,
    dx=1.0,
    dt=0.02,
    c=2.0,
    gamma=0.2,
    pml_gain=0.0,
    pml_width_frac=0.075,
):
    """Measure reflection energy ratio."""
    s = NewmarkWaveSolver(
        nx,
        nt,
        dx,
        dt,
        c,
        gamma,
        noise_sigma=0.0,
        seed=42,
        pml_gain=pml_gain,
        pml_width_frac=pml_width_frac,
    )
    x = np.arange(nx)
    u0 = np.exp(-0.01 * (x - nx // 2) ** 2)
    psi = s.solve(u0=u0)
    edge_w = int(nx * 0.05)
    edge_energy = np.sum(psi[:, :edge_w] ** 2) + np.sum(psi[:, -edge_w:] ** 2)
    total_energy = np.sum(psi**2)
    rho = edge_energy / (total_energy + 1e-12)
    return {"rho": float(rho), "edge": float(edge_energy), "total": float(total_energy)}


if __name__ == "__main__":
    grid = [(0.0, 0.0), (2.0, 0.075), (4.0, 0.1)]
    rows = []
    for g, w in grid:
        r = measure(pml_gain=g, pml_width_frac=w)
        r.update({"pml_gain": g, "pml_width_frac": w})
        rows.append(r)
    df = pd.DataFrame(rows)
    output_path = Path(__file__).parent.parent.parent / "reports" / "reflection_benchmark.csv"
    df.to_csv(output_path, index=False)
    print(f"Results saved to {output_path}")
    print(df)
