# Diff-Bound Commit Acceptor Layer — Closure Report

## 1. Invariant

Every code-modifying commit landing on `main` MUST be governed by at least
one diff-bound acceptor that declares, in a single YAML document, the full
six-step contract:

```
promise  →  diff_scope  →  signal  →  falsifier  →  rollback  →  evidence
                                                              ↘  memory
```

Unbound code commits are rejected fail-closed by the
`Commit Acceptor Gate` CI workflow on every pull request and every
merge-queue entry.

## 2. Files Introduced

| Layer        | Path                                                                  |
|--------------|-----------------------------------------------------------------------|
| Policy       | `.claude/commit_acceptor_policy.yaml`                                 |
| Template     | `.claude/commit_acceptor_template.yaml`                               |
| Example      | `.claude/commit_acceptors/canonical-action-result-comparator.yaml`    |
| Self-binding | `.claude/commit_acceptors/commit-acceptor-layer.yaml`                 |
| Validator    | `tools/commit_acceptor/validate_commit_acceptor.py`                   |
| Package init | `tools/commit_acceptor/__init__.py`                                   |
| Tests        | `tests/unit/commit_acceptor/test_validate_commit_acceptor.py`         |
| Tests init   | `tests/unit/commit_acceptor/__init__.py`                              |
| CI workflow  | `.github/workflows/commit-acceptor-gate.yml`                          |
| Report       | `docs/reports/diff_bound_commit_acceptor_layer.md`                    |

## 3. Schema Highlights

* Required top-level fields: 15 (id, status, claim_type, promise, diff_scope,
  required_python_symbols, expected_signal, measurement_command,
  signal_artifact, falsifier{command,description}, rollback_command,
  rollback_verification_command, memory_update_type, ledger_path,
  report_path).
* `status ∈ {DRAFT, ACTIVE, VERIFIED, REJECTED}`.
* `memory_update_type ∈ {append, replace, none}`.
* Forbidden schema fields, rejected anywhere in the YAML tree:
  `forbidden_symbols`, `max_files_changed`, `generated_at`.
* `diff_scope.changed_files` is a non-empty list of `{path, sha256?}`.
* `diff_scope.forbidden_paths` is the per-acceptor path-prefix denylist.

## 4. Diff Binding

* Code-file extensions: `.py .yaml .yml .toml .json .sh`.
* Markdown under `governance_markdown_paths`
  (`.claude/`, `docs/governance/`, `docs/architecture/`) is governance,
  not code; markdown anywhere else is code.
* `--require-acceptor-for-code-change` makes every changed code file MUST
  appear in at least one acceptor's `diff_scope.changed_files[].path`.
* A file claimed by an acceptor whose own `forbidden_paths` covers it
  fails fail-closed.
* `max_changed_files_by_claim_type` caps the number of bound files per
  claim type per acceptor (DRAFT and REJECTED also subject to the cap).

## 5. AST Import Boundary

* Forbidden import patterns: `trading`, `execution`, `forecast`, `policy`.
* AST walks `ast.Import.names[*].name` and `ast.ImportFrom.module`.
* Match: `name == pattern OR name.startswith(pattern + ".")`.
* Relative imports (`from . import x`) are skipped.
* Comments and string literals are NOT inspected — only real imports.
* AST parse error in a changed `.py` file is a validation error (exit 1).

## 6. Evidence Hashing Semantics

* `signal_artifact` is hashed (sha256 hex) on every run.
* Each `evidence[].path` is hashed; declared `sha256` is verified.
* Status DRAFT / ACTIVE: missing artefact → warning (validator returns 0).
* Status VERIFIED: missing OR mismatched → error (validator returns 1).
* No `generated_at` field is emitted in the JSON summary.

## 7. CLAIMS vs COMMIT_ACCEPTORS Boundary

`.claude/claims/CLAIMS.yaml` (validated by `.claude/claims/validate_claims.py`)
is a long-lived, multi-commit contract registry tracking persistent
project-level claims. The commit acceptor layer is orthogonal: per-commit,
diff-bound, fail-closed at the boundary between a pull request and `main`.
Neither layer modifies, duplicates, or shadows the other.

## 8. CI Wiring

`.github/workflows/commit-acceptor-gate.yml` runs on `pull_request` and
`merge_group`, on Python 3.11 and 3.12. Steps in order:

1. Static schema validation (`validate_commit_acceptor.py`).
2. Diff binding with `--require-acceptor-for-code-change` against
   `origin/main`.
3. `pytest tests/unit/commit_acceptor -v`.
4. `ruff check`, `ruff format --check`, `black --check`, `mypy --strict`
   on the new tree.

No step has `continue-on-error`. Job and workflow names match the
existing kebab-case `<topic>-gate.yml` convention and do not collide.

## 9. Failure Modes Now Blocked

* Silent code change without an explicit promise.
* Acceptor with no falsifier or trivially-passing falsifier.
* Acceptor referencing a forbidden import pattern.
* Acceptor claiming files under its own `forbidden_paths`.
* Sprawling change exceeding `max_changed_files_by_claim_type`.
* Schema fields silently re-introduced from prior conventions
  (`forbidden_symbols`, `max_files_changed`, `generated_at`).
* VERIFIED acceptors whose evidence file disappeared post-merge.
* Acceptor YAML mutation by the validator itself.

## 10. Probe Matrix (Falsifier Battery)

| # | Mutation                                                                          | Expected                          | Observed       |
|---|-----------------------------------------------------------------------------------|-----------------------------------|----------------|
| 1 | Remove `promise` from self-acceptor                                               | exit 1, "missing required field"  | matched        |
| 2 | Set `status: MAYBE` on self-acceptor                                              | exit 1, status not in valid set    | matched        |
| 3 | Set `claim_type: vibes`                                                           | exit 1, claim_type not in policy   | matched        |
| 4 | Inject `forbidden_symbols: [x]` at top level                                      | exit 1, forbidden_symbols          | matched        |
| 5 | Inject `max_files_changed: 99` under `diff_scope`                                 | exit 1, max_files_changed          | matched        |
| 6 | Inject `generated_at` inside `evidence[]`                                         | exit 1, generated_at               | matched        |
| 7 | Remove all entries from `diff_scope.changed_files`                                | exit 1, non-empty list             | matched        |
| 8 | Drop self-acceptor; keep code change                                              | exit 1, code change without acceptor | matched      |
| 9 | Add `import trading.engine` to validator                                          | exit 1, forbidden import           | matched        |
| 10| Claim `trading/x.py` in self-acceptor                                             | exit 1, forbidden_path             | matched        |
| 11| Push `claim_type: performance` with 11 changed_files                              | exit 1, exceeds cap                | matched        |
| 12| Set `memory_update_type: forever`                                                 | exit 1, memory_update_type         | matched        |
| 13| Strip `falsifier.description`                                                     | exit 1, falsifier missing          | matched        |
| 14| Replace policy with malformed YAML                                                | exit 2, malformed YAML             | matched        |
| 15| Run validator twice; assert acceptor sha256 unchanged                             | sha256 unchanged                   | matched        |

After all probes: `git diff --exit-code` clean, only intended new files
present in `git status --porcelain`.

## 11. Local Gate Results (pre-commit)

| Gate                                                    | Result |
|---------------------------------------------------------|--------|
| `validate_commit_acceptor.py` (static)                  | PASS   |
| `validate_commit_acceptor.py` (diff binding, require)   | PASS   |
| `pytest tests/unit/commit_acceptor -v` (44 passed)      | PASS   |
| `ruff check`                                            | PASS   |
| `ruff format --check`                                   | PASS   |
| `black --check`                                         | PASS   |
| `mypy --strict`                                         | PASS   |

## 12. Verdict

CLOSED. The diff-bound commit acceptor layer enforces, on every pull
request and merge-queue entry, that no code change reaches `main`
without an explicit promise, a falsifiable probe, and a deterministic
rollback — so the repository's commit history is itself a
contract-bound execution trace.
