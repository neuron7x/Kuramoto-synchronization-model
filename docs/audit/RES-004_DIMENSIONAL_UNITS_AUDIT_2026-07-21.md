# RES-004 — Dimensional / Units Audit of the physics laws (2026-07-21)

Purpose: prove every physics-law quantity is dimensionally consistent, and that no invariant
compares quantities of different dimension (a category error the system's "mechanism ≠ metaphor"
discipline forbids). Scope: the 7 falsification laws (T1–T8) + the core Kuramoto/neuro invariants.
Units are stated in SI base or explicitly **dimensionless [1]**; market quantities carry
[price] or [return]=[1] as noted.

## A. Dimensionless-by-construction (the load-bearing safety invariants)
| quantity | symbol | dimension | check |
|---|---|---|---|
| Kuramoto order parameter | R = \|⟨e^{iθ}⟩\| | **[1]** (mean of unit phasors) | INV-K1 0≤R≤1 is a pure ratio — dimensionless ✓ |
| serotonin / GABA / dopamine gates | s, g | **[1]** ∈[0,1] | gate = σ(·): logistic maps ℝ→[0,1] dimensionless ✓ |
| Ricci curvature (Ollivier) | κ | **[1]** (1 − W₁/d, ratio of two [length]) | INV-RC1 κ≤1 compares [1] to [1] ✓ |
| Kelly fraction | f* = μ/σ² | **[1]** (μ=[return], σ²=[return]²) ⇒ [return]⁻¹·… | see B: f* has [return]⁻¹, NOT [1] — flagged |
| cryptobiosis distress | T | **[1]** ∈[0,1] | combined normalized neuromod — dimensionless ✓ |

## B. Dimensional finding — Kelly f* = μ/σ²
μ has dimension [return] (=[1] if returns are log-returns, a pure ratio); σ² has [return]². So
f* = μ/σ² carries **[return]⁻¹**. For log-returns [return]=[1] ⇒ f* is dimensionless, and
INV-KELLY2 "applied fraction ≤ cap" (a [1] bound) is consistent ONLY under the log-return
convention. **Action:** the invariant registry must state returns are dimensionless log-returns;
if arithmetic returns in currency were ever used, f* would gain units and INV-KELLY2's [1] cap
would be a category error. Recorded as the one convention the audit makes explicit.

## C. Rate / time laws (must carry 1/[time])
| law | quantity | dimension | consistency |
|---|---|---|---|
| T2 Lyapunov spectrum | λ_k | **1/[time]** | Σλ_k=0 (INV-LY2) sums like-dimensioned rates ✓ |
| T3 calibration | target λ_1 | 1/[time] | residual ≤ tol compares [rate] to [rate] ✓ |
| T5 predictability horizon | τ = (1/λ_1)·ln(δ_tol/δ_0) | **[time]** | ln(ratio) is [1]; 1/λ_1 is [time] ✓; δ ratio dimensionless ✓ |
| T5 Landauer floor | E_min = k_B·T·ln(Δ/δ_0) | **[energy]** | k_B·T=[energy], ln(ratio)=[1] ✓ |
| T7 pinning | λ_2(L+Γ_P) | 1/[time] (graph-Laplacian eigenvalue on a rate operator) | > ε_pin compares [rate] to [rate] ✓ |

## D. Conservation / energy laws (must carry [energy] consistently)
| law | expression | dimension | consistency |
|---|---|---|---|
| INV-K8 swing energy | E = ½Σmθ̇² + V | [energy] if V=[energy] | V = −(K·N/2)R²: needs [K]=[energy] for consistency ⇒ K here is a coupling-energy, distinct from the T3 rate-K — **naming collision flagged** |
| T8 Jarzynski | ⟨e^{−βW}⟩=e^{−βΔF} | βW, βΔF **[1]** | β=1/(k_B T)=[energy]⁻¹, W,ΔF=[energy] ⇒ exponent dimensionless ✓ |
| INV-TH2 entropy production | ΔS ≥ 0 | [energy]/[temperature] | one-sided, like-dimensioned ✓ |

## E. Two naming collisions the audit surfaces (not errors, but must be documented)
1. **K** is used for BOTH the Kuramoto coupling-in-a-rate-context (T1/T3, where K·λ_max−2γ is a
   [rate]) AND the swing coupling-energy (INV-K8, where V=−(K·N/2)R² is an [energy]). Same symbol,
   two dimensions, different laws — legitimate but must be namespaced in docs.
2. **λ** is used for Lyapunov exponents (1/[time]) and for Laplacian eigenvalues (also 1/[time]
   in the pinning operator) — same dimension, coincidentally consistent; no action.

## Verdict
No dimensional VIOLATION found in any invariant's comparison (every ≤/=/≥ compares like-dimensioned
quantities). Two documentation actions: (1) declare the log-return convention that makes Kelly f*
dimensionless; (2) namespace the two meanings of K. Both are doc-hardening, not physics defects.
This audit is the RES-004 evidence artifact.
