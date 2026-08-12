# Remaining teeth closure — and a measured limit of the instrument itself (2026-07-22)

Third pass over the recorded survivors. Two results matter: several more falsifiers were made
able to fail, and the mutation-attribution model was found to have a granularity limit that a
naive reading would have mistaken for weak tests.

## Closures (each proven by re-running the same probe)
| module | before | after |
|---|---|---|
| `core/neuro/cryptobiosis.py` | 93.8% (15/16) | **100.0%** (16/16) |
| `core/neuro/signal_bus.py` | 23.5% (4/17) | **82.4%** (14/17) → +3 more teeth in flight |

**cryptobiosis `:220 GtE→Lt`** — under the mutant the staged rehydration ramp completes on the
*first* advance, i.e. the system resumes full metabolism immediately after a threat instead of
ramping over `n_rehydration_stages`. Nothing asserted the stage count. The new test requires
REHYDRATING at every intermediate stage and ACTIVE only after the last.

**signal_bus `_update_regime`** — a four-branch classifier whose every comparison and boolean
join survived. The new truth table pins each branch *and each conjunct*: CRISIS needs **both**
deep-negative RPE and high serotonin (neither alone reaches it), ELEVATED fires from **either**
arm, RECOVERY only from a prior CRISIS with falling free energy. Plus the Protector-veto table
(strict threshold; a firing Protector **zeroes** the multiplier), the piecewise Kelly-coherence
bounds, and the history ring-buffer cap.

## A test that passed and killed nothing — caught by re-measuring
The first `spectral_gap` teeth **passed but killed zero mutants**. Two reasons, both instructive:
- `pytest.raises(ValueError)` also catches the *numpy broadcast* ValueError that the mutant itself
  raises, so the assertion could not discriminate. Fixed with `match="Expected square matrix"`.
- The negative-adjacency guards (`:515/:516`) feed **only the warning**, not the returned number,
  so any numeric assertion is blind to them. Fixed with a `caplog` assertion on the module's own
  stated observability contract ("a silent repair of a physical quantity must be surfaced").

This is the discipline working on its author: passing is not evidence until the mutant dies.

## The instrument's limit: module-level attribution dilutes a function-level claim
`research/robustness/cpcv.py` measured **45.9%**, which reads as a weak falsifier. It is not.
The claim `robustness-hac-psr-newey-west` asserts the **Newey–West HAC variant of the PSR**. Of the
20 survivors, only **three** lie in that scope (`_newey_west_effective_size:204`,
`probabilistic_sharpe_ratio_hac:292/:317`); the rest live in `cpcv_splits` and `estimate_pbo` —
code this claim does not assert at all.

Those three were closed (each is a fail-closed `or` guard that the mutant turns into an `and`, so a
single degenerate input — lag 0, a NaN sample, a collapsed effective size — would be computed on
instead of refused). The remaining sixteen were **deliberately not padded with tests**: writing
them would raise a module-level number without strengthening the claim, which is metric gaming.

**Recorded limitation:** the weighting layer joins mutation evidence to claims **per module**,
while a claim may assert one function of a larger module. Until attribution is function-scoped, a
module-level kill-rate is a *lower bound* on the claim's falsifier strength, and this document is
the reason a low number must be investigated rather than "fixed".

## Third measured limit: three survivors are EQUIVALENT MUTANTS (empirically proven)

The three in-scope `cpcv` survivors (`:204`, `:292`, `:317`) did **not** die after the new tests
were added. Rather than assume weak tests, the hypothesis was tested directly: both the original
and the `Or→And`-mutated module were loaded side by side and evaluated on the degenerate inputs.

```
case                           original           mutant   same?
_nw_effective_size lag=0            6.0              6.0    True
hac_psr NaN sample                  nan              nan    True
hac_psr constant                    nan              nan    True
hac_psr normal                      1.0              1.0    True
```

**Byte-identical on every input.** The guards are fast-path/explicitness constructs whose
fall-through produces the same value (NaN propagates through the arithmetic; a Bartlett sum over
`range(1, 0+1)` is empty, so the effective size is already `n`). These mutants are *unkillable by
any test* — a known mutation-testing phenomenon, not a teeth gap.

The new tests are kept regardless: they pin the contract explicitly (lag 0 → n, NaN → NaN,
degenerate effective size → NaN) even though the metric cannot credit them.

## The three limits, together
A mutation number lies in both directions unless it is investigated:
1. **A test can pass and kill nothing** — `pytest.raises(ValueError)` also caught the ValueError the
   mutant itself raised, so the assertion could not discriminate (fixed with `match=`).
2. **Module-level attribution under-reports** a claim that asserts one function of a large module
   (cpcv 45.9%).
3. **A survivor can be unkillable in principle** — the three equivalent mutants above.

Recorded so that nobody later "fixes" 45.9% by padding tests. The honest reading of that number is
*investigated and explained*, not improved.
