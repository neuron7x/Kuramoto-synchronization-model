# GeoSync Physics Glossary

> **Status:** canonical. Machine-checked by
> `scripts/ci/check_physics_docs_canon.py` (overclaim scan). Every physics term
> used in the README and canonical docs is defined here and tagged with its
> **kind** so a reader cannot mistake a mathematical object, a computational
> property, an unproven hypothesis, or a conceptual analogy for one another.

**Kind tags:** `MATH` (mathematical object / theorem), `COMP` (property of the
computation / implementation), `EMPIRICAL` (requires real-data evidence to
claim), `ANALOGY` (conceptual / non-claim), `FORBIDDEN` (banned framing, listed
only so it is recognizable).

| Term | Kind | Definition |
|---|---|---|
| Kuramoto order parameter (R) | `MATH` | Complex mean-field amplitude of a phase ensemble, `R∈[0,1]`; `R→1` is full synchronization (`INV-K1`). |
| Critical coupling (K_c) | `MATH` | Onset coupling for synchronization; `K_c = 2/(π·g(0))`, Lorentzian `K_c = 2γ`. Never hardcoded. |
| Finite-size floor | `MATH` | Incoherent ensembles show `⟨R⟩ ~ O(1/√N)`; bounds use `ε = C/√N`, not magic numbers. |
| Restrepo-Ott-Hunt boundary | `MATH` | Sync-onset condition on a curvature graph: `Φ = K·λ_max(A_κ) − 2γ` (`INV-KR1`). |
| Ott-Antonsen reduction | `MATH` | Low-dimensional manifold for the Kuramoto order parameter; `|z(t)|≤1` (`INV-OA1`). |
| Lyapunov exponent (MLE / spectrum) | `MATH` | Exponential divergence rate of nearby trajectories; sign classifies stability/chaos (`INV-LE*`, `INV-LY*`). |
| Ollivier-Ricci curvature | `MATH` | Optimal-transport curvature on a graph; `κ≤1` universal (`INV-RC1`). |
| Forman-Ricci curvature | `MATH` | Combinatorial curvature; finite-only, **not** Ollivier-bounded — never used as κ-bound evidence (`INV-CBR1`). |
| Signed curvature | `MATH` | Curvature retaining negative edges; preserved on the signed-coupling path, never silently clipped (`INV-KR4`). |
| Ricci flow trace | `COMP` | Discrete curvature-flow energy on a static graph; non-increasing in its declared domain (`INV-RC-FLOW`). |
| Gauss-Bonnet residual | `MATH` | Discrete Gauss-Bonnet balance over a finite simple graph's clique complex (`ricci.gauss_bonnet`). |
| Free energy (F) | `COMP` | `F = U − T·S`; F may be negative, components non-negative (`INV-FE1/2`). A computational descent quantity, not a thermodynamic measurement. |
| Landauer bound | `COMP` | `E_min = k_B·T·ln(Δ/δ_0)`; an erasure-cost floor of the computation (`INV-TAU2`, `thermo.landauer_bound`). |
| Jarzynski / fluctuation identity | `COMP` | `⟨e^(−βW)⟩ = e^(−βΔF)`; exact statistical-mechanics identity of the simulated Langevin system (`INV-ST2`). |
| Gabor uncertainty limit | `MATH` | `Δt·Δf ≥ 1/(4π)`; exact Fourier bound. **Not** a Heisenberg/Planck claim (`INV-GABOR1`). |
| Causal graph snapshot | `COMP` | `MarketCausalGraphSnapshot` with a structural schema and provenance hash (`manifold.metric_snapshot_schema`). |
| Causal cutoff | `EMPIRICAL` | Relativistic-**inspired** information-propagation cutoff; explicitly **not** relativistic physics (`manifold.causal_cutoff`). |
| Evidence capsule | `COMP` | Immutable artifact (data/config hashes, seed, null result) emitted by an instrumented run. |
| Falsifier | `COMP` | A command/test returning non-zero when a claim breaks; required for promotion of anchored claims. |
| Witness | `COMP` | A test that proves the code respects a law; its tolerance derives from the law's formula. |
| Claim tier / evidence tier | `COMP` | Allowed statuses: `Active`, `Not Measured`, `Not Deployable`, `Instrumented`, `Measured-Single`, `Measured-Multi`, `Blocked`. |
| Validity domain | `MATH` | The preconditions under which a law holds; outside it, the law is not asserted. |
| Serotonin / dopamine / GABA dynamics | `ANALOGY` | Engineering risk-instrumentation analogies; biological labels are arithmetic proxies, not biological claims. |
| Gradient ontology (ΔV) | `ANALOGY` | The author's root research axiom (`INV-YV1`); scoped to the system's substrate, not a market law. |
| Cosmological-compute / Bekenstein-cognitive | `ANALOGY` | PNCC research-ontology axioms; non-claim framing, never empirical or market physics. |
| Validated alpha / proven predictor / law of markets | `FORBIDDEN` | Banned framing (see `FORBIDDEN_CLAIMS.md`); the platform does not make these claims. |

**Rule:** a term tagged `EMPIRICAL` may only be claimed with a real-data
artifact (hashes + null baseline). A term tagged `ANALOGY` can never support a
promotion. A term tagged `FORBIDDEN` must never appear as an asserted capability.
