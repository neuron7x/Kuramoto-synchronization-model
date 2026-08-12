# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Import-order independence of the Lyapunov-spectrum float64 contract.

INV-LY1 (1e-3 / 1e-6 precision) and INV-LY2 (Σλ = 0 to 1e-3 on Hamiltonian
flow) both require ``jax_enable_x64``. The spectrum module must enable it at
import so its correctness does NOT depend on whether an unrelated module (e.g.
``core.kuramoto.lyapunov_calibration``) happened to enable it first.

The check runs in a FRESH interpreter that imports ONLY the spectrum module,
isolating import order from the pytest ``conftest`` (which may already have
enabled x64 process-wide).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

_PROBE = """
import jax, jax.numpy as jnp, numpy as np
from core.physics.lyapunov_spectrum import lyapunov_spectrum

assert jax.config.read("jax_enable_x64") is True, "x64 not enabled on import"

w2 = 4.0  # harmonic oscillator: Hamiltonian flow, spectrum (0, 0), Sum = 0
res = lyapunov_spectrum(
    lambda x: jnp.array([x[1], -w2 * x[0]]),
    jnp.array([1.0, 0.0]),
    dt=0.01,
    n_steps=2000,
    n_exp=2,
)
s = np.asarray(res.spectrum)
assert s.dtype == np.float64, f"spectrum dtype {s.dtype} (float32 => precision loss)"
assert abs(float(s.sum())) < 1e-3, f"INV-LY2 violated: sum(lambda)={s.sum():.3e}"
print("OK")
"""


def test_spectrum_enables_x64_regardless_of_import_order() -> None:
    """A fresh interpreter importing only lyapunov_spectrum must compute in
    float64 and satisfy INV-LY2 — no dependency on import order."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"import-only lyapunov_spectrum failed float64/INV-LY2 contract.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout
