# Mathematical Foundations — Sketch of the Phase-Locking Precursor Claim

This document sketches the formal mathematical content underpinning
the systemic-risk-as-phase-transition hypothesis. It is a **proof
sketch**, not a publication-grade derivation; references to primary
literature are given inline so a reader can fill in the details.

---

## 1. Hypothesis (formally stated)

Let $G_t = (V, E_t, W_t)$ be a directed weighted exposure graph at
time $t$, with $|V| = N$ banks and $W_t \in \mathbb{R}_{\ge 0}^{N \times N}$
the matrix of bilateral exposures. Define the Sakaguchi-Kuramoto
dynamics

$$
\dot{\theta}_i(t) = \omega_i + \frac{1}{N}\sum_{j} W_{ij}(t)\,
   \sin\!\bigl(\theta_j(t) - \theta_i(t) - \alpha_{ij}\bigr)
\qquad (1)
$$

with natural frequencies $\omega_i$ derived from per-bank stress
indicators (volatility, leverage, liquidity), and per-edge phase
frustration $\alpha_{ij} \in [-\pi/2, \pi/2)$.

The Kuramoto order parameter

$$
r(t)\,e^{i\psi(t)} = \frac{1}{N}\sum_{j=1}^{N} e^{i\theta_j(t)}
\qquad (2)
$$

is the verdict-bearing scalar.

**Claim H1 (precursor):** Let $\tau_*$ be the onset time of a
banking-crisis event (formally defined by the BIS / IMF Laeven-Valencia
ledger). Then

$$
\mathbb{P}\bigl[\, r(t) \ge r_{\text{crit}} \,\big|\, t \in [\tau_* - L,\, \tau_*)\,\bigr]
\;>\;
\mathbb{P}\bigl[\, r(t) \ge r_{\text{crit}} \,\big|\, t \notin \cup_e [\tau_e - L,\, \tau_e)\,\bigr]
\qquad (3)
$$

for some lead-time window $L$ (typically 30–120 trading days) and
some critical threshold $r_{\text{crit}}$. The empirical falsification
contract requires the AUC of the corresponding two-distribution test
to satisfy

$$
\mathrm{LB}_{95\%}\!\bigl[\mathrm{AUC}\bigr] > 0.70
$$

after Bonferroni correction across the full prosecutor roster.

---

## 2. Bifurcation theory of (1) on directed scale-free graphs

### 2.1 Mean-field reduction (Restrepo-Ott-Hunt 2005)

For the standard ($\alpha = 0$) Kuramoto on a directed weighted
graph $W$, define

$$
H_i = \frac{1}{N}\sum_{j} W_{ij}\, e^{i\theta_j}, \qquad
H_i = h_i\,e^{i\phi_i}.
$$

The mean-field reduction gives the self-consistency equation

$$
h_i = \frac{1}{N}\sum_{j} W_{ij}\, h_j\,
   F\!\bigl(\,h_j / \omega_j\,\bigr)
\qquad (4)
$$

where $F$ is a bounded analytic kernel. Linearising (4) around the
incoherent fixed point $h_i \equiv 0$ yields the spectral condition

$$
K\,\lambda_{\max}(W) \;\ge\; \lambda_c(g)
\qquad (5)
$$

where $\lambda_{\max}(W)$ is the leading eigenvalue of $W$ and
$\lambda_c(g)$ depends only on the natural-frequency density $g$.
For a Lorentzian $g$ with width $\gamma$, $\lambda_c(g) = 2\gamma$.

This is the **synchronization-onset boundary** that GeoSync's
``core/kuramoto/kuramoto_ricci_engine.py`` evaluates as ``Φ = K λ - 2γ``.

### 2.2 First-order character on scale-free $W$ (Gómez-Gardeñes 2011)

When $W$ has a heavy-tailed degree distribution
$P(k) \sim k^{-\gamma_d}$ with $\gamma_d \in (2, 3)$ and the
correlation $\langle \omega_i\,k_i \rangle$ is non-trivial — *i.e.*
high-degree banks are also high-stress — the bifurcation in (5)
becomes a **discontinuous (first-order) transition** with
hysteresis. Empirically, this means

$$
r_{\text{onset}}^{\text{up}} - r_{\text{onset}}^{\text{down}} > 0
\qquad (6)
$$

between the forward and reverse coupling sweep at fixed
$\langle k \rangle$ (Gómez-Gardeñes et al. 2011, eq. 4). This is the
diagnostic that ``research.systemic_risk.kuramoto_extensions
.explosive_sync_sweep`` measures directly.

### 2.3 Crisis as approach to (5)

The **precursor mechanism** is the claim that real interbank
exposure data, viewed through the lens of (1), has

$$
K(t)\,\lambda_{\max}\!\bigl(W(t)\bigr)\, \uparrow \,\lambda_c(g(t))
\qquad \text{as} \qquad t \to \tau_*^{-}
$$

— *i.e.* the system approaches the bifurcation boundary from below
during the lead-time window, and **crosses** it only at $t = \tau_*$.
The discontinuous character on heavy-tailed $W$ (§ 2.2) means $r$
abruptly jumps from sub-critical to super-critical, which is what we
hypothesise to **see in $r(t)$ before the crisis is officially
declared** (the AUC in (3)).

---

## 3. Why a precursor is *plausible* but *not yet established*

Three caveats encoded in the empirical contract:

1. **Identifiability of $\omega_i$.** We do not directly observe the
   natural frequency. We *derive* it from balance-sheet stress
   indicators. Misspecification of the $\omega$-stress map biases
   $r(t)$ in unknown directions.

2. **Stationarity of $W$.** The mean-field analysis assumes the
   coupling matrix evolves slowly relative to the Kuramoto
   relaxation time. In reality $W$ moves on quarterly to annual
   scales while phases relax in days; the time-scale separation is
   borderline.

3. **Confounding by exogenous shocks.** Banking crises are caused
   by both endogenous (Minskian) and exogenous (e.g. sovereign
   default) drivers. A precursor signal may be picking up macro
   stress that is correlated with — but not causally upstream of —
   the bifurcation.

The Adversarial Baseline Ladder (pillar 4) and the Leakage Sentinel
(pillar 5) operationalise the falsification of (3) under each of
these caveats.

---

## 4. The Bayesian update

Let $\pi_0 = \log\mathrm{odds}\!\bigl[H_1\bigr]$ be the prior log-odds
of (3). Observing crisis $e$ with empirical AUC $\widehat{\mathrm{AUC}}_e$,
the posterior is

$$
\pi_e = \pi_{e-1} + \log \mathrm{BF}_{10}\!\bigl(\widehat{\mathrm{AUC}}_e\bigr)
$$

with the **rigorous** form (Wagenmakers 2007 BIC approximation, see
``research.systemic_risk.bayes_rigorous``)

$$
\log \mathrm{BF}_{10} \;=\; \tfrac{1}{2}\bigl(\,Z^2 \;-\; \log n_{\text{eff}}\,\bigr),
\qquad
Z = \frac{\widehat{\mathrm{AUC}} - 0.5}{\sqrt{\sigma_0^2}}
\qquad (7)
$$

with $\sigma_0^2 = \tfrac{n_++n_-+1}{12 n_+ n_-}$ (Mann-Whitney 1947)
and $n_{\text{eff}} = \tfrac{n_+ n_-}{n_++n_-+1}$.

This **does not** assume $H_1$ specifies a point alternative — the
BIC approximation marginalises over a unit-information Gaussian
prior on the noncentrality. The **Lindley penalty** $-\tfrac{1}{2}\log n_{\text{eff}}$
ensures that uninformative data (Z near 0) drives BF below 1, *i.e.*
favours $H_0$, even when AUC is exactly 0.5.

---

## 5. Decision-theoretic threshold

Under a 0/1 cost matrix with cost $c_{\text{FK}}$ for falsely killing
a true claim and $c_{\text{FP}}$ for falsely passing a false claim,
the Bayes-rule decision boundary is

$$
\pi^{\,*} = \log\!\left(\frac{c_{\text{FK}}}{c_{\text{FP}}}\right)
\qquad (8)
$$

(Berger 1985, §4.4). The default GeoSync calibration
$\pi^{\,*} = -5$ corresponds to $c_{\text{FK}}/c_{\text{FP}} \approx 1/148$:
**killing a true claim is roughly 150× cheaper than passing a false
one** — a falsification-first calibration explicitly stated.

---

## 6. Pre-registration commitment

The above closes the loop: (1) → (5) → (6) → (3) → (7) → (8).
**Before any real-data evaluation**, this proof sketch and the
calibration constants are frozen. Any future relaxation of $r_{\text{crit}}$,
of the lead-time window $L$, or of $\pi^{\,*}$ post hoc constitutes
**crisis-date tuning** in the sense of leakage sentinel S6 and
triggers ``INVALIDATE``.

The pre-registration contract is a sha256 over this file plus the
``research/systemic_risk/PROTOCOL.md`` config snapshot, recorded in
the next ``RunManifest.config_hash`` whenever real data is
ingested.

---

## References (canonical primary sources)

* Akaike, H. (1974). "A new look at the statistical model identification". *IEEE Trans. Automatic Control*.
* Bamber, D. (1975). "The area above the ordinal dominance graph and the area below the receiver operating characteristic graph". *J. Math. Psychology*.
* Berger, J. O. (1985). *Statistical Decision Theory and Bayesian Analysis*. Springer.
* Birkhoff, G. (1948). *Lattice Theory*. AMS.
* Clauset, A., Shalizi, C. R. & Newman, M. E. J. (2009). "Power-law distributions in empirical data". *SIAM Review*.
* Gómez-Gardeñes, J., Gómez, S., Arenas, A. & Moreno, Y. (2011). "Explosive synchronization transitions in scale-free networks". *Physical Review Letters*.
* Mann, H. B. & Whitney, D. R. (1947). "On a test of whether one of two random variables is stochastically larger than the other". *Annals of Math. Statistics*.
* Restrepo, J. G., Ott, E. & Hunt, B. R. (2005). "Onset of synchronization in large networks of coupled oscillators". *Physical Review E*.
* Sakaguchi, H. & Kuramoto, Y. (1986). "A soluble active rotator model showing phase transitions via mutual entrainment". *Progress of Theoretical Physics*.
* Schwarz, G. (1978). "Estimating the dimension of a model". *Annals of Statistics*.
* Skardal, P. S. & Arenas, A. (2019). "Abrupt desynchronization and extensive multistability in globally coupled oscillator simplices". *Physical Review Letters*.
* Wagenmakers, E.-J. (2007). "A practical solution to the pervasive problems of p-values". *Psychonomic Bulletin & Review*.
