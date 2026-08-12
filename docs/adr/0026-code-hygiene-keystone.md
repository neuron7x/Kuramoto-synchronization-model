# ADR 0026 — Code-hygiene keystone: anti-laundering, coverage, fail-closed parse

- Status: Accepted
- Date: 2026-06-25
- Relates to: ADR 0025 (code-hygiene ratchet)

## Context

ADR 0025 shipped a monotone-down code-hygiene ratchet. An adversarial
re-verification of that merged instrument — running it against itself —
proved three degradation vectors by which it would, in a dynamic
many-agent repo, report "held" while the system decays:

- **V1 — `--write` laundering (keystone).** `_write_baseline` regenerates
  the baseline from the current tree with no comparison to the prior one.
  Demonstrated: add `except Exception: pass`, run the gate's own `--write`,
  commit; the broad-except total grew 326→327 and the next `verify` printed
  "No new debt." Under completion pressure the cheapest response to any red
  gate is to re-baseline, so the ratchet converges to a rubber stamp.
- **V5 — coverage shrinks silently.** `runtime_roots` was a static 7-package
  list; the repo has 50+ top-level Python packages and spawns more. A new
  top-level package (or code relocated into an unlisted one) was completely
  ungated and the gate still printed "held."
- **V4 — silent zero on unparseable.** A file that failed `ast.parse`
  (e.g. newer syntax under the 3.12 runner) contributed zero debt and
  vanished from the ledger instead of surfacing.

## Decision

- **Anti-laundering meta-gate** — `scripts/ci/check_debt_baseline_monotonic.py`
  diffs the committed baseline *totals* (per dimension) against `origin/main`
  and fails if any total increased. `--write` that pays debt down passes;
  `--write` that admits debt cannot land. Fail-closed if the base ref is
  unreadable. This makes the aggregate strictly non-increasing regardless of
  how the per-file ledger is regenerated.
- **Complete classification** — every top-level package containing `.py` is
  now explicitly in `runtime_roots` (gated) or `excluded_roots` (deliberately
  ungated) in `CODE_QUALITY_MANIFEST.json`; `check_code_hygiene.py` fails on
  any unclassified top-level package. The previously-implicit ~39 ungated
  packages are now an explicit, reviewable surface. Promotion of an excluded
  runtime package into the gated set is a deliberate, reviewed expansion.
- **Fail-closed parse** — a new `unparseable` debt dimension records any
  runtime file that will not AST-parse, so it is visible debt rather than a
  silent zero.

Enforcement: the three checks run in `code-hygiene-gate.yml` (the meta-gate
needs `fetch-depth: 0` to read `origin/main`) and in `make code-quality`.

## Consequences

- New debt must be refactored away, not frozen. The only way the baseline
  moves is down.
- `excluded_roots` is now a long, explicit list. That is intentional: it is
  the honest current state (the gate always scanned only 7 roots), now
  auditable instead of implicit.

## Residual vectors (knowingly NOT closed here)

Tracked openly rather than masked (enforcement honesty):

- **V2 — migration friction.** Symbol keys are `path::qualname`; a pure file
  move (the ADR-0024 `geosync/` migration) trips both ratchet arms. To be
  addressed when D-01 starts, via move-aware key remapping — not before, to
  avoid pre-emptive complexity.
- **V3 — rotation in place.** Count-ledgers track per-file totals, not
  identity; removing N and adding N broad-excepts in one file nets zero. The
  meta-gate bounds the aggregate but not same-count identity swaps. Closing
  this needs identity-keyed count dims (a baseline reformat).
- **V6 — laundering into excluded roots.** Moving a god-module into an
  excluded package drops its debt as a "fix." The explicit `excluded_roots`
  surface makes such moves reviewable but does not yet block them.
- **V7 — aliased ambient calls.** `import datetime as DT; DT.now()` evades
  the suffix matcher; recall degrades as aliasing spreads.
- **V8 — Goodhart.** A wide `except (A, B, C, ...)` is as fail-open as
  `except Exception` but is not counted. The metric is a proxy.
- **V11 — path-filter bypass.** Build-time or template-generated `.py` and
  `.pyi` stubs do not trigger the workflow.

These are candidates for subsequent hardening PRs; none is silently assumed
closed.
