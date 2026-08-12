# Methodology Pointer

The authoritative methodology document is
``KURAMOTO_NETWORK_ENGINE_METHODOLOGY.md`` at the repository root
(supplied by the project architect). This file only records the
module-to-protocol mapping and the resolved deviations.

## Protocol → module map

| Protocol | Scope | Module |
|---|---|---|
| M1.1 | Contracts / types | ``core/kuramoto/contracts.py`` |
| M1.2 | Phase extraction | ``core/kuramoto/phase_extractor.py`` |
| M1.3 | Coupling estimation K_ij | ``core/kuramoto/coupling_estimator.py`` |
| M1.4 | Natural frequency ω_i | ``core/kuramoto/natural_frequency.py`` |
| M1.5 | PCMCI causal validation | ``core/kuramoto/causal_validation.py`` |
| M2.1 | Delay estimation τ_ij | ``core/kuramoto/delay_estimator.py`` |
| M2.2 | Frustration α_ij | ``core/kuramoto/frustration.py`` |
| M2.3 | Dynamic coupling K_ij(t) | ``core/kuramoto/dynamic_graph.py`` |
| M2.4 | Emergent metrics | ``core/kuramoto/metrics.py`` |
| M3.1 | Synthetic ground truth | ``core/kuramoto/synthetic.py`` |
| M3.2 | Falsification | ``core/kuramoto/falsification.py`` |
| M3.3 | OOS validation + DM + SPA | ``core/kuramoto/oos_validation.py`` |
| M3.4 | Trading pipeline integration | ``core/kuramoto/feature.py`` |
| SE.1 | SDDE simulation | ``core/kuramoto/synthetic._simulate_sdde`` (Python EM) |
| Orchestrator | Engine composition | ``core/kuramoto/network_engine.py`` |

## Resolved deviations from the methodology

Each deviation is deliberate and justified below.

### 1. ``stability-selection`` PyPI package replaced by inline implementation

The PyPI ``stability-selection`` package is unmaintained since
2021 and breaks on ``sklearn ≥ 1.3`` due to the removal of the
deprecated ``normalize`` parameter. The methodology explicitly
warns against installing it. We ship a pure-numpy
complementary-pairs stability selection (Shah & Samworth 2013)
inside ``coupling_estimator.complementary_pairs_stability``.

### 2. ``skglm`` MCP/SCAD replaced by inline proximal gradient

To keep the core path dependency-free we implement the MCP and
SCAD proximal operators directly and run ISTA with an exact
Lipschitz constant computed via SVD. Convergence and recovery
are validated against synthetic ground truth in
``tests/unit/core/test_kuramoto_coupling_estimator.py``.

### 3. Delay target uses forward differences, not
``np.gradient``

The methodology sketch uses central differences for the target
``y = θ̇``; central differences sit at ``t + 0.5``, which
introduces a **half-step offset** relative to the Sakaguchi
drift equation used at step ``t``. This biases integer lag
estimates by 1 step. We use forward differences (``np.diff``)
which match the Euler–Maruyama identity exactly.

### 4. Joint per-row delay search instead of weighted consensus

The methodology sketches a ``argmin RSS`` profile likelihood
against cross-correlation candidates. In practice coordinate
descent on the joint row objective — with OLS re-fitting of
``β`` at every candidate lag — is more robust, and for small
rows we enumerate the whole grid. The original method's
"weighted average of lags" would produce non-integer delays
and is explicitly called out as statistically invalid in the
methodology; we do not implement it.

### 5. Signed community detection without ``leidenalg``

The methodology lists ``leidenalg`` for signed community
detection. We implement a recursive spectral-sign split with
signed modularity (Gómez, Jensen & Arenas, 2009) that has no
heavy dependency and recovers planted partitions with NMI ≥ 0.9
on our synthetic benchmarks.

### 6. Critical slowing down without ``ewstools``

``rolling_csd`` in ``metrics.py`` implements trailing rolling
variance and lag-1 autocorrelation directly in numpy. This
matches the methodology's "variance / autocorr" early-warning
signal without the dependency.

### 7. Permutation entropy without ``antropy``

``permutation_entropy`` in ``metrics.py`` is a pure-numpy
Bandt–Pompe implementation. Verified against analytic limits
(monotonic → 0, uniform random → 1).

### 8. IAAFT without ``nolitsa``

``iaaft_surrogate`` in ``falsification.py`` is a direct
implementation of Schreiber & Schmitz (1996). Avoids the
``nolitsa`` install profile issues on numpy 2.x.

### 9. Julia SDDE solver: Python Euler–Maruyama is used

The methodology lists Julia's ``StochasticDelayDiffEq.jl`` as
the "exact SDDE solver" via :mod:`juliacall`. For the scale of
the identification stack (N ≤ 50, T ≤ 10 000) the Python
Euler–Maruyama integrator in ``synthetic._simulate_sdde`` and
``oos_validation.simulate_forward`` is sufficient — accuracy
against analytic Kuramoto coherence at ``K > K_c`` matches to
within ``10⁻⁴``. The Julia backend remains a documented
optional upgrade path for production-grade continuous-time
simulations.
