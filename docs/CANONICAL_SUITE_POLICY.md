<!-- SPDX-License-Identifier: MIT -->
# Canonical Python 3.12 Test-Suite Policy (TST-001)

Status: ACTIVE · Owner: remediation/wave7 · Runner: `scripts/ci/run_canonical_suite.py`

This document defines how the canonical Python 3.12 test suite is run **honestly
and safely**, what is deliberately excluded, and what a valid evidence receipt
looks like. It is the human-readable contract behind
`scripts/ci/run_canonical_suite.py` and the receipts under
`artifacts/tests/full_py312/`.

---

## 1. Safety contract (non-negotiable)

This repository contains **source-rewriting test lanes** — mutation and ratchet
probes that edit source files *in place* while they execute. Running them
unattended, or concurrently with anything else touching the tree, corrupts the
working copy. Both `CLAUDE.md` and the `.gitlab-ci.yml` pipeline header warn
about this explicitly:

> anything with "mutation"/"ratchet" in its name … rewrites source files in
> place and must never run unattended or concurrently with anything else
> touching the tree.

The canonical runner therefore **must never collect or execute** these lanes.
Exclusion is enforced three independent ways (belt-and-braces):

1. **`--ignore`** for every known source-rewriting directory / file, so the
   modules are never imported at collection time.
2. **`-k` de-selection**: `not mutation and not ratchet and not nightly and not gpu`.
3. **`-m` marker de-selection** (only markers that exist in `pytest.ini`).

Additionally, **every** pytest invocation is bounded by BOTH:

* a **per-test timeout** (`--timeout`, from `pytest-timeout`, thread method), and
* an **overall wall-clock timeout** enforced by the runner via `subprocess`.

Nothing can hang, and no source-rewriting lane can run.

### Excluded source-rewriting / unsafe lanes

Directories ignored wholesale:

| Path | Reason |
|------|--------|
| `tests/mutation/` | mutation ledger / falsifier forge — rewrites source |

Individual files ignored (they live beside safe siblings):

| File | Reason |
|------|--------|
| `tests/ci/test_mutation_kill_ratchet.py` | mutation kill ratchet probe |
| `tests/ci/test_ratchets_enforced.py` | ratchet enforcement probe |
| `tests/governance/test_truth_gate_mutation.py` | truth-gate mutation probe |
| `tests/physics/test_cognitive_core_mutation_tribunal.py` | cognitive-core mutation tribunal |
| `tests/tools/test_verifier_mutation_kill.py` | verifier mutation-kill probe |
| `tests/tools/test_coverage_intelligence_ratchet_edges.py` | coverage-intelligence ratchet |

### Excluded slow / infra lanes

By marker: `nightly`, `flaky`, `slow`, `canary`, `live_balance`, `heavy_math`,
`UNSTABLE`. These require nightly pipelines, live venue balances, dedicated
rerun jobs, or compute/time budgets a sandbox does not have. GPU / network
lanes are additionally excluded by the `-k` keyword filter and fail fast under
the per-test timeout when a fixture reaches for absent infrastructure.

---

## 2. Faithful-to-repo execution

The suite is **defined by** `pytest.ini`. The runner does **not** neutralise the
repo `addopts`; it honours them and only *adds* safety, bounding, and evidence
flags on top. In particular it preserves:

* `--import-mode=importlib` — the tree relies on this to disambiguate duplicate
  test basenames (e.g. two `test_schema_contracts.py`). Dropping it produces
  spurious "import file mismatch" collection errors.
* `-W error::DeprecationWarning` — third-party deprecations therefore surface as
  real signal, which in a below-floor sandbox is itself an environment finding.
* `--continue-on-collection-errors` — one bad module never aborts the receipt.

The only override is the fail-fast cap: `--maxfail=10000` replaces the repo
`--maxfail=50` so the receipt records **every** failure, not the first fifty.

Default target: `tests/unit` — the large pure-logic surface, which by
construction contains none of the source-rewriting lanes.

---

## 3. Evidence receipt

Every run writes, under `artifacts/tests/full_py312/`:

| Artifact | Contents |
|----------|----------|
| `junit.xml` | machine-readable per-test results + durations |
| `summary.json` | real counts, verdict, excluded-lane list, env fingerprint, commit/tree binding |
| `run.log` | full stdout/stderr of the bounded run |
| `collect.log` | stdout/stderr of the collection probe |

The **environment fingerprint** records: Python version + implementation +
executable, platform, `git` commit SHA, tree SHA, branch, dirty flag, and key
dependency versions (`numpy`, `scipy`, `pandas`, `torch`, `pytest`, …). The
receipt is **bound to the commit and tree SHA** it was produced from.

---

## 4. Honesty contract & verdicts

This sandbox is known to be **below security floors for several dependencies**
(ENV-001) and may lack GPU / network / market-data fixtures. A signed,
0-failure canonical receipt is therefore a task for the **ENV-005 hermetic
container**, *not* this sandbox. The runner records the **REAL** counts and
never fabricates a clean pass. Verdicts:

| Verdict | Meaning |
|---------|---------|
| `CLEAN_SANDBOX` | 0 failures, 0 errors, 0 collection errors, no missing deps — the sandbox mirror of a clean run (the *signed* 0-failure receipt still requires ENV-005) |
| `ENV_LIMITED` | failures / errors / missing deps attributable to sandbox limits |
| `ENV_LIMITED_TIMEOUT` | overall wall-clock budget exhausted; receipt is partial |
| `NO_TESTS_COLLECTED` | nothing was collected (mis-targeted run) |
| `COLLECTION_CLEAN` / `COLLECTION_ERRORS` | `--collect-only` phase verdicts |

**The canonical, signed 0-failure receipt is produced only by the ENV-005
hermetic container run, on pinned, at-or-above-floor dependencies, with GPU /
network / data fixtures present. This policy and its sandbox receipts are the
bounded, safe precursor to that run — never a substitute for it.**

---

## 5. Usage

```bash
# Collection probe only (measures collection errors, runs no test bodies):
python scripts/ci/run_canonical_suite.py --collect-only --targets tests/unit

# Full bounded run producing the receipt:
python scripts/ci/run_canonical_suite.py \
    --targets tests/unit --per-test-timeout 30 --job-timeout 1500
```

The runner exits `0` even on an `ENV_LIMITED` verdict: its job is to **produce
an honest receipt**, not to gate CI. Gating is the ENV-005 container's role.
