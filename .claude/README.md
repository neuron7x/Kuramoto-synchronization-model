# .claude/ — Physics Kernel for Claude Code

## What This Is

A local knowledge base that gives Claude Code domain-specific physics
understanding. Without this, Claude Code writes tests that check numbers.
With this, it writes tests that check physics.

## How It Works

1. **CLAUDE.md** (project root) — auto-loaded at session start. Rule Zero.
2. **physics/** — Theory files, invariants, taxonomy, examples, validator.
3. **PROMPTS.md** — Copy-paste templates for Claude Code tasks.
4. **hooks/** — Pre-commit hook for CI gate.

## File Inventory

```
CLAUDE.md                               (project root, auto-loaded)
.claude/
├── PROMPTS.md                          Task delegation templates
├── README.md                           This file
├── hooks/
│   └── pre-commit-physics              Git pre-commit hook
└── physics/
    ├── INVARIANTS.yaml                 57 invariants, 15 modules
    ├── KURAMOTO_THEORY.md              K_c, R, finite-size, Lyapunov
    ├── SEROTONIN_THEORY.md             5-HT ODE, sigmoid, desensitization
    ├── DOPAMINE_THEORY.md              TD-error: δ = r + γV' - V
    ├── GABA_THEORY.md                  Inhibition gate, monotone sigmoid
    ├── TEST_TAXONOMY.md                Test type hierarchy + decision tree
    ├── EXAMPLES.md                     5 before/after test transformations
    └── validate_tests.py               7-level AST validator + code audit
```

## Validator Levels

### Test mode (default)
| Level | What it checks | Method |
|-------|---------------|--------|
| L1 | INV-* reference in docstring | Regex on docstring |
| L2 | INV-* ID exists in INVARIANTS.yaml | Cross-reference |
| L3 | Test structure matches invariant type AND test_type | AST + dual dispatch |
| L4 | Assert error messages: INV-ID, expected, observed, params | Regex on msg |
| L5 | No magic number thresholds | Heuristic + context |

### Code audit mode (--audit-code)
| Level | What it checks | Method |
|-------|---------------|--------|
| C1 | Silent clamp/clip without logging | Regex + context scan |
| C2 | Numeric bounds without INV-* comment | Regex on clip args |

## Quick Start

```bash
tar xzf geosync_physics_kernel.tar.gz
cp .claude/hooks/pre-commit-physics .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
python .claude/physics/validate_tests.py --self-check
python .claude/physics/validate_tests.py tests/unit/physics/
python .claude/physics/validate_tests.py core/neuro/ --audit-code
```
