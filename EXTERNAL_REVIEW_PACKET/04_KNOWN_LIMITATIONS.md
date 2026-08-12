# Known Limitations

> Already-disclosed weakness inventory. Source-of-truth:
> `research/systemic_risk/LIMITATIONS.md`. This is a synopsis.

## Domain

* No real-data run — every PASS so far is on synthetic stand-ins.
* No mechanism claim — phase-locking *correlation* with crisis
  onset would be associational, not causal.
* Network coverage limited (e-MID is Italy-only; BIS LBS is
  jurisdiction-aggregated).

## Statistical

* Small N of crises — Bonferroni at k=3 gives α_per_crisis ≤ 0.0033
  for FWER α=0.01. Below 3 valid windows the verdict is structurally
  UNDECIDED.
* Bootstrap CI undercoverage at small n — percentile CI may sit at
  0.92-0.93 actual coverage at n_pre_event ≈ 60.
* No walk-forward validation on real data yet.

## Modelling

* Sakaguchi α frozen at zero in the production score — full α
  estimation lives in `core.kuramoto.frustration` and is not yet
  engaged on real data.
* First-order ω estimator (sample-σ × 2π·fs); the proper Lomb-
  Scargle estimator is gated on a flag-day decision.
* Static crisis ledger — Western + 2023 anchors only.

## Engineering

* `core/kuramoto/jax_engine.py` carries 5 pre-existing
  `mypy --strict` errors. Out of scope for this module's quality
  gate.
* The `scripts/export_governance_schemas.py` helper is sensitive to
  local Python `sys.path` ordering when an editable `geosync`
  package is installed. CI environment is clean.

## Outstanding gaps (post-2026-05-08 self-audit)

* Real-data ingest pipeline (e-MID / ECB MMSR) — licence-restricted.
* Evaluation on 2008 / 2011 / 2020 — blocked by data feed.
* AUC > 0.75 on real data — blocked.
* Zenodo publication — requires user account credentials.
* Daily SHA256 verification of real-data runs — blocked.
* External adversarial review — **this packet** is the readiness
  artefact.
