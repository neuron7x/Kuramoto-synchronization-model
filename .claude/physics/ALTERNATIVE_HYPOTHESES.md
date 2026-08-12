# Alternative Hypotheses Registry

> **Status:** living document. **Purpose:** every load-bearing GeoSync claim
> (synchronisation regime, criticality, OOS alpha) must demonstrably survive
> the alternatives below before it is allowed in `README.md`, a paper, or a
> pitch deck. The 2026-04-30 external audit explicitly required this file
> ([`docs/audit/2026-04-30-external-audit.md`](../../docs/audit/2026-04-30-external-audit.md)).

A signal that "looks like Kuramoto synchronisation" is not Kuramoto
synchronisation if a simpler null model produces the same statistic. The
six alternatives below are the minimum battery a claim must clear; they
are deliberately ordered from cheapest-to-test to most-cumulative.

---

## H1 — Correlation clustering

> Assets move together because of common market beta, not Kuramoto-style
> phase coupling.

* **Signature it can mimic:** elevated `R(t)` when many assets co-move,
  i.e. exactly the regime GeoSync currently flags as "synchronised".
* **Discriminator:** subtract a 1-factor (market) or 3-factor
  (market/sector/style) projection from each return series and recompute
  `R(t)` on the residuals.
* **Pass criterion:** post-residualisation `R_resid(t)` retains
  ≥ 50% of the SNR (Sharpe-like) advantage of `R_raw(t)` against the same
  benchmark, after multiple-testing correction.
* **Status:** test stub at `tests/research/alt_models/test_factor_residualised_R.py`
  (TODO — to be implemented as part of the audit follow-up).

## H2 — Volatility regime shift

> `R(t)` tracks volatility compression / expansion, not phase synchronisation.

* **Signature it can mimic:** monotone relationship between `R(t)` and
  realised volatility, presented as evidence of a "phase transition".
* **Discriminator:** condition on a fixed-volatility window (e.g.
  `realised_vol ∈ [σ_lo, σ_hi]`) and check whether the `R(t)` advantage
  survives within the band.
* **Pass criterion:** `R(t)` retains predictive lift conditional on
  matched-volatility buckets; ratio ≥ 0.5 of unconditional lift.
* **Status:** partially covered by `tests/research/cross_asset_kuramoto/`
  (vol-conditioned diagnostics) but not lifted to gating status yet.

## H3 — Sector / factor exposure

> Apparent phase alignment emerges from shared exposure to SPY, rates, USD,
> oil, liquidity — not endogenous coupling.

* **Signature it can mimic:** synchronisation peaks that cluster around
  macro events (FOMC, oil shocks, USD moves).
* **Discriminator:** fit a multi-factor regression
  ``r_i(t) = α_i + Σ β_{ij} F_j(t) + ε_i(t)`` and run all GeoSync metrics
  on `ε_i(t)` (factor-neutral residuals).
* **Pass criterion:** factor-neutral `R(t)` is significantly different
  from a permutation null at p < 0.01 after Holm correction.
* **Status:** not yet implemented at gate level.

## H4 — Hilbert-transform artefacts

> Phase extraction on non-oscillatory financial series can manufacture
> instantaneous phase that has no oscillator behind it.

* **Signature it can mimic:** smooth-looking `θ_i(t)` traces, broadband
  `R(t)` that responds to anything with low-frequency content.
* **Discriminator:** repeat every analysis with at least 3 phase
  extractors — Hilbert, complex Morlet wavelet, ranks of returns,
  return-sign — and compare. A genuine signal is invariant. An artefact
  is not.
* **Pass criterion:** signed lift remains ≥ 0.5× the Hilbert lift across
  *all* phase extractors. Sign flips or > 50% lift loss → reject.
* **Status:** wavelet path partially covered in `core/kuramoto/phase_extractor.py`
  (multi-extractor mode); rank/sign extractors are TODO.

## H5 — Threshold artefacts

> Any bounded noisy statistic with a tuned threshold can produce the
> appearance of a regime transition.

* **Signature it can mimic:** "phase transition" reported because `R(t)`
  crossed a chosen threshold τ; under bootstrap, τ-crossings happen at
  similar rates in pure noise.
* **Discriminator:** report **finite-size scaling** — run `R_N(K)`,
  `χ_N(K) = N·Var(R)`, `K_c(N)` for `N ∈ {8, 16, 32, 64, 128}` and check
  whether a scaling collapse exists. No collapse → no criticality.
* **Pass criterion:** scaling exponents `(β/ν, γ/ν)` stable across at
  least three N values; null-model `χ_N(K)` peak does not match observed
  peak.
* **Status:** **NOT YET DONE.** The repo currently uses thresholds on
  `R(t)` without a finite-size-scaling proof. Until this is in place,
  the term "criticality" must be replaced with "regime threshold" in all
  user-facing documentation.

## H6 — Synthetic-data circularity

> If the synthetic generator embeds the very structure the detector
> recovers, the recovery is not market evidence — it is a mirror
> applauding itself.

* **Signature it can mimic:** "OOS validation" in which the OOS data
  comes from the same generator (or a close cousin) used during model
  development.
* **Discriminator:** for every OOS claim, declare a `data_provenance`
  field in the audit JSON: ``synthetic`` / ``historical-real`` /
  ``live-paper``. Synthetic results may not back any user-facing alpha
  claim.
* **Pass criterion:** every numerical claim that appears in `README.md`
  or `BASELINE.md` headline metrics has provenance ``historical-real``
  or ``live-paper``, signed in
  `artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json`.
* **Status:** synthetic-only claims are currently being audited and
  retracted as part of the 2026-04-30 cleanup pass.

---

## How to register a passing claim

1. Write the experiment in `experiments/`.
2. Emit a `result.json` containing the alternative-hypothesis battery and
   the pass/fail verdict per H1–H6.
3. Sign it into `artifacts/audit/SCIENTIFIC_VERIFICATION_REPORT.json` via
   `python scripts/build_verification_report.py`.
4. Only then update `BASELINE.md` and the README headline.

A claim that has not cleared at least H1 + H2 + H4 + H5 is **not**
allowed in headline copy. Use `CLAIMS.md` to track in-flight claims.
