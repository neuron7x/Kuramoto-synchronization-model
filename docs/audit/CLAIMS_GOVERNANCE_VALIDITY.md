# Claims-Governance Weighting — Validity & Value Proof

**Artifact:** `geosync/proof/weighting.py` (epistemic-integrity measure **E**)
**Consumes:** `artifacts/geosync_proof/audit.json` × `docs/MUTATION_KILL_BASELINE.json` ∪ `artifacts/test_strength/mutation.modules.json`
**Reproduce:** `python -m geosync.proof.weighting`
**Scope of the weight:** `logic:compare+boolop` mutation kill-rate (`mutation_probe --only-logic`) — **not** full mutation coverage.

This document leads with what is **wrong or unproven** about the measure, then states what
it validly buys. That order is deliberate: a governance instrument that opens with its own
strengths is selling, not auditing.

---

## 1. Self-critique first — the failure modes of E

These are the standing weaknesses of the measure as shipped. None is hidden inside the
number; each is co-reported by the artifact so a reader hits it before the headline.

### 1.1 Today the measure calibrates nothing — the honest negative
Joining all **27** registered `CLAIMS.yaml` falsifiers to the **9** modules that have any
recorded logic-mutation evidence (via `evidence_paths` source files **and** via the
records' `tests` field): **0 / 27 join** (reproduced below in §4). The set of modules with
demonstrated teeth and the set of modules behind the canonical claims are **disjoint**.
Consequently `calibration_coverage` is `0/0 → n/a`, and against the committed
`audit.json` (a resolve-only run: all 27 `NOT_TESTED`) the headline is `E = 0.5`. That 0.5
is the **neutral fixed point of the scale, not a passing grade** — it is exactly what a
fully-untested audit should score. The first honest output of this layer is a **negative
result**: the teeth-measurement machinery and the claims registry are not yet connected.
The measure reports this loudly rather than laundering unmeasured falsifiers into green.

### 1.2 `E = 0.5` for an all-untested audit can be misread as "half good"
Because the signed scale maps `g = 0` (untested / neutral) to `(0+1)/2 = 0.5`, a corpus
with no verified and no refuted claims sits at 0.5. This is **principled** (0 net epistemic
force) but **not intuitive** to a reader expecting 0-to-100 "quality". Mitigation, not fix:
**E is never valid without `calibration_coverage` beside it.** A 0.5 at coverage `n/a`
means "nothing is actually verified", and the summary line prints the two together. Reading
E alone is a misuse the artifact structurally discourages but cannot forbid.

### 1.3 The weight measures LOGIC-falsification power only
`falsification_power` is the compare/boolop kill-rate from `--only-logic`. Constant,
arithmetic, and control-flow mutants are **out of scope**. A falsifier that pins every
comparison but ignores a wrong constant will score high here while missing a real class of
bug. The scope string rides on every power value; the number must never be read as
"mutation coverage".

### 1.4 Small-n teeth are treated the same as large-n teeth in the scalar
`power = 1.0` from `total = 3` (e.g. `gauss_bonnet`, 3 mutants) and `power = 1.0` from
`total = 26` (`stuart_landau_es`) both collapse to the scalar `1.0`. The **evidence
strength differs** — 3 killed mutants is a weaker demonstration than 26. The mutant count
`n_mutants` is carried alongside every power value as provenance, but the **headline E does
not down-weight small-n**. A reader auditing a specific claim must inspect `n_mutants`; the
scalar alone hides sample size. We deliberately did **not** invent an n-weighting function,
because any such curve would be a hand-tuned constant — the discipline forbids it more than
it forbids the omission.

### 1.5 Measured-zero and unmeasured both scalar to 0.0
A SUPPORTED with a **measured** toothless falsifier (`killed=0/total=8`) and a SUPPORTED
with **no** recorded evidence both contribute `g = 0` and `calibrated_support = 0`. They are
epistemically different (one is a demonstrated failure to bite, the other is unknown), and
the artifact **does** distinguish them by `power.state` (`MEASURED` vs `UNMEASURED`) and by
`calibration_coverage` (the measured-zero counts as calibrated, the unmeasured does not).
But in the single scalar E they are indistinguishable. The distinction survives only in the
per-claim rows.

### 1.6 The join is inferred, not declared
`CLAIMS.yaml` has no explicit `claim → mutation-module` pointer. The join is inferred from
`evidence_paths` (source files) and the records' `tests` field. This inference is why the
honest result is `0/27` and is the **first thing to fix** (§6). An inferred join can also
mis-attribute: if a claim's `evidence_paths` happened to name a mutated module the falsifier
does not actually exercise, the claim would borrow teeth it did not earn. No current claim
triggers this (0 join), but the risk is real until the pointer is explicit.

### 1.7 Trusted inputs
E trusts `audit.json` to have classified verdicts correctly and the mutation manifests to
be honest counts. It re-hashes all three inputs into a tamper-evident envelope (§5), so
**tampering is detectable**, but a verdict that is wrong *upstream* (a mis-classified
SUPPORTED) propagates. E calibrates the audit's SUPPORTEDs; it does not re-litigate them.

---

## 2. What the measure is

Given the categorical audit (each claim → `SUPPORTED / REFUTED / DANGLING / NOT_TESTED /
FORBIDDEN_LANGUAGE`), E answers the question the categorical verdict cannot: **how much is a
SUPPORTED worth?** A SUPPORTED backed by a falsifier that kills no injected mutant is a green
light with no bulb — "a test that cannot fail is worthless" (Karpathy). So each SUPPORTED is
calibrated by its falsifier's **demonstrated** logic-mutation kill-rate.

### 2.1 Falsification power ∈ [0,1] — the only measured weight
For a claim, pool the recorded logic-mutation runs of the module(s) its falsifier
exercises:

```
matched  = records whose module ∈ claim.evidence_paths, OR whose `tests` include the falsifier's test file
killed   = Σ matched.killed
total    = Σ matched.total          (total = valid_mutants for the test_strength manifest)

no match      → UNMEASURED(no_record)      — sentinel, not a number
total == 0    → UNMEASURED(zero_mutants)   — no teeth DEMONSTRATED (NOT perfect teeth)
otherwise     → killed / total ∈ [0, 1]    — MEASURED
```

Every input is a count emitted by `tools/mutation_probe.py --only-logic`. No constant is
hand-assigned.

### 2.2 The anti-laundering rule
`mutation_probe.Report.kill_rate` defaults `total == 0 → 1.0` (an unmeasured test looks
maximally strong). The weighting **does not inherit this.** `UNMEASURED` is a distinct
sentinel carrying `value = None`; when a scalar is unavoidable it floors to `0.0`
(`UNMEASURED_SCALAR_FLOOR`), **never 1.0**. An unmeasured SUPPORTED earns zero calibrated
support — fail-closed, matching the categorical audit's own posture. `0.0` is the only
non-arbitrary floor: any positive ε would itself be an unprovenanced magic constant.

### 2.3 Per-claim signed force g ∈ [−1, 1]
```
g(SUPPORTED)                                = falsification_power.scalar()   (0.0 if toothless/unmeasured)
g(NOT_TESTED)                               = 0
g(REFUTED) = g(DANGLING) = g(FORBIDDEN_LANGUAGE) = −1
```
`{−1, 0, +1}` are the **definitional endpoints** of the scale, not tuned values. `DANGLING`
maps to `−1` (not an interior value) because the source audit already classes it `REJECT`: a
named-but-uncollectable falsifier is a phantom guarantee, as bad as one that fired.

### 2.4 Aggregation — weakest-link gate × size-weighted strength
```
E = G · Σ_c (g(c) + 1) / (2N)

  N   = number of scored claims        (a measured count — the only size weight)
  (g+1)/2  = exact affine remap of [−1,1] → [0,1]  (parameter-free)
  G   = reject gate = 0 if ANY claim is REJECT-class (REFUTED/DANGLING/FORBIDDEN_LANGUAGE), else 1
```
`G` mirrors the categorical audit's own weakest-link aggregate. **Proof of weakest-link
dominance:** any REJECT-class verdict ⇒ `G = 0` ⇒ `E = 0`, independent of how many green
claims exist. A REFUTED P0 can never be hidden behind green P2s. Per-priority **floors**
(`min g` per band) are co-reported as diagnostics; priority is expressed **structurally**
(which band, which floor), never as a numeric multiplier.

> **Design note (why a GLOBAL gate, not a P0/P1-band gate).** An earlier merge candidate
> gated only the P0/P1 bands, which would let a P2 REFUTED slip past the gate. That
> disagrees with the source audit, whose aggregate is `any REJECT-class ⇒ REJECT` over ALL
> claims. The global reject gate here is the stricter and *consistent* choice: E collapses to
> 0 exactly when — and only when — the categorical audit would REJECT.

---

## 3. Why there are no magic numbers

| Quantity in E | Source | Not a magic number because… |
|---|---|---|
| `falsification_power` | `killed / total` from `mutation_probe --only-logic` | a measured procedure output |
| `g = −1 / 0 / +1` | definitional scale endpoints | they *define* the [−1,1] axis; no interior value is chosen |
| `(g+1)/2` | affine remap | exact, parameter-free rescale of [−1,1]→[0,1] |
| `UNMEASURED → 0.0` | fail-closed floor | the only non-arbitrary floor; any ε>0 would be unprovenanced |
| `G ∈ {0,1}` | audit REJECT-class membership | reuses `geosync.proof.audit.verdict_class`; no new constant |
| `N`, `Σmax = 2N` | claim counts | measured cardinalities |
| tier / priority | **reported, not multiplied** | folding them in would require per-tier constants — forbidden |

Tier (`ANCHORED`/`EXTRAPOLATED`) and priority (`P0/P1/P2`) are kept as **separate reported
axes**. E's own tier follows an exact rule (no threshold): `ANCHORED` iff there is ≥1
SUPPORTED claim **and** every SUPPORTED one has MEASURED teeth (`coverage == 1.0`) **and**
nothing is rejected; otherwise `EXTRAPOLATED`.

---

## 4. The honest negative, reproduced

```
$ python -m geosync.proof.weighting --no-write
E=0.5000 tier=EXTRAPOLATED reject_gate=1 calibration_coverage=n/a (0/0 SUPPORTED calibrated) N=27 scope=logic:compare+boolop (mutation_probe --only-logic)
```
Annotated join accounting behind that line (from the same `build_report`):
```
recorded modules: 9      claims: 27      joined to mutation evidence: 0
verdict tally: {NOT_TESTED: 27}   (audit.json is a --resolve-only pass)
```
The 9 modules with demonstrated logic-mutation teeth
(`cross_asset_kuramoto/invariants`, `indicators/gauss_bonnet`, `kuramoto/second_order`,
`physics/cognitive_core`, `physics/stuart_landau_es`, `ci/check_mutation_kill_ratchet`, plus
the 3 risk/sizing modules `dynamic_position_sizer`, `gaba_inhibition_gate`,
`order_validator`) are **not** the modules named by the 27 canonical claims. Applied
honestly today, `falsification_power` is `UNMEASURED` for every registered claim. This is
the true epistemic state and the actionable gap.

---

## 5. Provenance & tamper-evidence

The report is emitted only as a provenance-bound object and bound into the same
tamper-evident envelope the categorical audit uses
(`geosync.proof.run._content_digest` / `_sha256_file`):

* `epistemic_integrity.procedure` names the exact formula, inputs, and repro command.
* `audit_sha256`, `claims_sha256`, `mutation_baseline_sha256`, `mutation_modules_sha256`
  pin the exact input bytes; `audit_content_digest` chains to the upstream audit's own hash.
* `content_digest` self-hashes the whole report (minus itself). An external party recomputes
  it over the received bytes — trusting the bytes, not the author. Any single flipped byte in
  any input changes a hash.

E is therefore always reported as a triple `{value, procedure, tier}`, satisfying the
no-unprovenanced-numbers discipline. Given the empty join, E currently ships tier
`EXTRAPOLATED` / coverage `n/a` — it declines to certify teeth it has not measured.

---

## 6. What would EARN (not fabricate) calibration

The framework is built; the evidence to feed it is the missing piece. To move a claim off
`UNMEASURED` honestly:

1. **Declare the join.** Add an optional `falsifier.mutated_module` (repo-relative source
   path) to each claim in `CLAIMS.yaml`, matched against the mutation JSON module key. This
   converts the inferred, `0/27` join into a first-class, reviewed link and closes §1.6.
2. **Extend the ratchet ledger** to the claim-critical modules named in the 27 falsifiers'
   `evidence_paths`, running `mutation_probe --only-logic` **bounded, serial, opt-in** —
   probes rewrite source in place and must never run concurrently — and freezing
   `killed/total` into `MUTATION_KILL_BASELINE.json`, exactly as the existing 6+3 modules
   were enrolled.
3. **Re-run the audit in execute mode** so SUPPORTED rows exist, then
   `python -m geosync.proof.weighting`. Coverage rises from 0, and E begins to report earned,
   size-annotated strength for the claims that now have teeth.

Until then, the correct and reported value of this measure is: **the machinery is honest and
connected end-to-end, and it currently measures that nothing is calibrated.**

### 6.1 What would falsify the *value* of this layer
If, after steps 1–2 land, the calibrated E moved in **lockstep** with the raw categorical
`SUPPORTED` count — i.e. calibration never re-weighted any SUPPORTED away from its neighbour
— then this layer would be decoration. The positive control in the teeth suite
(`test_proven_strictly_beats_toothless`) pins the opposite on synthetic evidence; the same
separation must survive on real evidence for the value claim to hold.

---

## 7. Positioning (what E is and is not)

E is an **epistemic-integrity measure of the claims audit** — a statement about how well the
audit's own falsifiers are demonstrated to bite. It is **not** a statement about market
performance, forecasting skill, or deployment readiness. A high E means "the SUPPORTED
verdicts rest on falsifiers with demonstrated logic-killing teeth", nothing more. This
document and the report it describes avoid the language firewall
(`FORBIDDEN_CLAIMS.md`); a `FORBIDDEN_LANGUAGE` verdict contributes `g = −1` and forces
`E = 0`, so the overclaim firewall lives **inside** the score, not merely around it.
## Measured result on the live 27 claims (2026-07-22)

Run `python -m geosync.proof.audit && python -m geosync.proof.weighting`:

```
E=0.5000 tier=EXTRAPOLATED reject_gate=1 calibration_coverage=0.000 (0/22 SUPPORTED calibrated)
N=27 scope=logic:compare+boolop (mutation_probe --only-logic)
```

**The sobering, honest finding — and the whole point of this layer.** The categorical audit reports
**22 SUPPORTED** (a green wall). The weighting reports that **0 of those 22 carry any measured
logic-falsification power**: the recorded mutation manifests cover physics modules
(`core/kuramoto/…`, `core/physics/…`), while the 27 claims' falsifiers live in other test files
(`tests/geosync_hpc/…`) that have never been logic-mutation-tested. So `calibration_coverage=0.000`
and the system-level epistemic integrity is **EXTRAPOLATED, not ANCHORED** — a green categorical
audit is **not** proven integrity. This is not a bug (verified: zero overlap between recorded and
claimed test files → honest UNMEASURED → weight 0, never laundered to 1.0). It is the measurement
doing its job: exposing that "SUPPORTED" without measured teeth is unearned trust.

**Next work (stated, not faked):** run `tools/mutation_probe.py --only-logic` over the claim
falsifiers' modules to earn calibration; the weighting will then credit only the teeth it measures.
Until then the honest number is E=0.5000 / EXTRAPOLATED, and this document says so.
