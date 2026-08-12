# ADR 0021 — Falsifier-required ANCHORED claims (Phase 1 entry gate)

**Status.** Accepted (planning), 2026-05-03. Implementation lands in Phase 1.
**Supersedes.** Nothing — extends [ADR 0020](0020-ierd-adoption.md) by tightening the ANCHORED tier semantics.
**Related.**
- [`docs/governance/IERD-PAI-FPS-UX-001.md`](../governance/IERD-PAI-FPS-UX-001.md) (binding directive, §1 + §4 + §5)
- [`docs/CLAIMS.yaml`](../CLAIMS.yaml) (current schema v2)
- [`scripts/ci/check_claims.py`](../../scripts/ci/check_claims.py) (current schema validator)
- [`scripts/ci/compute_fps_audit.py`](../../scripts/ci/compute_fps_audit.py) (current FPS_audit computation)

---

## Context

Phase 0 of IERD adoption (ADR 0020) introduced the four-tier claim ledger (ANCHORED / EXTRAPOLATED / SPECULATIVE / UNKNOWN). At Phase 0, an **ANCHORED** entry requires:

1. every artefact in `evidence_paths` exists, AND
2. the `evidence_paths` set contains at least one test file or one frozen artefact (per `compute_fps_audit.py`).

This is a real bar. It is also **not enough** to support the IERD §1 promise that "every ANCHORED claim has a falsifying test". A test can exist alongside a claim without actually being a falsifier — for example, a test that asserts `result is not None` is a code-correctness test, not a physics-falsification test.

The CLAUDE.md `Forbidden:` block already bans the magic-number / no-INV / no-context test patterns:

```python
assert R < 0.3              # magic number — forbidden
assert R == 0.0              # exact on stochastic — forbidden
assert result.order > 0      # no INV, no context — forbidden
```

But this rule lives in CLAUDE.md and is enforced by `.claude/physics/validate_tests.py`. It is **not** structurally bound to the claim ledger. An ANCHORED claim can therefore reference a generic test that happens to exist, and the gate would still pass.

Phase 1 closes this gap.

## Decision

Phase 1 entry promotes the schema to v3 and adds a required `falsifier` field on every ANCHORED claim. The shape:

```yaml
- id: kuramoto-order-parameter-bounded
  priority: P0
  tier: ANCHORED
  description: >
    Kuramoto order parameter R(t) is universally bounded
    0 ≤ R(t) ≤ 1 for all t (INV-K1) ...
  evidence_paths:
    - core/kuramoto/ott_antonsen.py
    - tests/unit/physics/test_T23_ott_antonsen_chimera.py
  falsifier:
    test_id: tests/unit/physics/test_T23_ott_antonsen_chimera.py::test_invariant_K1_bounded
    invariants_cited:
      - INV-K1
      - INV-OA1
    failure_signature: >
      assertion message must contain "INV-K1 VIOLATED:" or
      "INV-OA1 VIOLATED:" with R-value, threshold, and step count
      per the CLAUDE.md 5-field error message rule.
  added_utc: "2026-05-03"
```

EXTRAPOLATED, SPECULATIVE, and UNKNOWN tiers do not require `falsifier` — for those, `evidence_paths` alone is the bar.

### Schema v3 changes (machine-readable diff)

* New required field on ANCHORED claims:
  ```yaml
  falsifier:
    test_id: <pytest node id, kebab-or-double-colon>
    invariants_cited: [<INV-...>, ...]
    failure_signature: <docstring fragment>
  ```
* `check_claims.py`:
  * accepts schema_version `1` (legacy → ANCHORED default), `2` (current), and `3` (new);
  * for v3 ANCHORED entries, validates that `falsifier.test_id` parses as a valid pytest node id and that the file part exists;
  * cross-checks that every `INV-*` in `falsifier.invariants_cited` actually appears in the test file (grep), and emits a hard error otherwise;
  * cross-checks that the test file's body contains a 5-field assertion message matching the `failure_signature` shape (loose substring match, not a strict regex).
* `compute_fps_audit.py`:
  * adds a third bit `F` to the audit row: `[T A p F]` — `F` is set iff the falsifier exists, parses, and the citations match;
  * `counts_for_numerator` requires `F` set on ANCHORED entries (EXTRAPOLATED still passes on the test-or-artefact bar alone).

### Phased rollout inside Phase 1

Anchor date: 2026-05-03 (PR #528 merge target). All intervals are
**relative to the merge date** so a slip in Phase 0 propagates
deterministically. CI clock is calendar time, not engineering time.

| Step | Scope | Target | Exit |
|---|---|---|---|
| 1.0 | publish schema v3 with `falsifier` optional and warn-only on missing | **anchor + 0 days (this PR)** | parser accepts v1/v2/v3, `falsifier` shape validated when present, warn fired on v3 ANCHORED missing falsifier |
| 1.1 | backfill `falsifier` on the 19 ANCHORED claims in the current ledger | **anchor + 14 days** | `check_claims.py` reports `falsifier coverage: 19/19 ANCHORED` |
| 1.2 | flip `falsifier` to **required** on v3 ANCHORED via opt-in flag `--require-falsifier` in CI | **anchor + 21 days** | a v3 ANCHORED entry without `falsifier` fails the gate |
| 1.3 | bind `compute_pai.py` to falsifier audit: a module is "covered" only if every routed `INV-*` has a falsifier-test reference in CLAIMS.yaml | **anchor + 35 days** | `compute_pai.py --require-falsifier` is the new default; PAI tightens; informational forbidden_assertion_count becomes a hard cap |
| 1.4 | wire `.claude/physics/validate_tests.py` into CI as a separate gate that runs against every test referenced from a `falsifier.test_id` | **anchor + 49 days** | structural test taxonomy + 5-field error-message rule enforced as merge gate |
| 1.exit | full Phase-1 compliance | **anchor + 56 days** | new claim `geosync-phase1-falsifier-coverage` lands as ANCHORED P0 with FPS_audit-grade evidence |

Each step is a separate PR. The schema change does not regress Phase-0 invariants because v2 is still accepted during Phase 1.0–1.1. The 56-day clock starts on PR #528 merge to `main`; slip is logged in `docs/governance/IERD-PAI-FPS-UX-001.md` as a deviation marker.

## Consequences

### Positive

* The "ANCHORED but no real falsifier" loophole is closed. Yana's Q1 / Q2 attack vectors lose the "you have tests but they don't falsify" angle.
* `compute_pai.py` and `compute_fps_audit.py` numbers stop being lower bounds; they become tight measurements of the falsifier bar.
* CLAUDE.md's existing `validate_tests.py` discipline binds to the public claim ledger — single source of truth.

### Costs

* Backfilling 19 ANCHORED entries with falsifier metadata costs roughly one PR per cluster (kuramoto, ricci, lyapunov, etc.). Scoped under Phase 1.1.
* Tests that today implicitly cover an INV but don't carry the citation (the pattern fixed in Wave 2 for DRO-ARA and DFA criticality) need a corresponding `falsifier.test_id` entry. Some tests will need a `failure_signature`-shaped assertion message added.
* Schema v3 acceptance bumps the `check_claims.py` complexity slightly. New unit tests required.

### Risks

* If `validate_tests.py` rejects a referenced test as structurally non-conformant (taxonomy mismatch), the CI gate refuses to admit the claim until the test is restructured. Mitigation: Phase 1.0 lands schema v3 with the `falsifier` field optional and `--strict-falsifier` warn-only for two weeks before the final flip.
* Some claims (e.g. the cross-asset Kuramoto walk-forward bundle) are EXTRAPOLATED with frozen-artefact evidence rather than a single falsifier test. The schema explicitly does not require `falsifier` for EXTRAPOLATED. This is intentional and matches the spirit of the tier.

## Alternatives considered

1. **Make `falsifier` required on every tier.** Rejected — SPECULATIVE means "no falsifier yet", that's the entire point of the tier. Forcing one would conflate research notes with engineering claims.
2. **Make `falsifier` a free-text field.** Rejected — would not be machine-checkable; we'd be back to the same problem at one level of indirection.
3. **Use the existing `commit_acceptor.yaml` falsifier shape verbatim.** Considered. The acceptor format has `falsifier.command` (a shell command); the claim ledger needs `falsifier.test_id` (a pytest node id). The acceptor's command-runner pattern is heavier than what the claim gate needs at PR time. Compromise: the field shape is borrowed (object with named keys), but the contents differ.
4. **Defer to Phase 2.** Rejected — Phase 2 is for ADRs + convergence reports, which are about process documentation. Phase 1 is the right home for "claim ledger evidence quality", since the ledger is what Phase 0 just shipped.

## References

* IERD-PAI-FPS-UX-001 directive: `docs/governance/IERD-PAI-FPS-UX-001.md`.
* Phase 0 adoption: `docs/adr/0020-ierd-adoption.md`.
* External-audit response: `docs/yana-response.md` (Q1, Q2).
* CLAUDE.md TEST TAXONOMY + Forbidden block.
* `.claude/physics/validate_tests.py` — the structural validator that schema v3 will bind to.
