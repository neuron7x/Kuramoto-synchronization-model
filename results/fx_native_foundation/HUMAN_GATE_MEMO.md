# FX-native foundation · human gate memo (§6 + addendum A1/A6)

**Addressee:** Yaroslav.
**Mode:** `MODE_A_PRE_DEMO`. `ABORT_LINE` is **not** a MODE_A option
(addendum A6); it requires MODE_B diagnostics first. `CONTINUE_TO_
MECHANISM_SELECTION` is not a MODE_A option either (it *is* MODE_B).

## The two admissible options (binding)

### Option 1 — `DEFER_UNTIL_POST_DEMO` *(recommended)*

Shelve FX-native foundation work until demo-critical work closes.
Work continues on cross-asset Kuramoto (verified on disk at
`~/spikes/cross_asset_sync_regime/` — 14 scripts, `PUBLIC_REPORT.md`,
12 result JSON/CSV, `paper_state/` live day-12). When you re-open the
line post-demo, the MODE_A output set here is the starting state — no
re-discovery needed.

Consequence: the FX-native line stays *open but paused*. No registry
mutation. No impact on `combo_v1_fx_wave1` closure.

### Option 2 — `ESCALATE_TO_OWNER`

Route the priority decision outside Claude Code entirely (to you as
portfolio owner) because one of the §14 stop conditions applies or
because you want to resolve the DXY-residual corridor question on a
different calendar.

Consequence: MODE_A output set is final; next action is yours, not the
automation's.

## Claude Code's recommendation: **Option 1**

Rationale (one line each, full detail in `KURAMOTO_RELATION.md`,
`SCHEDULING_DECISION.md`, `INPUT_GAPS.md`):

- Demo-critical work is open (memory: `project_demo_deadline.md`).
- Cross-asset Kuramoto ships Sharpe +1.262 OOS on disk; FX-native has
  no prior evidence.
- 4 of 6 distinct FX-native mechanism classes are blocked by missing
  inputs (rates / options / L2 / calendar).
- The only distinct corridor with in-repo inputs (DXY-residual
  cross-section) has no prior and no preregistration. Its earliest
  honest verdict is weeks of MODE_B work.
- Every MODE_A → MODE_B hour today displaces demo polish + PR #203.

## Guardrails preserved either way

- `combo_v1_fx_wave1` stays `REJECTED`.
- `config/research_line_registry.yaml` unchanged.
- `scripts/registry_validator.py` still blocks `(combo_v1, 8fx_daily_
  close_2100utc)` at exit code 2.
- `tests/test_research_line_registry.py` 12/12 green.

Per §6: without your explicit authorisation, MODE_A ends here.
