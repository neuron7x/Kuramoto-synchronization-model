# 05 — Next Empirical Chapter (pre-registration)

The infrastructure chapters (`00`–`04`) establish *admissibility* governance.
This chapter pre-registers the first **empirical** study — and binds it, in
advance, to a falsification frame so it cannot be promoted into a profitability
claim.

## Study: real-data L2 Ricci replay as a FALSIFICATION study

**Question (falsification, not profitability):** does the L2 microstructure Ricci
descriptor survive its pre-registered nulls and leakage/cost falsifiers on a real
recorded order-book session — or is it killed?

**Status:** NOT STARTED. Gated on a recorded depth-5 dataset + deterministic
replay (unavailable in the current environment). Until then the claim tier is
**HYPOTHESIS/OBSERVE**, never MEASURED.

## Pre-registered design (binding before any data is touched)

1. **Data source** — one real depth-5 order-book session; record `venue`,
   `symbol`, `time_range`, `git_sha`, `data_sha256`, `config_sha256`
   (minimum-evidence schema; non-zero hashes mandatory).
2. **Method** — fixed, committed descriptor + horizon; no post-hoc parameter
   search.
3. **Falsifiers (must all run, pre-committed):**
   - permutation null, phase-randomized (IAAFT) null, topology-preserving null;
   - cost-model falsifier (negative net-of-cost ⇒ REJECT);
   - lookahead/leakage detector (positive + negative control);
   - timestamp-integrity check.
   (All six already executable — `governance/FALSIFIER_LEDGER.yaml`.)
4. **Replay path** — a single command that recomputes the artifact from the
   recorded data + a deterministic seed.
5. **Verdict rule (pre-set):** the descriptor is *admissible as a measured
   observation* only if it beats every null and survives every falsifier; a
   single failed falsifier ⇒ REJECT, recorded as preserved negative evidence
   (`governance/NEGATIVE_EVIDENCE.yaml`).

## Forbidden in this chapter (binding)

- NO profitability, alpha, edge, or deployability claim — regardless of outcome.
- NO parameter tuning after seeing returns.
- NO promotion of a survived null into "validated"; survival ⇒ "not refuted on
  this dataset", nothing more.
- NO claim without non-zero `data_sha256` + a runnable replay command.

## Success criterion (for the chapter, not for trading)

A reviewer can re-run the replay command from the recorded dataset and obtain the
identical verdict (REJECT or NOT-REFUTED). The scientific contribution is the
*falsification verdict and its reproducibility*, not any economic value.
