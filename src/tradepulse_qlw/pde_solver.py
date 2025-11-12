from __future__ import annotations

import numpy as np

try:
    from numba import cuda, jit
except Exception:

    def jit(f):  # no-op
        return f

    cuda = None


class NewmarkWaveSolver:
    def __init__(
        self,
        nx: int,
        nt: int,
        dx: float,
        dt: float,
        c: float,
        gamma: float,
        noise_sigma: float = 0.0,
        seed: int | None = None,
        pml_width_frac: float = 0.075,
        pml_gain: float = 2.0,
        use_numba: bool = True,
        use_gpu: bool = False,
    ):
        self.nx, self.nt, self.dx, self.dt = nx, nt, dx, dt
        self.c, self.gamma, self.sigma = c, gamma, noise_sigma
        self.pml_width_frac, self.pml_gain = pml_width_frac, pml_gain
        self.use_numba, self.use_gpu = use_numba, use_gpu and (cuda is not None)
        self.rng = np.random.default_rng(seed)
        self.gamma_x = self._pml_profile()
        # Note: Numba JIT is applied at function level, not method level
        # Use static methods or module-level functions for JIT compilation

    def _pml_profile(self):
        w = max(1, int(self.nx * self.pml_width_frac))
        prof = np.zeros(self.nx, dtype=np.float64)
        ramp = np.linspace(0, 1, w) ** 2
        prof[:w] = ramp
        prof[-w:] = ramp[::-1]
        return self.gamma + self.pml_gain * prof

    def _laplacian(self, u: np.ndarray) -> np.ndarray:
        lap = np.empty_like(u)
        lap[1:-1] = (u[2:] - 2 * u[1:-1] + u[:-2]) / (self.dx * self.dx)
        lap[0] = lap[1]
        lap[-1] = lap[-2]
        return lap

    def _accel(self, u: np.ndarray) -> np.ndarray:
        eta = self.rng.normal(0.0, self.sigma, size=u.shape) if self.sigma > 0 else np.zeros_like(u)
        result: np.ndarray = (self.c * self.c) * self._laplacian(u) - self.gamma_x * u + eta
        return result

    def solve(
        self, u0: np.ndarray | None = None, v0: np.ndarray | None = None
    ) -> np.ndarray:
        nx, nt, dt = self.nx, self.nt, self.dt
        u = np.zeros((nt, nx), dtype=np.float64)
        v = np.zeros(nx, dtype=np.float64) if v0 is None else v0.astype(np.float64)
        if u0 is not None:
            u[0] = u0.astype(np.float64)
        a = self._accel(u[0])
        beta, gam = 0.25, 0.5
        dt2 = dt * dt
        u[1] = u[0] + dt * v + 0.5 * dt2 * a
        v += dt * a
        a_buf = np.empty(nx)
        for t in range(1, nt - 1):
            a = self._accel(u[t])
            u[t + 1] = u[t] + dt * v + (0.5 - beta) * dt2 * a
            a_buf[:] = self._accel(u[t + 1])
            u[t + 1] += beta * dt2 * a_buf
            v += (1 - gam) * dt * a + gam * dt * a_buf
        return u.astype(np.float32)
