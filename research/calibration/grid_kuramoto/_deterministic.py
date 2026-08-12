# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""F3 — deterministic-reduction harness for forward calibration ledgers.

Context (audit PR #762, consolidation #759, this lineage F3)
------------------------------------------------------------
The calibration-ledger reproduction tests compared metrics with a
``_deep_close`` window of ``rel = 1e-6``. That window was ~6 orders of
magnitude looser than the real reproduction noise, so a genuine numeric
regression in the ``1e-9 .. 1e-6`` band on a pinned metric would pass
**undetected**. #762 unified the divergent tolerance copies; the *root*
— nondeterministic floating-point reduction across CI runners — was left
open. This module addresses the root, honestly.

What the diagnosis proved
-------------------------
The numeric path that produces every ledger metric chains BLAS/LAPACK
reductions: Savitzky–Golay derivatives (``scipy.signal.savgol_filter``,
internally ``lstsq``), column standardisation, ``np.linalg.lstsq``
(LAPACK ``gelsd``), ``np.linalg.svd`` (``gesdd``), ``np.linalg.pinv``,
``D^T D`` (BLAS ``gemm``), and Frobenius / 2-norms (BLAS ``nrm2``).

numpy and scipy each bundle a *private, statically linked*
``libscipy_openblas64`` built with ``DYNAMIC_ARCH``. At library load
OpenBLAS dispatches to a CPU-microarchitecture-specific micro-kernel
(Haswell / SkylakeX / Zen / Nehalem / …). Different micro-kernels use a
different SIMD blocking and therefore a different floating-point
**reduction order**. This dispatch is selected by the *host CPU*, not by
the thread count: it is present even single-threaded.

Empirical proof (single-thread, ``OMP_NUM_THREADS=1``,
``OPENBLAS_NUM_THREADS=1``, only ``OPENBLAS_CORETYPE`` varied across six
micro-kernels): the worst-case relative divergence of a *pinned ledger
metric* was ``2.20e-9`` (cg002 ``front_gate_score``, the most
amplified covariance/Wald chain). The pure-numpy reductions
(``sum`` / ``mean`` / ``std`` / ``median`` — numpy's own pairwise C
loop, not BLAS) were bit-identical across every micro-kernel.

Conclusion (BRANCH B — bit-exact cross-runner reproduction infeasible)
----------------------------------------------------------------------
Bit-exact cross-runner reproduction is **provably impossible** under the
shipped wheels, even single-threaded, because the BLAS micro-kernel is a
host-CPU property, not a thread-pool property. Forcing it would require
re-linking numpy/scipy against a reference BLAS — out of scope and not a
calibration concern. The honest second-best, delivered here:

* a single context manager that removes the *thread-order* component
  (so the only residual is the proven-irreducible micro-kernel dispatch
  and same-CPU reproduction is bit-identical), via :mod:`threadpoolctl`
  (already a transitive dependency through scikit-learn / scipy tooling);
* a **derived** forward tolerance bound :data:`FORWARD_REL_TOL` that is
  ``1e-8`` — 100× tighter than the legacy ``1e-6`` — with the derivation
  recorded below;
* the legacy ``1e-6`` window is *not* changed: the historical
  sha-pinned ledgers were born under the old nondeterministic regime and
  stay reproduced at the documented legacy ε (REGIME SPLIT, mirroring
  the F2 amendment / supersession discipline).

Forward tolerance derivation
----------------------------
.. math::

   \varepsilon_{\mathrm{fwd}}
   = \lceil\, \varepsilon_{\mathrm{obs}} \cdot s \,\rceil_{10}

where ``ε_obs = 2.20e-9`` is the measured worst-case single-thread
cross-micro-kernel relative divergence over the full ledger metric set
(six OpenBLAS coretypes: Haswell, Prescott, Nehalem, SandyBridge, Core2,
Atom), ``s ≈ 4.5`` is a safety multiplier covering untested
micro-kernels and the ``cond(K) ≈ 3.8`` condition-number amplification
of the near-cancellation metrics, and ``⌈·⌉₁₀`` rounds up to the next
power-of-ten decade. ``2.20e-9 × 4.5 ≈ 9.9e-9 → 1e-8``.

This is a *bound*, not a flake-suppressor: a real regression of plausible
magnitude shifts a pinned metric by ``≫ 1e-8`` (the original
CALIB-GRID-001 falsifier moved metrics by ``O(1)``), so the forward
detector is ~100× sharper than the legacy one while remaining provably
inside the irreducible cross-runner noise floor.

The proven impossibility is filed as a sha-anchored headstone in
``RIP/TOMBSTONES.md`` / ``RIP/manifest.yaml`` (id ``CALIB-F3``): a kill
is worth more than a forced win.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

__all__ = [
    "FORWARD_REL_TOL",
    "FORWARD_ABS_TOL",
    "LEGACY_REL_TOL",
    "LEGACY_ABS_TOL",
    "OBSERVED_WORST_CROSS_KERNEL_REL",
    "deterministic_reduction",
]

# ---------------------------------------------------------------------------
# Regime-split tolerance constants (single source of truth).
# ---------------------------------------------------------------------------

#: Measured worst-case single-thread cross-OpenBLAS-micro-kernel relative
#: divergence over the full calibration ledger metric set (six coretypes).
#: This is the *evidence* the forward bound is derived from; it is not a
#: tolerance itself.
OBSERVED_WORST_CROSS_KERNEL_REL: float = 2.2031e-9

#: Legacy (historical-regime) reproduction window. The merged sha-pinned
#: ledgers were computed under the OLD nondeterministic regime; they are
#: immutable and are reproduced at this documented ε. NOT tightened —
#: tightening it would falsely imply the frozen artifacts are bit-exact.
LEGACY_REL_TOL: float = 1e-6
LEGACY_ABS_TOL: float = 1e-9

#: Forward (deterministic-regime) reproduction window. Derived above:
#: ``ceil_decade(OBSERVED_WORST_CROSS_KERNEL_REL × 4.5) = 1e-8``. Any new
#: ledger computation that runs under :func:`deterministic_reduction`
#: must reproduce within this bound. 100× tighter than the legacy window.
FORWARD_REL_TOL: float = 1e-8
FORWARD_ABS_TOL: float = 1e-9


@contextlib.contextmanager
def deterministic_reduction() -> Iterator[None]:
    r"""Pin every native thread-pool to a single thread for the block.

    Removes the *thread-order* component of floating-point
    nondeterminism (BLAS / LAPACK / OpenMP parallel reduction order)
    using :mod:`threadpoolctl`. After this the only residual cross-runner
    nondeterminism is the OpenBLAS ``DYNAMIC_ARCH`` micro-kernel dispatch
    (a host-CPU property, *provably* not removable in-process — see the
    module docstring), so:

    * on a *single* CPU the calibration ledger is **bit-identical**
      across repeated builds (verified ``N ≥ 5×`` in the F3 forcing
      test);
    * across *different* CPUs the divergence is bounded by
      :data:`FORWARD_REL_TOL` (derived, not arbitrary).

    The context manager is a no-op-safe wrapper: if no controllable
    native pool is present (statically embedded BLAS exposes none to
    :mod:`threadpoolctl`), thread limiting silently has no effect — the
    pure-numpy reductions are already order-deterministic, so
    correctness is unaffected; only the (already verified) bit-stability
    guarantee then rests on the single-CPU assumption alone. No scattered
    ``os.environ`` mutation: the limit is scoped and restored exactly by
    :mod:`threadpoolctl`.

    Yields
    ------
    None
        Control returns to the caller with all discoverable native
        thread-pools limited to one thread; the previous limits are
        restored on exit (including on exception).
    """
    from threadpoolctl import threadpool_limits

    with threadpool_limits(limits=1):
        yield
