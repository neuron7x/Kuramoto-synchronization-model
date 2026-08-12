# Destruction Stage — Consolidated Findings (mandatory pre-integration destruction)

Base attacked: `186d245ef` (remediation/wave12 == grp/main HEAD).
6 destroyer agents (data-corruption, permission-collisions, dependency-failure, load-beyond-SLA,
malformed-input, operator-error) + TST-007 skip-classification. All attacks isolated (no commits,
trees left clean). This file is the machine-evidence record; each CONFIRMED item becomes a fix with a
**regression test that replays the exact destroyer repro** (positive + would-have-caught negative).

Legend: FO = fail-OPEN (false-GREEN / accepts garbage as valid — worst class); FC = fail-CRASH
(fail-closed but crash/hang/uninformative — availability/DoS); DES = design/config gap.

## CONFIRMED — fail-OPEN (false verdict / accepts a provable lie)

| ID | Sev | Class | Locus | Defect | Fix direction |
|----|-----|-------|-------|--------|---------------|
| DS-01 | HIGH | FO | src/ebsvap/claim_compiler.py FORBIDDEN_PATTERNS | homoglyph/ZWSP/NUL bypass: `prоven`(Cyrl о), `pro​ven`, `pro\x00ven` → ADMIT; ASCII twin → REJECT. Defeats admissibility contract. | NFKC-normalize + confusable-fold + strip control/zero-width before matching |
| DS-02 | HIGH | FO | scripts/ci/check_state_ontology.py + check_terminology.py | same regex-on-raw-text; forbidden word slips past ontology firewall | shared normalizer, same fix |
| DS-03 | HIGH | FO | scripts/ci/check_physics_score.py `--scan` NEGATION | any of not/never/no/non-/without on the line disarms the whole violation: "validated, not overfit"→PASS | scope negation to the claim clause; do not blanket-disarm the line |
| DS-04 | MED | FO | scripts/ci/check_physics_score.py `--scan` | `\bvalidated\b` past-tense only; "validates"(present)→PASS | add validate/validates/validating/validation stems |
| DS-05 | HIGH | FO | geosync/risk/risk_core.py:135 kelly_shrink | `lambda_map.get(ews_level, 0.5)`: UNKNOWN/None/""/wrong-case → 0.5 half-size instead of fail-closed | default 0.0 (fail-closed KILL on unrecognized regime) |
| DS-06 | HIGH | FO | scripts/ci/check_ci_permissions.py:341 audit_dir | `glob("*.yml")` only — `pwn.yaml` never scanned (GH runs both) | glob yml+yaml |
| DS-07 | HIGH | FO | scripts/ci/check_ci_permissions.py:158,244 | job-level `permissions: write-all` (string) → `{}`, WRITE_ALL_DEFAULT top-level only → job self-grants all writes, PASS | flag write-all string at job level |
| DS-08 | MED | FO | scripts/ci/check_ci_permissions.py `_checks_out_pr_head` | pwn-request evasions: `run: git fetch refs/pull/N/head` and `ref: ${{ env.PRREF }}` indirection → PASS | detect run-step PR-head fetch + env-indirection ref |
| DS-09 | HIGH | FO | scripts/ci/release_gate.py probe_d_manifest_coldverify | coverage-blind: drop line + corrupt file → GREEN(MISS); add tracked-but-unlisted file → GREEN. Docstring calls it "supply-chain integrity proof". Canonical gate backstops CI, but release_gate standalone false-green | delegate to generate_manifest.check() / add set-comparison |
| DS-10 | MED | FO | scripts/ci/check_dataset_manifests.py | evidence-class inversion: SIMULATION→FACT passes though manifest body says origin:repository_generated / SYNTHETIC_GENERATED | provenance-consistency: FACT/MEASURED incompatible with synthetic origin markers |
| DS-11 | MED | FO/DES | governance/remediation_ledger.v1.json | NO validating gate (0 CI/test refs); schema never executed; item TST-001 status "partial-env-limited" ∉ enum → committed ledger schema-INVALID; closed⟹PASS unenforced | add scripts/ci/check_remediation_ledger.py (schema + baseline_tree resolves + closed⟹verdict:PASS + source_evidence exists); fix TST-001 status; wire into CI |
| DS-12 | MED | FO | scripts/ci/check_debt_baseline_monotonic.py | `NaN` JSON literal (json.loads accepts) → sum=nan, `nan>base==False` → debt growth undetected, PASS | reject non-finite JSON numbers (parse_constant); isinstance(dict) guards; run under -O safe |
| DS-13 | MED | FO | core/physics/lyapunov_spectrum.py | INV-LY3 validates dt/n_steps/qr_every/shape but NOT x0 finiteness → NaN x0 returns plausible spectrum | validate x0 all-finite → ValueError |

## CONFIRMED — fail-CRASH (fail-closed but crash/hang/uninformative — DoS)

| ID | Sev | Class | Locus | Defect | Fix direction |
|----|-----|-------|-------|--------|---------------|
| DS-14 | MED | FC | src/ebsvap/claim_compiler.py compile_claim | unbounded conjunct recursion → depth 1000 uncaught RecursionError (crash, not REJECT) | explicit depth guard / iterative → REJECT with reason |
| DS-15 | MED | FC | src/ebsvap/claim_compiler.py compile_claim | non-dict evidence(list/None), non-Claim conjuncts(str), non-str text(int) → AttributeError crash | type-guards → REJECT (fail-closed clear reason) |
| DS-16 | MED | FC | core/physics/lyapunov_exponent.py maximal_lyapunov_exponent | O(n²) divergence double-loop, no length cap → 100k series ≈ 3-4h hang | length cap / step budget → ValueError |
| DS-17 | LOW | FC | ~20 gates json.loads(...).get() | no isinstance(dict) guard; nested-JSON RecursionError uncaught → uninformative crash (fail-closed on exit) | shared safe-load-dict helper |
| DS-18 | LOW | FC | 4 gates (state_ontology/terminology/dataset/numerical_stability) | crash raw ModuleNotFoundError under missing dep instead of clean exit-2 | guarded import → exit 2 |

## CONFIRMED — design / architecture (deeper; scoped)

| ID | Sev | Class | Locus | Defect | Fix direction |
|----|-----|-------|-------|--------|---------------|
| DS-19 | MED/HIGH | DES | src/ebsvap/authority_gateway.py ActionCertificate | no MAC over cert fields: knowing a live authority string → forge cert (own nonce/args_hash) → AUTHORIZED. "proof-carrying" reduces to secret string | HMAC signature binding cert→issuer (keyed registry), verify in authorize |
| DS-20 | MED | DES | src/ebsvap/authority_gateway.py _used_nonces | per-Gateway nonce set → cross-instance replay (AUTHORIZED again on g2) | shared durable ledger injection point + document; add replay test |
| DS-21 | LOW/MED | FO | src/ebsvap/authority_gateway.py args_hash | json.dumps(default=repr) → crafted `__repr__` collides args_hash({obj})==args_hash('1') | reject non-JSON-native values (no default=repr silent coercion) or type-tag |
| DS-22 | LOW | FC | admin/api.py:72 | hmac.compare_digest(str,str) raises TypeError on non-ASCII Bearer → HTTP 500 spam (DoS, not bypass) | .encode() both operands to bytes |
| DS-23 | MED | DES | scripts/ci/generate_manifest.py / check_root_manifest.py | cold-verify hashes WORKING TREE not HEAD → regenerate-on-dirty-tree false-green + partial-commit local-GREEN/fresh-clone-RED. CI not fooled (clean checkout) | dirty-tree guard / HEAD-consistency assertion |

## HELD (attacked, did not break — honest nulls; recorded to prove non-vacuity)
- yaml.safe_load everywhere (no !!python/object RCE). maximal_lyapunov_exponent degeneracy guards
  (empty/1-elem/identical/NaN/Inf/2D → INV-LE1 ValueError). lyapunov_spectrum dt/n_steps/shape guards.
  execution KillSwitch snapshot atomic (0 torn reads / 50k races). position_sizer neg/NaN/inf → 0.0.
  admin auth wrong/empty → 401, unset token → 500 fail-closed, no NFKC bypass. MANIFEST canonical gate
  (generate_manifest --check) RED on flip/truncate/swap/drop/extra. dataset per-file checksum RED.
  lineage determinism-oracle re-execution RED on golden-CSV mutation. lock gate malformed/unpin/strip RED.
  reproducible-archive untracked-injection robust by git-archive construction. waivers/version-ssot/
  skip-ratchet all fail-closed. process_oracle whitelist fail-closed.
