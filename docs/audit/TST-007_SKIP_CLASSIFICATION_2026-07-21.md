# TST-007 — skip/xfail marker classification (2026-07-21)

Deliverable for remediation item TST-007 ("classify the skip/xfail markers"). The ledger's
snapshot cited 211 markers / 113 files; the live tree now has **266 markers in 144 files**
(the count grew with the suite — the point of this item is a *typed inventory*, not a frozen
number). Reproduce: `python scripts/audit/classify_test_skips.py` (machine-readable:
`--json` → `artifacts/audit/tst007_skip_inventory.json`).

| category | count | actionable? |
|---|---|---|
| dependency-induced | 156 | no — optional dep (numpy/torch/ccxt/z3/vcrpy) absent; TST-008's job |
| data-artifact-gated | 31 | no — a research blob (parquet/panel/Askar) not staged locally |
| conditional-inapplicable | 26 | no — scenario does not apply (schema lacks field, nothing to compare) |
| platform | 16 | no — OS/arch conditional |
| env-or-slow-gated | 2 | no — network/live/perf gating |
| by-design-xfail | 1 | no — a known, documented negative |
| **todo-wip** | **1** | **yes** — explicit TODO/WIP/flaky |
| **unclassified** | **33** | **yes** — reason present but not auto-matched; needs a human tag |

**Finding:** only **34 of 266** markers (todo-wip + unclassified) are potential silent holes;
the other **232** are legitimate conditional gating (dependency / data / platform / scenario /
by-design). The `pytestmark = pytest.mark.<custom>` labels (e.g. `L3`) are correctly NOT counted
— the inventory matches `pytestmark` only when it references skip/xfail.

**Follow-ups (tracked, not faked):** the 33 unclassified reduce to conditional-data-shape and
"run-only-when-dep-absent" complements on inspection but are left as an explicit human-tag queue
rather than force-fitted; the dependency-induced bucket is TST-008's remediation. This inventory
is the TST-007 evidence artifact.
