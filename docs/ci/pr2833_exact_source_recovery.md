# PR #2833: exact source and governance example recovery

## Scope and provenance

This is a bounded code-correctness repair against PR head
`77f4771ddb515f41de5e580a219cf5f2eec7f851`. It restores four files from
[the identified upstream snapshot](https://github.com/neuron7xLab/GeoSync/tree/174aef0c46dc25a6b59bc8fb1457d20e13a38c11),
commit `174aef0c46dc25a6b59bc8fb1457d20e13a38c11`. The two Python sources
were already different from their frozen pins before this PR. The two JSON
examples were absent from this fork but available in the upstream repository.
Recovery used the original bytes, not regenerated artifacts or new hash pins.

| Restored file | SHA256 |
| --- | --- |
| `scripts/run_cross_asset_kuramoto_shadow.py` | `6cdf0027a71aef08be09fca236abf385eef9d174417c0347762acca345240b7c` |
| `research/systemic_risk/d002g_null_mechanisms.py` | `c7e275191454e1e961d5a079a21b6e1dbfcbc1661d48ddf14d0d0c39a426f257` |
| `data/cme_trajectory_trace_example.json` | `d9f0afcc0567b81a60de585835000f5f1e287306140eb5b1bca4ded45c50168f` |
| `data/physics_boundary_report.json` | `1f9509861714e8e90a8253761bae2c1ac1fbc9ef0ceeaebdc1b3ab37cffd9dfa` |

The source changes restore seven original `noqa` comments. Both parsed Python
ASTs are identical to their pre-repair versions. The expected source hashes in
the existing frozen manifests remain unchanged. The recovered JSON Git blob
IDs are `d321f08ab2fa34e0caa431cf29ac12e716485b83` and
`4fc8aa419d916e2381eb14fbef898061073e4b9c`, respectively.

Two exact `.gitignore` exceptions admit these governance examples while
ordinary `data/*` remains ignored. Neither example supplies licensed market
inputs. The trajectory retains its historical `ACCEPT` candidate decision,
`S5_PROXY` status, and `UNKNOWN` verifiers. The boundary report retains `FAIL`,
`UNKNOWN`/`MISSING` verifiers, and the historical proxy quality score **54/90**
documented in [PHYSICS_BOUNDARY_AUDIT.md](../PHYSICS_BOUNDARY_AUDIT.md). These
values are not newly measured research results. The unchanged schemas and
validators remain the acceptance authority.

## Bounded validation

| Check | Observed result |
| --- | --- |
| Frozen Kuramoto contract, gate runner, D002H Gate E | 44 passed |
| CME trajectory and physics boundary schema suites | 21 passed |
| Existing trajectory validator CLI | Exit 0, `OK trajectory trace` |
| Ruff on both changed test files, with `--no-force-exclude` | Passed |
| Four restored SHA256 values and source AST identity | Matched |

The 21 schema tests include negative controls for missing evidence, out-of-range
and Boolean scores, inconsistent trajectory totals, and extra fields. They
also preserve the examples' proxy and failed-verdict boundaries. The frozen
contract suite retains its existing mutation test that rejects a hash mismatch.

The schema and CLI output is persisted in
`tmp/pr2833_cme_fixture_verification.log`. A combined local replay also completed
with **197 passed in 43.53 seconds**, including these 65 tests and 132 tests for
other PR repairs. Its raw log and JUnit receipt are
`tmp/pr2833_targeted_replay.log` and `tmp/pr2833_targeted_replay.xml`. These bounded
results do not establish full CI or release readiness. The exact replay,
falsifier, four evidence hashes, and nine-file scope
are bound by the [correctness acceptor](../../.claude/commit_acceptors/pr2833-exact-source-recovery-20261027.yaml).
Its scope is within the 12-file correctness limit, including this report and the
acceptor itself.

## Remaining ancestry blocker

Eight historical anchors are ancestors of the pinned upstream snapshot. Their
commit objects are absent from the current fork checkout, so its existing
`HEAD`/`origin/main` ancestry checks still cannot establish the required relation.

| Contract | Historical anchor |
| --- | --- |
| Calibration superseded | `a5527708833df308e67536aaa690b4f16e88dccd` |
| Calibration superseding | `e71d1915233283452f3fb219aafabd2f19035371` |
| D002H Gate A | `1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5` |
| D002H Gate B | `b97daae8b554ab9960510564e19263adcc1fe71b` |
| D002H Gate C | `a9d852d34258861809325df81bd7cba6d0e557ec` |
| D002H Gate D | `077073ee801c434840d64f911e7b1f39ce2ac0fa` |
| D002H Gate E | `e1d3ae304274e8b8f509edeb83b0a9adfeb43a77` |
| D002H Gate F | `0e598fff84308356fd93e953d4fdde0b7811ac53` |

1. **Attempted:** recover original source bytes and inspect all eight historical
   objects against the current fork and pinned upstream history.
2. **Gate:** calibration supersession ancestry and D002H Gates F/G require
   ancestors of current `HEAD` or `origin/main`.
3. **Observed failure:** current-fork ancestry probes cannot resolve the anchor
   objects; all eight upstream ancestry probes return exit 0.
4. **Why an honest pass is unavailable:** upstream ancestry and identical file
   content do not establish the separate current-fork ancestry relation.
5. **Protected surface:** immutable anchor SHAs, frozen pins, and existing
   ancestry assertions remain unchanged; no graft, replacement ref, skip, or
   fallback was introduced.
6. **Safe next step:** review an explicit fork/import provenance contract that
   binds the source parent chain, pinned source snapshot, real import commit,
   and imported content. Keep that relation distinct from direct ancestry.
7. **Owner decision required:** approve any change to the lineage acceptance
   contract before implementation. This source restoration does not supply that
   approval or authorize merging a blocked PR.

## Agent state and claim boundary

| State | Value |
| --- | --- |
| `intent_type` | Repair frozen source identity and missing governance examples |
| `canonical_files_used` | `AGENTS.md`, `CLAUDE.md`, `README.md`, `PRODUCT_CATEGORY.md`, `CLAIMS.md`, `FORBIDDEN_CLAIMS.md`; repository, autonomous execution, semantic control, inference readiness, and inference operation protocols; inference manifest; existing schemas and acceptor policy |
| `file_roles_used` | Sources and historical examples: artifact/context; ignore rules: boundary; tests: replay/falsifier; acceptor: protocol; this report: context |
| `claim_tier_before` / `claim_tier_after` | Unchanged historical proxy and frozen research status |
| `changed_surface_type` | Source restoration, historical examples, test validation, bounded provenance report |
| `allowed_method` | Exact upstream byte recovery and existing-validator replay with negative controls |
| `blocked_claims` | New empiricism, full CI success, release readiness, current-fork ancestry, merge authorization |
| `verification_command` | Acceptor `measurement_command` and `falsifier.command` |
| `evidence_artifact_path` | This report, acceptor evidence hashes, and local replay receipts above |
| `remaining_blocker` | Eight lineage anchors; other PR gates are outside this bounded repair |

Interpretation follows [SEMANTIC_CONTROL_LAYER.md](../SEMANTIC_CONTROL_LAYER.md),
[INFERENCE_READINESS.md](../INFERENCE_READINESS.md), and
[INFERENCE_OPERATION_PROTOCOL.md](../INFERENCE_OPERATION_PROTOCOL.md).

## Context for continued PR work

The combined replay used Python 3.12 with the hash-verified development-lock
versions `statsmodels==0.14.6` and `patsy==1.0.2`. Its 197 tests comprise 44 frozen
source/gate tests, 21 governance-example tests, 39 estimator/lock tests, 11
migration/middleware tests, four dependency/evidence/claim negative controls,
and 78 scanner, false-confidence, and hermetic-image tests. Other installed
packages were a temporary validation environment, not a fresh installation of
the complete project lock; GitHub Actions remains the authority for that
environment and for the full suite.

The companion acceptors bind three additional repairs: unavailable or failed
ADF evidence now leaves estimates invalid; Alembic preserves application error
logging; and scanner/audit fixes distinguish public labels and references from
credentials while auditing the exact Docker image dependency heredoc. These
changes preserve the existing numerical thresholds and negative controls.

Known remaining work at the initial head must be checked against each new
commit's complete check-run inventory:

- Fourteen licensed Askar parquet inputs are absent from this fork. All 14
  required filenames were subsequently located in the pinned upstream tree;
  their content, checksums, provenance, and redistribution permission have
  not yet been validated. The explicit `NO_REAL_DATA_MANIFEST_STAGED` failure
  also requires genuine licensed inputs and their provenance manifest.
  Synthetic substitutions do not satisfy it.
- Historical ancestry remains blocked as described above. Recovering original
  bytes does not establish an ancestor relation in this fork.
- The ten-axis gate reports real mutation-enrollment, public-docstring, and
  type-escape debt, plus an unclassified archived secret baseline. Resolve
  specific findings with tests and canonical scope evidence; do not raise
  budgets or repin the measured baseline to conceal them.

Continue from the latest remote PR head, preserve concurrent commits, and use
an expected-head lease for updates. Fetch all check-run pages: the connector's
workflow-run listing alone returns only its first page. A local targeted pass
does not establish a green PR; record the exact commit and terminal CI verdict
before making a broader claim.

A subsequent PR Gate repair corrects detect-secrets metadata normalization:
the scanner replaces its saved file regex with the declared CLI regex, rather
than retaining the old regex string in a set. The validator now requires that
exact declared policy while preserving its fingerprint, version, plugin, and
other-filter checks. Fourteen additional tests execute the actual workflow
validator, including twelve rejected forms of unreviewed drift. No exclusion
pattern was added by this repair. Individually verified public artifact/file
digests were reconciled in the baseline; credential findings were not approved.

Read-only upstream metadata inspection located all 14 Askar objects as ordinary
Git blobs totaling 16,298,908 bytes. Coverage metadata supplies neither the
required raw-file SHA256 values nor a vendor permission record. The current
[dataset policy](../DATASET_MANIFEST_POLICY.md) explicitly classifies Askar as
`MEASURED` / `UNKNOWN` / `RED`; no parquet payload was downloaded or staged.

The evidence-runner implementation and the typed acceptor schema currently
describe conflicting falsifier exit conventions; the runner also writes an
`evidence_sha256` field that the strict schema does not admit. These new
acceptors remain `ACTIVE`, follow the schema's inverse-falsifier convention,
and were checked using their declared commands directly. Reconcile the runner
and contract before using it to promote them to `VERIFIED`.

## CI follow-up after the first repair

The repair was published as
[`96a8f48`](https://github.com/neuron7x/Kuramoto-synchronization-model/commit/96a8f48b4cb6290db7aac9446cbc5bd86a27b821).
Two newly exercised checks exposed further environment and dependency debt:

- [Mutation job 122491793532](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40590097659/job/122491793532)
  could not establish the gamma baseline. Replaying the exact workflow in a
  fresh, isolated Python 3.12 environment failed collection because Hypothesis
  was absent. Adding the dev-lock Hypothesis, statsmodels and patsy releases
  then exposed a pandas 3.1 deprecation error during statsmodels 0.14.6 import.
  The workflow now also uses the compatible dev-lock pandas 2.3.3 release.
  Its 25 gamma tests pass. The real logic mutation probe killed 14 of 16
  mutants (87.5%), above the unchanged 85% floor; both surviving comparison
  mutations remain recorded. The probe restored the isolated source bytes.
  Local receipt: `tmp/pr2833_mutation_environment_receipt.json`.
- [Service audit job 122491794717](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40590098103/job/122491794717)
  passed the new exact-heredoc extraction and hermetic audit, then found
  `PYSEC-2026-2190` and `PYSEC-2026-2191` in the existing CoherenceBridge
  Kafka client. Both service pins now use the fixed `kafka-python==2.3.2`.
  Local audits pass for CoherenceBridge (21 resolved dependencies), sandbox
  (24), and the root service requirements (142). Five existing producer tests
  pass with the service-resolved Protobuf version; a hash-verified official
  Kafka wheel also accepts the existing producer configuration and serializers.
  Local receipts: `tmp/pr2833_service_dependency_audit/`.

The old CoherenceBridge lock retains its explicit offline-placeholder header,
missing hashes and nine other pre-existing version drifts. Updating its Kafka
pin does not certify that lock. No live Kafka broker or Docker/Python 3.11
service replay was performed. These follow-up results are local evidence;
check the next published commit's terminal CI results before claiming that
either remote job is fixed. Research tiers and frozen artifact pins are
unchanged.

## 2026-10-28 — governance kernel source recovery and mutation receipt

The canonical governance verification kernel `data/governance/neuron7x_verification_protocol_v2026_8.json` was recovered
byte-for-byte from `neuron7xLab/GeoSync` commit
`174aef0c46dc25a6b59bc8fb1457d20e13a38c11` (Git blob
`c7e4162b615e87e11699a679781a73a3d2442c3f`), SHA256
`01bec86cda97f1256bf6ba3c25041dfc115e09422264c9ae8be6e485bd717326`. The existing JSON schema, 5% ADF boundary and negative kernel
validation tests were not relaxed. This is a governance contract, not measured
market data or evidence for scientific promotion.

Exact-parent `Mutation Kill Gate` run `40593099169`, job `122502072824`,
measured **14/16** killed gamma logic sites (87.5%), while the stored ledger
said 13/15. Only the two recorded counts are reconciled; floor **0.85** and
the two surviving mutants remain unchanged. The governance tooling coverage
profile is now explicitly routed in the component-test matrix without
altering the release coverage denominator.

Replay: `python -m pytest -q --override-ini addopts='' tests/unit/governance/test_verification_protocol.py tests/tools/test_governance_tooling_coverage_profile.py`,
`python scripts/ci/check_mutation_kill_ratchet.py --base-ref origin/main`,
`python scripts/ci/check_manifest_hashes.py`. These are post-change checks,
not a claim of execution at patch creation; newly triggered exact-SHA CI must
verify. Askar licensing, flattened-history ancestry, debt budgets and the
release evidence digest cycle remain separate blockers.

## 2026-10-28 — certification bootstrap suppressions

The research-integrity exact-parent run `40593099402` measured **340**
real `# noqa` suppressions against the immutable budget **338**. The two
side-effect-only optional imports in `scripts/serotonin_certify.py` were
changed to equivalent `importlib.import_module` calls under their existing
`ImportError` guards; this removes two otherwise unused-import suppressions
and two type-ignore directives without reducing coverage or changing the
certification pipeline. Execution controls run the original AST import guards
with successful, missing-module and unexpected-error witnesses. No frozen
research source or numerical threshold was changed. The unchanged budget and
runtime evidence must be revalidated by the new exact-SHA CI; no pass is
preclaimed by this note.


## 2026-10-28 — isolate diagnostic receipts from the secret-scan root

Exact-parent PR Fast Diagnostics run [40601989404](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40601989404),
job [122532432668](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40601989404/job/122532432668),
failed `test_full_gate_passes_on_clean_tree` when its own generated
`artifacts/pr-fast-diagnostics/group-4/shard_nodeids.txt` was scanned by
SEC-006. Some collected test IDs contain token-like assignment strings: the
scanner classified these transient diagnostic lines as credentials. They were
not tracked repository sources and were produced by the same diagnostic job
before the clean-tree test ran. This is a self-contamination failure, **not**
a reason to disable the scanner or dismiss its negative controls.

The diagnostics workflow now writes all test collection, shard selection,
execution logs and status receipts under `$RUNNER_TEMP/pr-fast-diagnostics/`,
and uploads the same evidence artifact from `${{ runner.temp }}`. The
contract regression checks both shell paths, the Python shard-selection
variable and the artifact upload path; existing SEC-006 planted AWS/PEM
negative controls and the unmodified repository scanner remain authoritative.
No exclusion pattern, baseline fingerprint, test selection, timeout or numeric
threshold changed. This patch removes the specific verified source of
self-contamination; it is **not** evidence that the inherited Askar licensing,
upstream Git ancestry, root debt budgets or historical release bundle gates
are green. Validate only against terminal checks for the newly published SHA.

## 2026-10-28 — historical entrypoint scope, with negative control

The exact-parent [PR Gate job 122548559408](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40606555621/job/122548559408)
failed `test_single_entrypoint_guard_has_no_violations` because the live
entrypoint scanner traversed
`archive_snapshots/github_9e6e4792_unique/src/tradepulse/sdk/mlsdm/__main__.py`.
That path is an imported, preserved upstream snapshot rather than an active
executable entrypoint. Other repository gates already classify the **top-level**
`archive_snapshots/` as historical, not live code.

The scanner now excludes only entrypoints whose first repository-relative
path segment is exactly `archive_snapshots`. It **still fails** for a
noncanonical `__main__.py` under a nested `runtime/archive_snapshots/`
or a similarly named `archive_snapshots_live/`, as asserted by a new
negative control. The three canonical entrypoints, the named live legacy
allowlist and every other discoverable entrypoint remain governed. No
frozen source, claim tier, ancestry assertion, numerical tolerance, secret
scanner or debt budget is changed.

A synthetic isolated replay of this exact scanner branch and negative
fixture passed (1 test). Canonical commands after commit:
`python -m pytest -q --override-ini addopts='' tests/test_architecture_guards.py`
and `python scripts/ci/check_root_manifest.py`.
The synthetic result is **not** full-repository CI proof. Askar permissions,
eight flattened-history anchor predicates, release-evidence self-consistency,
and other actual exact-head failures remain unresolved.

## 2026-10-28 — preserve optional import semantics while retiring two suppressions

The [Research Integrity Gate](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40606555947/job/122547385996)
still measured 340 actual Python lint suppressions against the immutable 338
budget on parent `96fafcc`, despite a previous reduction in the certification
bootstrap. This is unresolved real debt, not grounds to raise the budget.

Two unrelated *unused-import* suppressions were therefore removed without
sacrificing their runtime checks. In `tools/validate_dopamine_config.py`,
the duplicate `import jsonschema` is removed: the retained
`from jsonschema import Draft7Validator` still imports the module and
preserves the explicit fail-closed error. In `scripts/commands/build_core.py`,
an unused `import build` is replaced by
`importlib.import_module("build")` under the same `ModuleNotFoundError`
guard, retaining both the missing-dependency message and import-time side
effects. The new regression suite executes extracted production AST
guards for success, absence and unexpected errors; it does not fake a build
artifact or a complete runtime install.

Expected debt delta: two fewer real suppressions, with budget 338 unchanged.
Exact-head CI must measure the entire tree before a ratchet PASS can be
reported. No frozen source, research claim, empirical data or release evidence
hash has been repinned. Replay:
`python -m pytest -q --override-ini addopts='' tests/ci/test_optional_import_probes.py`,
`python -m pytest -q --override-ini addopts='' tests/ci/test_architecture_debt_inference.py`,
`python scripts/ci/check_root_manifest.py`.

## 2026-10-28 — P0-5 numerical clamp registry: source-preserving line-shift repair

At PR parent `ec77a95a34a3f925e7cc7831e4b4744494a98a63`, [fast-shard job 122572158664](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40613663861/job/122572158664) reported **11 SAFE_LINE_SHIFT groups, 16 existing sites, 0 NEW_CLAMP, 0 REMOVED_CLAMP** in `test_real_tree_is_in_sync`. Each newly reported line was checked against the current exact-head source text and matching clamp operation. Only registry `path:line` addresses changed; the original count of registrations per path and shape, eight clamp classes, declared reasons, physics implementation, numerical thresholds, source and scanner scope remain intact.

Affected sources: `core/indicators/hurst.py` (1), `core/indicators/kuramoto.py` (6), `core/physics/lyapunov_exponent.py` (3), `core/physics/lyapunov_spectrum.py` (4) and `core/physics/wave_propagation.py` (2). The existing hard-void tests for NEW_CLAMP, count change, unregistered clamps and stale registrations remain in force; no newly introduced clamp is authorized by a line shift.

Replay on the new commit: `python tools/physics/check_silent_clamps.py --json && python tools/physics/predict_clamp_voids.py && python -m pytest -q --override-ini addopts='' tests/tools/test_predict_clamp_voids.py tests/tools/test_numerical_policy.py`. The scoped acceptor `.claude/commit_acceptors/pr2833-clamp-site-line-shifts-20261028.yaml` remains `ACTIVE` until actual exact-new-HEAD tests pass; this update does not claim the whole PR green or satisfy outstanding Askar, ancestry or release-evidence blockers.

## 2026-10-28 — REL-011 release bundle digest reconciliation (NOT_READY preserved)

[Repo-integrity job 122571096652](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40613663857/job/122571096652) found three release-bundle integrity failures because the canonical `artifacts/releases/1.1.0/release_evidence.json` and `SHA256SUMS` were still bound to an obsolete `MANIFEST.sha256` SHA256 (`9a923dc752b3c1261924972525a0333f96f683cffdb2e05eafbe5e39e31928c1`). The actual source manifest's SHA256 at `bfe551a782e3d0fff4b05eeedb4dc90a6322b125` was `f623d8419a0c1c87663f563b3fcde5734093791f69d68757d519c81a3fc02694`.

The release generator `scripts/ci/check_release_evidence.py` builds deterministic, sorted-key canonical JSON and path-sorted SHA256SUMS from on-disk artifact bytes. **All 13 other referenced artifacts were fetched and independently SHA256-verified from this exact Git commit (13/13 match),** and the original bundle and checksums were byte-exact to their deterministic serializers. The only changed release-artifact field is the digest of the current root manifest; the latter is derived after appending this provenance and its `ACTIVE` acceptor. All 14 present artifact references remain content-bound.

The `MANIFEST.sha256` generator excludes the `artifacts/` tree, so the release bundle's manifest reference is **acyclic**; the root manifest doesn't pin the release bundle. The release source ref and every research hash, artifact verdict, schema, numeric floor, gate and policy remain unchanged. In particular **release_readiness.verdict stays NOT_READY**, with five missing mandatory receipt categories: `coverage`, `mutation`, `sbom`, `tests`, `wheel`. No evidence was fabricated to satisfy them.

Proof obligations for this commit: `python -m pytest -q --override-ini addopts='' tests/ci/test_release_evidence.py && python scripts/ci/check_root_manifest.py`. Negative controls include tampered artifact digests, stale bundle, injected schema category and missing mandatory receipts. The acceptor `.claude/commit_acceptors/pr2833-release-bundle-digest-binding-20261028.yaml` remains **ACTIVE** pending exact-new-HEAD CI. Full release readiness remains RED; this work corrects only integrity drift.

## 2026-10-28 — archived Git snapshots are inert to canonical namespace enforcement

[Fast-shard 8 job 122572158646](https://github.com/neuron7x/Kuramoto-synchronization-model/actions/runs/40613663861/job/122572158646) failed `tests/test_architecture_guards.py::test_namespace_integrity_has_no_violations`: the broad `__CANONICAL__` scanner flagged 32 historical package files, first `archive_snapshots/github_9e6e4792_unique/src/tradepulse/__init__.py`. The repository's canonical [code-quality scope](../../CODE_QUALITY_MANIFEST.json) already classifies `archive_snapshots` as a preserved excluded source root. This is historical content, not a live package declaring authority for the current runtime.

Repair: `scripts/check_namespace_integrity.py::_is_scannable` excludes **only** files whose first relative path segment is `archive_snapshots`. Every `src/geosync` canonical package remains mandatory. The existing negative control still detects `analytics/rogue/__init__.py`. A new regression plants an archived `__CANONICAL__ = True` package and two ACTIVE counterparts under `runtime/archive_snapshots/...` and `archive_snapshots_live/...`; only the latter must violate. This preserves the attack detection and avoids weakening other namespaces. No runtime source or architectural budgets changed.

Replay: `python -m pytest -q --override-ini addopts='' tests/test_architecture_guards.py && python scripts/check_namespace_integrity.py && python scripts/ci/check_root_manifest.py`. The scoped acceptor `.claude/commit_acceptors/pr2833-archive-namespace-scope-20261028.yaml` remains `ACTIVE` pending exact-new-HEAD CI. The deterministic REL-011 release bundle and SHA256SUMS must be regenerated in the same commit to bind the new root manifest digest (all five missing mandatory release receipts and NOT_READY preserved). No Askar, lineage or other evidence claim is promoted.
