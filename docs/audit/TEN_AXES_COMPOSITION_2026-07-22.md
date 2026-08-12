<!-- SPDX-License-Identifier: MIT -->
# Ten-axis composition profile — first measurement (2026-07-22)

## Why this exists

GeoSync enforced dozens of independent ratchets and nothing composed them. Each gate could be
green while the artifact as a whole was never stated. A doctrine that is not measured is not
held — it is decoration. `scripts/ci/check_ten_axes.py` measures it.

The ten axes: **elegance, aesthetics, beauty, simplicity, precision, adaptability, resistance,
coherence, completeness, reproducibility**.

## Rules of construction

These are what make the profile admissible rather than a self-flattering dashboard.

1. **No hand-assigned ratings.** Every probe is `score = 1 - debt / population`. `debt` comes
   from a ratchet ledger already frozen and enforced by its own gate; `population` is measured
   here from repository bytes (AST walk / file walk) at run time.
2. **Unmeasured is never 1.0.** A probe that cannot measure its population reports `UNMEASURED`,
   contributes nothing, and an axis with no measured probe is not scored at all. This is the
   same rule `geosync/proof/weighting.py` applies to falsification power, for the same reason:
   absence of measurement is not evidence of quality. Probe state is reset before every run so
   a probe that measured once and then went blind cannot keep reporting stale numbers.
3. **Weakest-link at both levels.** An axis scores as its worst probe; the repository as its
   worst axis. A mean would let three cheap 0.99 probes bury one 0.03 hole — and would reward
   *adding easy probes*. The mean is reported as `mean_informational` and is never the verdict.
4. **No invented threshold.** There is no defensible absolute line at which `aesthetics >= 0.7`
   becomes "good". There *is* a defensible statement that a measured axis must never move down.
   Monotonicity is the contract; the frozen profile is `docs/TEN_AXES_BASELINE.json`.
5. **Populations are never hand-picked, and the sample cannot be chosen.** Ledger discovery is
   repo-wide over *tracked paths* — not a directory glob, and not filenames either: the
   repository's canonical waiver store is a directory named `governance/waivers/` whose files
   carry no marker in their names at all, and it was invisible for four drafts. The
   ledger/not-ledger classification — including the prefix map, which is applied *before*
   classification — is
   complete-by-construction (an unclassified candidate raises), each exclusion carries a stated
   reason, and the whole classification is **frozen in the baseline** so a loaded ledger cannot
   be quietly reclassified out of the denominator. Whether a ledger grants an exception is
   decided *generically* over its contents rather than by reading a hand-named debt key —
   whoever names the key chooses the answer.
6. **Nothing is credited that does not verify HERE.** It is not enough for a debt to live in a
   ledger some other gate owns — that gate's scope may not cover the entry. So the two probes
   that bind the completeness axis re-derive their own credit: a mutation-ratchet enrolment
   counts only if its named tests exist, contain test functions, and actually *import* the
   module they claim to cover; an invariant counts as witnessed only if its witness file
   contains a test function **that directly imports the invariant's own declared source**.
   Ancestor-package imports are not credit: one `from core import x` vouched for every module
   under `core/`, and that single clause produced 379 of 583 false credits.

   Each of these was a live inflation vector, and the sequence is instructive. Reading the debt
   from an unenforced artifact moved the verdict 15×. Trusting the *enforced* ledger's enrolment
   moved it 30×, because `check_mutation_kill_ratchet.py` re-probes a module only when that
   module or its tests **change** — a newly added entry for an untouched module is never probed.
   Requiring the witness merely to exist was defeated by `tests/conftest.py`; requiring it to
   hold a test function was defeated by naming *any* unrelated test file. The rule that survives
   all of it: **a claim of coverage must be verifiable by the thing that reports it.**

## What is frozen, and the ten ways it can regress

A ratio alone is far too easy to move without improving anything, so the whole probe is frozen —
its score, its debt, its axis and its stated procedure. `compare()` fails closed on:

| class | what it catches | re-freezable |
|---|---|---|
| `AXIS REGRESSION` | the score fell | no |
| `DEBT INCREASE` | the debt grew | no |
| `POPULATION INFLATION` | the score rose while the debt did **not** fall — the denominator grew | yes, deliberately |
| `PROBE REMOVED` | the ruler was deleted | no |
| `UNMEASURED REGRESSION` | the ruler went blind | no |
| `LEDGER RECLASSIFIED` | a ledger was moved between the surveyed and excluded sets | no |
| `BASELINE INCONSISTENT` | the frozen axis block disagrees with its own frozen probes | no |
| `AXIS MOVED` | the probe was reassigned, rewriting *which* axis the report names as the hole | yes |
| `PROCEDURE CHANGED` | the stated measurement was edited; the number can be unchanged while meaning something else | yes |
| `UNFROZEN PROBE` | a probe exists that the baseline never saw | yes |
| `ENROLMENT REMOVED` | a module left the mutation-kill ratchet | no |
| `ENROLMENT ADDED` | modules joined the ratchet — not a failure, but never silent | yes, deliberately |

`POPULATION INFLATION` is the load-bearing one: **a score may only rise because the debt fell.**
Adding documents, files or tests grows denominators for free, and without this rule every ratio
drifts upward while nothing improves. Populations do legitimately grow, so a re-freeze may
*record* the movement — which puts it in the diff — but `--write-baseline` still refuses to
record a fallen score, a grown debt, a blinded probe or a reclassified ledger.

Deleting the baseline and re-freezing would still bypass the writer's refusal locally, which is
why CI passes `--against-ref origin/$CI_DEFAULT_BRANCH`: the working profile is also compared
with the baseline **as committed on the default branch**, read via `git show`, failing closed on
an unknown ref. The reference is the default branch and not the merge base for two reasons —
this project runs branch pipelines (there is no `workflow:`/`rules:` block, so
`CI_MERGE_REQUEST_DIFF_BASE_SHA` is always empty and a merge-base variant would be dead code),
and pinning it denies an author the choice of an old, favourable comparison point. The job sets
`GIT_DEPTH: 0` so history is present regardless of runner defaults. A ref that genuinely
predates the baseline is reported as the introducing change rather than failing forever — but
only if NO ten-axis profile existed at that ref under any name, since renaming the baseline
constant would otherwise be a one-line way to switch the historical arm off.

## Declared boundary — what this gate cannot verify

**Narrowed 2026-07-22 (first real paydown).** The original boundary read: no static check can
prove a mutation run happened, because `scripts/ci/check_mutation_kill_ratchet.py` re-probes a
module only when that module or its tests *change*, so an entry added for an untouched module
was never probed. Adversarial review of the first enrolment batch confirmed it in the worst
place — four of six new entries were accepted by the gate without ever being probed.

That specific hole is now closed at the source. The ratchet re-probes every **newly enrolled**
module (`set(ledger) - set(base)` is unioned into the probe set), and it cross-checks the
recorded `killed`/`total` against what the probe just measured, not merely the rate against the
floor. Enrolment is therefore verified at the one moment its numbers are first asserted: on the
MR that asserts them. Fabricating `99/99` for an untouched module now fails that MR.

**What remains open**, stated plainly: a module enrolled honestly today is not re-probed again
until it or its tests next change. Drift between changes is invisible to both gates. The
compensating control is the same one as before — the enrolment SET is frozen in
`docs/TEN_AXES_BASELINE.json`, so any growth surfaces as `ENROLMENT ADDED (n)` and requires a
deliberate re-freeze. Read `mutation_calibration` as **verified enrolment in an enforced
ratchet**, not as continuously-measured test strength, and see
`docs/audit/MUTATION_METRIC_VALIDITY_2026-07-22.md` for why a kill-rate is a question rather
than a verdict in the first place.

## First measurement

Measured on the tree of this change. Eighteen probes, all `MEASURED` — no axis is blind.

| Axis | Score | Bound by | Debt / population |
|---|---|---|---|
| elegance | 0.9711 | `symbol_complexity_budget` | 247 / 8534 symbols over the complexity budget |
| aesthetics | 0.7295 | `public_docstrings` | 1696 / 6270 public symbols undocumented |
| beauty | 0.2500 | `waiver_free_gates` | 21 / 28 waiver ledgers still grant exceptions |
| simplicity | 0.2353 | `namespace_singularity` | 13 / 17 shipped packages outside the `geosync` namespace |
| precision | 0.9318 | `type_escape_density` | 1650 / 24206 annotations are `Any` or `type: ignore` |
| adaptability | 0.8838 | `import_architecture` | 74 / 637 files with `src` imports or path hacks |
| resistance | 0.7975 | `broad_except_density` | 129 / 637 files with a broad `except` |
| coherence | 0.7154 | `golden_path_integrity` | 37 / 130 (document × target) make citations are dangling |
| **completeness** | **0.0283** | `mutation_calibration` | **619 / 637 runtime modules are not enrolled in the enforced mutation ratchet** |
| reproducibility | 0.7268 | `ambient_determinism` | 174 / 637 files with ambient nondeterminism |

Non-binding probes: `file_size_budget` 0.9592, `silent_procedure_density` 0.9975,
`rtm_direct_traceability` 1.0000 (0 of 13 requirements traced only indirectly), `gate_health`
0.9540, `invariant_witness_binding` 0.4015, `assertion_bearing_tests` 0.9933, `skip_free_tests`
0.9939, `runtime_print_free` 0.9827.

## What the profile says

**Repository verdict: completeness = 0.0283.** The binding fact is not a code-quality problem —
it is a *measurement coverage* problem. 18 of 637 runtime modules are enrolled in the enforced
mutation-kill ratchet. For the other 97.2% the test suite passes but nothing holds the tests to
being able to fail.

The first measurement read 0.0078 (5 of 637). The first paydown — 13 modules probed serially,
three blind guards found and closed — moved it to 0.0283. Seven further modules were probed and
**deliberately not enrolled** — `application/security/tls.py`, `core/compliance/models.py`,
`core/indicators/novelty.py`, `core/indicators/timeframe.py`, `core/io/parquet_compat.py`,
`core/utils/clock.py`, `core/utils/memory.py` — each probed **0/0 logic sites**, which the probe
reports as kill-rate 1.0. Enrolling them would have bought nine modules
of coverage for zero evidence. That trap is now refused by the gate rather than by discipline:
`check_mutation_kill_ratchet.py` rejects any enrolment whose measured `total` is zero.

This one number took four corrections, each found by adversarial review rather than by the gate
passing, and the sequence is the honest history of the probe:

1. Scored against the mutation manifest's own membership → **0.9957**. A manifest that lists only
   what has been probed scores 1.0 by construction.
2. Denominator widened to all runtime modules, but still crediting all 19 manifest entries →
   **0.0298**. Ten of those entries (`geosync_hpc/`, `modules/`, `research/`, `scripts/`) lie
   *outside* the runtime roots, so files the denominator never contained were buying credit.
3. Both sides restricted to the runtime roots → **0.0141**. Still wrong at the source: the debt
   came from `artifacts/test_strength/mutation.modules.json`, which **no gate enforces**. Writing
   637 fabricated entries into it moved the repository verdict to 0.219 with a green gate. A
   number anyone can write is not evidence, least of all for the probe that binds the verdict.
4. Debt repointed to `docs/MUTATION_KILL_BASELINE.json` — the ledger
   `scripts/ci/check_mutation_kill_ratchet.py` re-probes whenever an enrolled module or its
   tests change → **0.0078**. Enrolment now means an enforced floor, not a recorded measurement.

`invariant_witness_binding` (0.4015 — 79 of 132 declared invariants have no witness test bound)
is the second completeness fact and points the same way. It deliberately measures *binding*, not
whether a bound witness currently passes: scoring `(total − bound_green_floor) / total` against
a frozen integer would mean declaring a new invariant *lowers* the score and deleting invariants
raises it. Whether witnesses pass is `scripts/ci/audit_invariant_teeth.py`'s job.

**Second-weakest: beauty = 0.2500.** Twenty-one of the twenty-eight tracked waiver ledgers grant
at least one exception. Every exception is reviewed and reasoned, which is why these are ratchets
and not bugs — but a system needing a special case at three gates in four is not yet the general
thing it is trying to be. The seven waiver-free ledgers today are `descriptor_promotion_allow`,
`docs_consistency_allow`, `golden_path_allowlist`, `neuro_claim_boundary_allow`,
`rtm_traceability_allowlist`, `fast_quarantine.txt` and `forbidden_torch_jit_allowlist`.

This number moved 0.10 → 0.29 → 0.22 → 0.26 → 0.25 across five drafts *without the repository
changing*, purely by correcting what was surveyed and how loadedness was decided. Each move
closed a specific way of choosing the answer: the sample was hand-typed; discovery was scoped to
one directory and missed enforced ledgers in `.claude/`, `configs/` and `tests/ci/`; per-ledger
debt keys were named by hand; `.claude/commit_acceptors/*` were counted as standing waivers when
they are consumed once and can never be paid down; and a live waiver ledger
(`coverage_surface_allowlist`, which excludes a whole package from the release-coverage
denominator) scored waiver-free because its only keys were named `reason` and `note`. The number
is now discovered, not chosen — and its instability across drafts is the strongest evidence in
this document that a metric nobody attacks is a metric nobody should trust.

**Third: simplicity = 0.2353** — 13 of the 17 packages in the wheel surface are outside the
canonical `geosync` namespace. This is the known ADR-0024 residual (`B.wheel`), not new
information; the profile just prices it.

## How to move a number

Only by paying the debt the probe reads. There is no other input, and `DEBT INCREASE` blocks the
one arithmetic shortcut. Raising `mutation_calibration` means measuring more modules with
`tools/mutation_probe.py --only-logic` — and per
`docs/audit/MUTATION_METRIC_VALIDITY_2026-07-22.md`, a low kill-rate is a question, not a
verdict: check pairing, module attribution, and equivalent mutants before calling it a gap.

## Usage

```
python3 scripts/ci/check_ten_axes.py                    # profile + fail-closed regression check
python3 scripts/ci/check_ten_axes.py --json             # machine-readable report on stdout
python3 scripts/ci/check_ten_axes.py --against-ref REF    # also enforce vs the baseline at REF
python3 scripts/ci/check_ten_axes.py --write-baseline   # re-freeze; refuses to lower a score
```

CI job: `ten-axes-composition`. Teeth: `tests/test_ten_axes_gate.py` (47 cases).
