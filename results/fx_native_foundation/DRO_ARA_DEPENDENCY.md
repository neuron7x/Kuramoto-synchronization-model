# FX-native foundation · DRO-ARA dependency (MODE_A)

**Verdict: `INDEPENDENT_OF_DRO_ARA` for MODE_A deliverables.**
(Conditional re-assessment required before any MODE_B diagnostic that
uses a regime-derived feature — see §RDA-next below.)

---

## Scope of this verdict

MODE_A deliverables covered by this dependency statement:

1. `DATA_CONTRACT.md` — pure file paths + timestamps + raw cleaning
   rule. No DRO-ARA reference.
2. `KURAMOTO_RELATION.md` — compares two research *lines*, not their
   regime features. Cites cross-asset Kuramoto's published `R(t)` logic,
   not DRO-ARA.
3. `INPUT_GAPS.md` — catalogues available FX / macro / rates data.
   DRO-ARA is not an input; it is a consumer of inputs.
4. `SCHEDULING_DECISION.md` — pure prioritisation argument.
5. `HUMAN_GATE_MEMO.md` — a three-way choice over phase outcome.

None of these five files read, invoke, or derive anything from the
DRO-ARA engine. Their correctness is independent of whether the
DRO-ARA patch (γ, ADF R² ≥ 0.90, INV-DRO1..5) is applied or not.

## Why the phrasing is `INDEPENDENT_OF_DRO_ARA`, not `MIXED_DEPENDENCY_UNSAFE`

Per §RDA2, the `MIXED_DEPENDENCY_UNSAFE` label applies only when
"post-patch and pre-patch states would materially change the
analysis". For the five MODE_A outputs above the set of DRO-ARA values
that enter the analysis is the empty set. Any two DRO-ARA states
therefore produce identical MODE_A outputs, so the mixed-dependency
risk cannot materialise.

## Forward-looking clause — MODE_B re-assessment required

If and when this protocol is promoted to MODE_B_POST_DEMO, the substrate
diagnostics (`§9.DIA3 regime_map`, `§9.DIA1 common-factor audit`) may
legitimately want to build an FX-regime variable. If that variable uses:

- `core/dro_ara/engine.py::derive_gamma` (γ = 2H + 1),
- `core/dro_ara/engine.py::regime_classifier` (CRITICAL/TRANS/…),
- `core/dro_ara/engine.py::rs` mapping,

then MODE_B must re-open this file and pin the exact DRO-ARA engine
commit before any diagnostic runs. The invariants in play are
`INV-DRO1..INV-DRO5` (see `GeoSync-main/CLAUDE.md`). Fail-closed
vocabulary to use in that case:

- `DEPENDS_ON_POST_PATCH_DRO_ARA` + engine SHA → proceed.
- `DEPENDS_ON_PRE_PATCH_DRO_ARA` + engine SHA → proceed only if the
  MODE_B diagnostics are explicitly framed as "pre-patch comparison".
- `MIXED_DEPENDENCY_UNSAFE` → STOP.

The MODE_A set does not exercise any of these paths.

## Silent-mixing guard (RDA3)

No MODE_A output has copied, imported, or re-derived a DRO-ARA value
and carried it into an analytical claim. This statement is falsifiable:
a grep of the MODE_A deliverables for the tokens
`dro_ara | gamma | INV-DRO | derive_gamma | regime_classifier`
should return zero analytical uses (citations in the
forward-looking clause above do not count).

## Explicit label

**`INDEPENDENT_OF_DRO_ARA`** — valid for the MODE_A deliverable set at
commit `1099458` and any subsequent commits that do not touch MODE_B
substrate diagnostics.
