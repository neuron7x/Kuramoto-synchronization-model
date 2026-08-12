# GeoSync Physics Law T8 — Exact Fluctuation Theorems (Stochastic Thermodynamics)

**Status:** ACTIVE • **Tier:** ANCHORED on Jarzynski (1997); Crooks (1999); Sekimoto (1998)
**Module:** `core/physics/stochastic_thermodynamics.py`
**Tests:** `tests/unit/physics/test_T8_stochastic_thermodynamics.py`
**Invariants:** INV-ST1, INV-ST2, INV-ST3

> Pure statistical mechanics. This law card describes an overdamped
> Langevin particle in a harmonic well. It is **not** a market model and
> emits no market claim — the only inputs are a stiffness schedule, a
> temperature, and a random seed.

---

## 1. Statement

A single overdamped degree of freedom `x` in a time-dependent harmonic
potential `V(x, t) = ½ k(t) x²` evolves by the overdamped Langevin
equation (mobility `1/γ`):

```
dx = −(1/γ) V'(x, t) dt + sqrt(2 kT / γ) dW_t
```

integrated with Euler-Maruyama at step `dt`:

```
x ← x − (dt/γ) k x + sqrt(2 γ kT dt) · N(0, 1).
```

The equilibrium free energy of the harmonic well is the Gaussian
partition-function result

```
F(k) = −(1/2β) ln(2π / (βk)),     β = 1/kT,
```

so a stiffness ramp `k_i → k_f` has the exact free-energy difference

```
ΔF = F(k_f) − F(k_i) = −(1/2β) ln(k_i / k_f).
```

Work along a protocol is accumulated in the Sekimoto stochastic-energetics
convention — the protocol parameter advances at fixed configuration and the
work increment is the resulting change of potential energy:

```
dW = (∂V/∂k) dk = ½ x² dk.
```

The three exact, closed-form results that this law enforces:

1. **Equipartition (INV-ST1).** The stationary distribution is the
   Boltzmann Gaussian `p(x) ∝ exp(−βV)`, giving `Var(x) = kT/k`.
2. **Jarzynski equality (INV-ST2).** For an arbitrarily fast protocol,
   `⟨e^(−βW)⟩ = e^(−βΔF)` exactly in expectation over the non-equilibrium
   work distribution. For the harmonic ramp, `e^(−βΔF) = sqrt(k_i/k_f)`.
3. **Second law (INV-ST3).** By Jensen's inequality on the Jarzynski
   identity, `⟨W⟩ ≥ ΔF`, and the mean dissipated work `⟨W⟩ − ΔF` shrinks
   as the protocol is slowed toward the quasi-static limit.

## 2. Public surface

| Symbol | Role |
|---|---|
| `harmonic_free_energy(k, kT)` | Closed-form `F(k) = −(1/2β) ln(2π/(βk))` |
| `delta_free_energy(ki, kf, kT)` | Closed-form `ΔF = −(1/2β) ln(ki/kf)` |
| `langevin_ensemble_step(x, *, k, dt, kT, gamma, rng)` | One vectorized Euler-Maruyama step |
| `stiffness_ramp_work(seed, ...)` | Ensemble **work** array for the linear stiffness ramp (Jarzynski observable) |
| `stationary_samples(seed, *, k, ...)` | Boltzmann-stationary sampler (equipartition witness) |
| `jarzynski_average(work, kT)` | `⟨e^(−βW)⟩`, numerically stabilised |

Pure NumPy. Vectorized (all `M` trajectories as one array). Deterministic
for a given seed. No I/O, no hidden state. `mypy --strict` clean.

## 3. Constitutional invariants

```
INV-ST1 | statistical | Var(x) = kT/k (equipartition / Boltzmann stationary) | P0
                      | relative tol 0.10; measured ≈0.017.
INV-ST2 | statistical | ⟨e^(−βW)⟩ = e^(−βΔF) = sqrt(ki/kf) (Jarzynski)      | P0
                      | relative tol 0.05; measured ≤0.004.
INV-ST3 | statistical | ⟨W⟩ ≥ ΔF (second law) AND ⟨W⟩(τ=2.0) < ⟨W⟩(τ=0.5)  | P1
                      | (dissipation monotonic in protocol speed).
```

## 4. Measured numbers (reference run, ensemble = 40000)

| Quantity | Target | Measured |
|---|---|---|
| `e^(−βΔF) = sqrt(ki/kf)` (ki=1, kf=4) | 0.5000 | — |
| `⟨e^(−βW)⟩`, seeds {1,7,42,123} | 0.5000 | 0.498–0.500 (dev ≤0.4%) |
| `⟨W⟩` at τ=1.0 | ≥ ΔF=0.693 | ≈0.93 |
| `⟨W⟩` at τ=2.0 vs τ=0.5 | slower < faster | 0.84 < 1.08 |
| `Var(x)` stationary, k∈{1,2,4} | kT/k | within ~1.7% |

## 5. Falsifiers

* INV-ST1: `|Var(x) − kT/k| / (kT/k) > 0.10` for any tested stiffness.
* INV-ST2: `|⟨e^(−βW)⟩ − e^(−βΔF)| / e^(−βΔF) > 0.05` on the reference ramp.
* INV-ST3: `⟨W⟩ < ΔF`, OR `⟨W⟩(τ=2.0) ≥ ⟨W⟩(τ=0.5)`.

Each falsifier maps to a single assertion in the T8 test module; a
violation is an implementation bug, never a tolerance to relax — the
physics is closed-form and verified.

## 6. References

* Jarzynski, C. (1997). *Nonequilibrium equality for free energy
  differences.* Phys. Rev. Lett. **78**, 2690.
* Crooks, G. E. (1999). *Entropy production fluctuation theorem and the
  nonequilibrium work relation for free energy differences.* Phys. Rev. E
  **60**, 2721.
* Sekimoto, K. (1998). *Langevin equation and thermodynamics.* Prog. Theor.
  Phys. Suppl. **130**, 17.
