# CodeQL Security-Board Triage — PR #895

Date: 2026-06-09 · Branch: `security/codeql-board-triage`

## Scope

Full verify · validate · falsify pass over the GitHub code-scanning board for
`neuron7xLab/GeoSync`. Every finding was checked against real code before any
action: real defects fixed, proven false positives dismissed with written
justification.

## Board at entry

| Stream | Open |
|--------|------|
| Dependabot | 0 |
| Secret scanning | 0 |
| Code scanning (CodeQL) | 753 |

CodeQL runs the **`security-and-quality`** suite (`.github/workflows/codeql.yml`),
so maintainability/quality queries land on the *security* board. Only **3**
findings carried a real `security_severity_level` (2 high + 1 medium).

## Real-severity security (3 → resolved)

| # | Rule | Sev | Disposition |
|---|------|-----|-------------|
| 831 | py/overly-permissive-file | high | **Fixed** — checkpoint `.tmp` `0o644`→`0o600`; `os.replace` preserves mode; regression test added. |
| 700 | py/http-response-splitting | medium | **Dismissed (FP)** — `Content-Type` from `mimetypes.guess_type` (fixed table, no CRLF) + suffix whitelist + webroot canonicalisation. |
| 1 | py/incomplete-url-substring-sanitization | high | **Dismissed (FP)** — URL is a module constant; test uses `urlparse` exact hostname match; no substring check exists. |

## Real bugs found inside the "quality" noise (→ fixed)

- **4× `StructuredLogger` positional-arg crashes** (`py/call/wrong-arguments`
  #288–#291). `StructuredLogger.<level>(msg, **kwargs)` takes no positional
  args and does no `%`-formatting; four error/fallback branches called it
  printf-style and would raise `TypeError` the instant the branch ran —
  masking the original error. Reproduced empirically, converted to structured
  kwargs. The entropy test's `DummyLogger` had encoded the broken signature and
  was corrected.
- **1× phantom export** (`py/undefined-export`, `core/orchestrator/__init__.py`).
  `__all__` listed `"ModePhase"` (typo for the imported `ModulePhase`);
  `import *` would `AttributeError`. Corrected.

## False positives dismissed in bulk (verified)

- **117× `py/undefined-export`** — modules export lazily via PEP 562
  `__getattr__`; every `__all__` entry resolves at runtime (`UNRESOLVABLE=0`
  across `core.neuro` 63, `core.neuro.advanced` 35, `application` 18,
  `scripts` 1). CodeQL does not model PEP 562. Dismissed with justification.
- `py/comparison-of-identical-expressions` in physics code — intentional
  `x == x` NaN checks (numba / INV-HPC2). FP.
- `py/call-to-non-callable` — `Callable`-typed params and conditional class
  definitions. FP.

## Remaining backlog (not security)

Unused imports/variables, ineffectual statements, import-style — genuine
maintainability debt, largely in ruff-excluded `tests/`. Owned by the
ruff/mypy lane, not the security board. Recommend either keeping
`security-and-quality` and clearing the debt via extended ruff coverage, or
moving the security board to a security-only query suite so quality findings
route to the linter.

## Verification

`ruff check` · `black --check` · `mypy --strict` clean on every changed
module; physics-code-audit clean; targeted pytest green including the new
`test_g1_checkpoint_is_owner_only` regression guard.
