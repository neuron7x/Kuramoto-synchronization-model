# PR #1416 Fail-Closed Repair Protocol

Repository: `neuron7xLab/GeoSync`

PR: `#1416` / branch `agent-dopamine-v2`

Mode: manual expert engineering handoff for Claude Code. No automatic greenwashing. No weakened tests. No hidden quarantine.

Date: 2026-06-29

---

## 0. Operating law

The PR is not ready because it has a green-looking description. It is ready only when the full evidence chain is terminal green:

```text
claim -> source -> invariant -> witness -> artifact -> command -> hash/diff -> verdict
```

For the current repair cycle this reduces to:

```text
law -> witness -> artifact -> readiness -> test -> shard -> CI -> merge
```

Merge remains forbidden until all required checks for the current head are terminal green.

---

## 1. Current known state

Latest observed PR head before this document was created:

```text
c71ff170c722f356c6a122ac9e9b2df468885cab
```

The PR is open, not merged, and mergeable, but mergeability is not readiness.

Known green layers before this document:

```text
Commit Acceptor Gate: success on Python 3.11 and 3.12
Readiness Gate: previously success on the prior replay
Physics Invariants: success
Physics Kernel Gate: success
Physics-2026 Gate: success on prior replay
Repo Integrity Gate: success on prior replay
python-quality in PR Gate: success on prior replay
```

Known red / unresolved layers:

```text
Research Integrity Gate: failed at `pytest — research/systemic_risk` on head 1843b0bf...
PR Gate: python-fast-shard was still in progress / red-prone surface
```

A new observability patch was applied to `Research Integrity Gate` so that a future `research/systemic_risk` failure preserves `/tmp/research_systemic_risk.log` as the `research-systemic-risk-pytest-log` artifact.

---

## 2. Critical bug and gap register

### BUG-001 — Hidden pytest tail in `Research Integrity Gate`

Severity: P0 evidence-blocker.

Observed symptom:

```text
Research Integrity Gate -> pytest — research/systemic_risk -> failure
connector-visible logs show only the beginning of the job, not pytest traceback
```

Why it matters:

The gate was red, but the actionable pytest node id and traceback were not machine-readable through the available connector surface.

Current mitigation:

`research-integrity-gate.yml` now captures:

```text
/tmp/research_systemic_risk.log
```

and uploads it on failure as:

```text
research-systemic-risk-pytest-log
```

Next Claude Code action:

```text
1. Wait for Research Integrity Gate on the current head to become terminal.
2. If failed, download artifact `research-systemic-risk-pytest-log`.
3. Extract exact failing pytest node id, traceback, assertion payload, and root cause.
4. Patch only the causal source/test/artifact defect.
5. Do not skip, xfail, relax, or delete the failing test.
```

Acceptance:

```text
Research Integrity Gate = terminal success
or artifact contains exact failing node id + traceback and a causal patch follows
```

---

### BUG-002 — `PR Gate` fast shards lack durable failure artifacts

Severity: P0 observability-blocker.

Observed symptom:

```text
PR Gate / python-fast-shard failed 4/4 on previous head
failure step = Run fast deterministic pytest gate
connector-visible logs were truncated before failure tail
artifacts = none
```

Why it matters:

The workflow does print a failure summary, but if the connector exposes only the head of logs, the repair loop cannot reliably extract failing node ids.

Required fix if shards fail again:

Modify the existing required `PR Gate` only; do not add a new debug workflow. Preserve fail-closed semantics.

Minimum acceptable artifact payload:

```text
/tmp/shard_run.log
/tmp/shard_nodeids.txt
/tmp/all_nodeids.txt
/tmp/collect_stderr.log
/tmp/quarantine_paths.txt
```

Use pinned artifact action already accepted in the repo:

```text
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
```

Next Claude Code action:

```text
If any python-fast-shard fails and logs do not expose the exact traceback, patch PR Gate to upload the shard evidence files on failure.
```

Acceptance:

```text
A failed fast shard produces exact node ids and traceback artifacts, or the shard is green.
```

---

### BUG-003 — Suspected `Physics Inference Readiness` order/context failure

Severity: P0 if reproduced; otherwise hypothesis.

Reported failing node:

```text
tests/ci/test_physics_inference_readiness.py::test_synthetic_tier_is_ready_and_honest
expected READY_SYNTHETIC_ONLY
actual BLOCKED_MISSING_WITNESS
```

Interpretation:

`BLOCKED_MISSING_WITNESS` means the live readiness computation could not validate the law-witness index. It is not a generic pytest failure.

Strong hypothesis:

```text
standalone readiness surface may be green,
but full fast-shard context may create order pollution, cwd/path drift, merge-ref drift, or stale artifact exposure.
```

Current mitigation already applied:

The test now includes `result` as assertion payload on verdict mismatch. That does not weaken the assertion; it exposes `blocker_path` and `checks`.

Required Claude Code replay:

```bash
python -m pytest \
  tests/ci/test_physics_inference_readiness.py::test_synthetic_tier_is_ready_and_honest \
  -vv -s

python - <<'PY'
import json
from scripts.ci.check_physics_inference_readiness import compute_readiness
print(json.dumps(compute_readiness(), indent=2, sort_keys=True))
PY

python scripts/ci/check_physics_law_witness_index.py
python scripts/ci/check_physics_inference_readiness.py
```

If local standalone passes but shard fails, test PR merge ref and shard order:

```bash
git fetch origin refs/pull/1416/merge:pr-1416-merge
git checkout pr-1416-merge
```

Acceptance:

```text
READY_SYNTHETIC_ONLY is confirmed by live computation, committed artifact, dedicated gate, and pytest shard.
```

---

### BUG-004 — Possible law-witness artifact drift

Severity: P0 if verified.

Files:

```text
scripts/ci/check_physics_law_witness_index.py
scripts/ci/check_physics_inference_readiness.py
artifacts/physics_v2/law_witness_index.json
artifacts/physics_v2/inference_readiness.json
```

Risk:

Committed `inference_readiness.json` may claim `READY_SYNTHETIC_ONLY` while live recomputation sees a stale or invalid `law_witness_index.json`.

Required commands:

```bash
python scripts/ci/check_physics_law_witness_index.py
python scripts/ci/check_physics_inference_readiness.py
python scripts/ci/check_physics_law_witness_index.py --write
git diff -- artifacts/physics_v2/law_witness_index.json
python scripts/ci/check_physics_inference_readiness.py --write
git diff -- artifacts/physics_v2/inference_readiness.json
```

Artifact diff is valid only if:

```text
no new BLOCKED verdict appears
READY_SYNTHETIC_ONLY does not degrade to BLOCKED_*
all blocking laws are COVERED or ledgered
all witness paths exist
all witness paths are git-tracked
ANCHORED invariant test paths exist
```

Do not commit regenerated artifacts blindly.

---

### BUG-005 — Possible missing or invisible witness binding

Severity: P0 if verified.

The AST scanner is expected to discover witness functions under `tests/**/test_*.py` using a simple literal decorator pattern:

```python
@law("exact.law_id")
def test_some_law_witness() -> None:
    ...
```

Common invisible-witness causes:

```text
file not under tests/
file does not start with test_
decorator is aliased
decorator is on a class, not FunctionDef
law id passed by variable, not string literal
generated dynamic test
syntax/import error blocks collection
```

Claude Code action if `blocking law without witness` appears:

```text
1. Extract law_id.
2. Find it in physics_contracts/catalog.yaml and invariant configs.
3. Add a real witness test with positive case, negative falsifier, explicit tolerance, deterministic input.
4. Regenerate and audit law_witness_index + inference_readiness artifacts.
```

---

### BUG-006 — Possible ANCHORED invariant dangling test path

Severity: P0 if verified.

File:

```text
.claude/physics/INVARIANTS.yaml
```

Invalid state:

```text
ANCHORED provenance with empty, missing, placeholder, or untracked test path.
```

Required check:

```bash
python - <<'PY'
from pathlib import Path
import re
text = Path('.claude/physics/INVARIANTS.yaml').read_text()
paths = sorted(set(re.findall(r'tests/[A-Za-z0-9_./-]+\.py', text)))
missing = [p for p in paths if not Path(p).exists()]
if missing:
    print('FATAL: missing invariant test paths')
    print('\n'.join(missing))
    raise SystemExit(1)
print('OK: invariant test paths exist')
PY
```

Acceptance:

```text
No ANCHORED invariant points to a missing or untracked test path.
```

---

### BUG-007 — Fast-shard grep can misclassify negative-test stdout as failure summary

Severity: P1 log-hygiene gap.

Current risk:

The workflow uses grep over the whole pytest log:

```text
grep -aE '^(FAILED|ERROR)' /tmp/shard_run.log
```

Some negative-control tests intentionally print failure-like text. The real source of truth is pytest short summary and exit code, not arbitrary stdout grep.

Preferred repair:

```bash
awk '/short test summary info/ {flag=1} flag {print}' /tmp/shard_run.log | tail -200
```

or a JSON report if dependency policy allows.

Acceptance:

```text
CI exposes real pytest failed node ids and traceback, not arbitrary FAILED/ERROR strings from test stdout.
```

---

### BUG-008 — Scope creep: dopamine PR now carries CI/readiness observability changes

Severity: P1 process risk.

Original PR goal:

```text
bounded evidence-gated dopamine component hardening v2
```

Expanded repair scope:

```text
physics readiness assertion observability
research integrity pytest artifact capture
possibly PR Gate shard artifact capture
```

This expansion is acceptable only while it is strictly in service of making hidden required-check failures observable and causal. It must not become a broad unrelated refactor.

Acceptance:

```text
All added non-dopamine changes are acceptor-bound and directly tied to hidden CI failure diagnosis.
```

---

### BUG-009 — Commit acceptor binding risk for any new diagnostic file

Severity: P0 process blocker if missed.

Rule:

Any new workflow/doc/test/artifact added to this PR must be covered by a commit acceptor diff scope. Unbound diagnostic files create policy-red noise.

Known prior failure:

A temporary debug workflow was added without acceptor binding and created a self-inflicted red. Do not repeat that pattern.

Acceptance:

```text
Commit Acceptor Gate green after every patch.
```

---

### BUG-010 — Do not treat research/systemic_risk failure as dopamine semantics

Severity: P1 diagnostic error.

The current dopamine component hardening may have triggered broad CI surfaces by touching `src/`, `scripts/`, and `tests/`, but a failure in `tests/research/systemic_risk/` must be diagnosed as research-integrity failure unless logs prove otherwise.

Acceptance:

```text
Patch the failing node's causal module/test/artifact, not dopamine docs by association.
```

---

## 3. Claude Code execution protocol

Run this from a clean runner-equivalent environment.

### 3.1 Checkout exact PR merge ref

```bash
git fetch origin main
git fetch origin refs/pull/1416/merge:pr-1416-merge
git checkout pr-1416-merge
git rev-parse HEAD
git status --short
```

### 3.2 Validate current failure surfaces

```bash
python -VV
python -m pip --version || true
python -m pytest --version
```

### 3.3 Research Integrity failure extraction

If `Research Integrity Gate` fails:

```text
1. Download artifact `research-systemic-risk-pytest-log`.
2. Extract exact pytest node id and traceback.
3. Reproduce locally:
```

```bash
python -m pytest tests/research/systemic_risk/ -q --maxfail=1 -rA --tb=short
```

Patch only the causal source/test/artifact.

### 3.4 Physics readiness extraction

If `test_synthetic_tier_is_ready_and_honest` fails:

```bash
python -m pytest tests/ci/test_physics_inference_readiness.py -vv -s
python scripts/ci/check_physics_law_witness_index.py
python scripts/ci/check_physics_inference_readiness.py
```

Use assertion payload to extract:

```text
verdict
blocker_path
checks.witness_index.ok
checks.witness_index.blocker
```

### 3.5 PR Gate fast shard extraction

If any `python-fast-shard` fails:

```text
1. Read raw logs for exact node ids if visible.
2. If not visible, patch existing required PR Gate to upload shard evidence artifacts on failure.
3. Do not add a separate debug workflow.
```

### 3.6 No-weakening rules

Do not use:

```text
pytest.skip
xfail
assert True
expected verdict downgrade
severity downgrade without ledger_reason
quarantine without issue=#<n>
workflow continue-on-error
new debug workflow outside acceptor binding
```

---

## 4. Final acceptance matrix

Before merge-ready verdict:

```text
Commit Acceptor Gate: PASS
Research Integrity Gate: PASS
PR Gate repo-policy: PASS
PR Gate python-quality: PASS
PR Gate python-fast-shard 1/2/3/4: PASS
PR Gate python-fast-tests aggregator: PASS
PR Gate python-heavy-tests: PASS or legitimate content-aware skip
Readiness Gate: PASS
Physics Invariants: PASS
Physics Kernel Gate: PASS
Physics-2026 Gate: PASS
Repo Integrity Gate: PASS
Docs Consistency Gate: PASS
Claim Boundary Gate: PASS
Security/secrets-supply-chain: PASS
```

Artifact validity:

```text
law_witness_index.json stale: no
inference_readiness.json stale: no
all witness paths exist: yes
all witness paths tracked: yes
all blocking laws covered or ledgered: yes
ANCHORED invariant paths exist: yes
```

No weakening:

```text
no deleted tests
no hidden skip
no xfail without issue and expiry
no relaxed assertion
no fake quarantine
no merge while required checks red or pending
```

---

## 5. Final report template

```text
VERDICT: PASS / FAIL

Repository: neuron7xLab/GeoSync
PR: #1416
Tested head: <sha>
Merge ref: <sha>

Root cause:
<one exact sentence>

Files changed:
- <path>

Evidence:
- Commit Acceptor Gate: PASS/FAIL
- Research Integrity Gate: PASS/FAIL
- PR Gate python-fast-shard 1/2/3/4: PASS/FAIL
- check_physics_law_witness_index.py: PASS/FAIL
- check_physics_inference_readiness.py: PASS/FAIL
- test_physics_inference_readiness.py: PASS/FAIL

Artifact diff validity:
- no new BLOCKED verdict: yes/no
- all witness paths exist: yes/no
- all witness paths tracked: yes/no
- all blocking laws covered or ledgered: yes/no
- ANCHORED invariant paths exist: yes/no

No weakening:
- no test deletion
- no skip/xfail
- no relaxed assertion
- no severity downgrade without ledger_reason
- no fake quarantine
- no red merge

Remaining risk:
<none or exact risk>
```
