# PROVENANCE — CALIB-GRID-002 (integral / weak-form swing identifier)

> Pre-committed on branch `feat/calib-grid-002` off `origin/main` sha
> `a5e0d533b2201c999b31c792773e858f8da713bf` **before** the full
> CALIB-GRID-002 simulation was run. This file fixes the estimator
> class, the literature anchor, the theorem-class metric, the data
> parity assertion and the M/D provenance from theory and citation
> alone. It contains **no** measured calibration value (those live in
> `cg002/RESULTS.json` / `RESULTS.md`, produced after this file was
> committed).

## 1. Lineage and scope

CALIB-GRID-002 is a **new pre-registered lineage**, not a refinement of
the frozen CALIB-GRID-001 / R1 gates. CALIB-GRID-001 + R1 proved (PR
#749 / #751, sha-pinned NEGATIVE) that the R1 swing estimator is a
**differential-regression** estimator: it forms the swing target
`m θ̈ + d θ̇` by a double Savitzky–Golay derivative of the phase, and a
swept verification proved no consistent *differential* estimator exists
at the frozen `σ = 0.02` / frozen record length. The merged
identifiability front-gate (PR #755) makes that failure self-evident
(REFUSE on σ=0.02). Those frozen gates are **untouched** by
CALIB-GRID-002.

CALIB-GRID-002 attacks that proven differential-class boundary with a
legitimately **different estimator class**.

## 2. Estimator class — weak / integral form (literature anchor)

`core.kuramoto.coupling_estimator.estimate_swing_coupling_integral`.

Anchor: **Messenger, D. A. & Bortz, D. M.**, *Weak SINDy for partial
differential equations*, **Journal of Computational Physics** 443
(2021) 110525; and *Weak SINDy: Galerkin-based data-driven model
selection*, **Multiscale Modeling & Simulation** 19(3) (2021)
1474–1497.

The swing identity per node `i` is multiplied by a family of compactly
supported `C^{p-1}` test functions `φ_k(t)` (the canonical bump
`φ(s) = (1 - s²)^p`, `s ∈ [-1,1]`, `p = bump_order = 6`; `φ = φ' = 0`
at the window endpoints) and integrated. Integration by parts moves
**both** time derivatives off the noisy phase onto the analytically
known test function:

    ∫ φ_k · m_i θ̈_i dt =  m_i ∫ φ_k'' θ_i dt
    ∫ φ_k · d_i θ̇_i dt = −d_i ∫ φ_k'  θ_i dt

so the regression design contains **only `θ` and the analytic
derivatives of `φ`** — the phase is never differentiated.

**Noise-propagation justification (why the class is different, not a
retuned differential estimator).** Differentiation is a high-pass
operator: one numerical derivative scales the additive-noise PSD by
`ω²`, the double derivative the R1 path needs scales it by `ω⁴`
(CALIB-GRID-001 R1 RESULTS.md: the swept Savitzky–Golay verification
could not push the σ=0.02 Frobenius below ≈0.61). Integration is the
opposite — a low-pass operator: the quadrature `∫ φ_k η dt` of
zero-mean measurement noise `η` has variance `∝ σ² ‖φ_k‖² Δt` and
**averages noise down**. This is the documented advantage and the
reason the weak form is a different estimator class.

A state-space (Kalman/EM) alternative was considered and **not** chosen:
the weak form is exactly linear in `(K, P)` once the integrals are
formed (the same least-squares contract as the merged paths, so the
result is a bit-identical `SwingCouplingEstimate` and interoperates
unchanged with the merged identifiability front-gate), it has no latent
state to initialise and no EM convergence to audit, and it has the
cleaner, citable noise-propagation argument above. Documented choice.

## 3. Theorem-class independent metric (Dörfler–Chertkov–Bullo)

Anchor: **Dörfler, F., Chertkov, M. & Bullo, F.**, *Synchronization in
complex oscillator networks and smart grids*, **PNAS** 110(6) (2013)
2005–2010.

A **non-circular** consistency metric, separate from `‖K̂−K‖` and from
the critical-coupling scale: the **DC-power-flow / linearised
auxiliary-system phase-cohesiveness** prediction. For a connected
weighted coupling Laplacian `L(K)` and injection `P`, the DCB
small-signal (DC-power-flow) steady state is `δ* = L(K)⁺ P` and the
predicted edge phase-cohesiveness vector is `B(K)ᵀ δ*` (per-edge angle
differences). We compare the prediction built from the **recovered**
`(K̂, P̂)` against the prediction from the **true** `(K, P)`:

    dcb_phase_cohesiveness_rel_error
        = ‖ B(K̂)ᵀ L(K̂)⁺ P̂  −  B(K)ᵀ L(K)⁺ P ‖₂ / ‖ B(K)ᵀ L(K)⁺ P ‖₂

This probes whether the recovered system *reproduces the same
synchronisation / phase-cohesiveness physics* (Dörfler–Chertkov–Bullo
Eq. (2)–(3)), not merely whether the coupling matrix is close in
Frobenius norm. It is independent of the Frobenius metric and of the
`s_crit` metric (different functional of `(K̂, P̂)`). Pre-registered
gate: `≤ 0.15` rel. err. on the noiseless regime.

## 4. Embedded-data parity (DEV-TIME-ONLY, NOT a runtime dependency)

The pre-registered fixture is the **WSCC-9** system, transcribed
verbatim from Anderson & Fouad 2003 Ex. 2.6 (see the parent
`PROVENANCE.md`). pandapower is **not** a runtime dependency and is
**not** added to the runtime env.

A one-time DEV-TIME parity assertion was pre-registered: cross-check
the embedded IEEE-39 (Athay/Pai) `Ybus` against
`pandapower.networks.case39()` with a `rel.Frobenius ≤ 1e-8` hash-pinned
assertion. **Status: DEFERRED** — pandapower is not importable in this
environment (`python -c "import pandapower"` → `ModuleNotFoundError`).
Per the pre-registration this does **not** block CALIB-GRID-002 and
pandapower is **not** added to deps. Exact reproduction command for the
deferred check (run offline in an env with pandapower; the IEEE-39
fixture is not part of the pre-registered WSCC-9 verdict, so this is a
provenance nicety, not a gate):

```
python - <<'PY'
import numpy as np, pandapower as pp, pandapower.networks as ppn
from research.calibration.grid_kuramoto.grid_data import ieee_39_new_england
net = ppn.case39()
pp.runpp(net)
Y_pp = np.asarray(net._ppc["internal"]["Ybus"].todense())
sys = ieee_39_new_england()
# Compare the imaginary (susceptance) part of the embedded reduced model
# against the Kron-reduced pandapower Ybus on the matched generator nodes.
B_embedded = sys.susceptance
# (full Kron-reduction recipe documented in parent PROVENANCE.md §IEEE-39)
print("rel.Frobenius:", float(np.linalg.norm(... - ...)/np.linalg.norm(...)))
PY
```

`DEFERRED` value: pandapower not importable; assertion not evaluated;
no runtime dependency added; not on the CALIB-GRID-002 critical path.

## 5. M_i / D_i provenance

* **WSCC-9 (the pre-registered fixture):** the published Anderson &
  Fouad inertia/damping already embedded in `grid_data.py`. `H = [23.64,
  6.40, 3.01]` s → `m = 2H/ω_s`, `ω_s = 2π·60`; uniform `d_i = 2.0`
  p.u. (Dörfler–Bullo PNAS 2013 Fig. 1). No new machine data is
  introduced by CALIB-GRID-002.
* **IEEE-39:** not exercised by the pre-registered verdict. If a
  second-order IEEE-39 use is added later, `M_i / D_i` are **not** in
  the steady-state Athay/Pai case data and MUST be declared as a
  preregistered `unspecified → scenario sidecar` OPTION here, never
  silently assumed.

## 6. Null battery (minimal, mirrors the existing CALIB nulls)

* **Primary specificity null — topology-preserving payload shuffle.**
  Permute the per-node phase trajectories across nodes (preserving each
  node's marginal dynamics and the global record length) so the *true*
  edge structure is destroyed while the data statistics are matched;
  the weak-form support must NOT recover the true edges.
* **Flat-coupling placebo.** Simulate with a uniform (structureless)
  coupling so there is no edge contrast; the weak-form thresholded
  support must not manufacture a structured graph.

Empirical false-positive rate across the null battery is pre-registered
to be `≤ 0.05`.

## 7. Frozen-gate non-interference

Nothing here changes `PREREGISTRATION.md`, `gates.py`, the five frozen
CALIB-GRID-001 acceptance thresholds, the embedded IEEE data, the seeds,
σ, the θ₀ perturbation or the decision rule of CALIB-GRID-001 / R1. The
first-order path and the R1 differential swing path stay **bit-
identical** (verified by the existing bit-stability tests plus a new
CALIB-GRID-002 regression test). The frozen `noisy.frobenius` gate
**stays NEGATIVE** and is the differential-class boundary record;
CALIB-GRID-002 carries its own `cg002.*` gates and its own ledger.

## References

- Messenger, D. A., Bortz, D. M. (2021). *Weak SINDy for partial
  differential equations*. **J. Comput. Phys.** 443:110525.
- Messenger, D. A., Bortz, D. M. (2021). *Weak SINDy: Galerkin-based
  data-driven model selection*. **Multiscale Model. Simul.**
  19(3):1474–1497.
- Dörfler, F., Chertkov, M., Bullo, F. (2013). *Synchronization in
  complex oscillator networks and smart grids*. **PNAS**
  110(6):2005–2010.
- Anderson, P. M., Fouad, A. A. (2003). *Power System Control and
  Stability*, 2nd ed. IEEE Press / Wiley.
