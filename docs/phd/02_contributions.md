# 02 — Contributions

Five contributions, each a committed, CI-enforced mechanism. Each is scoped to
*admissibility* (fail-closed governance), explicitly not to empirical market
truth.

## C1 — Executable falsifier ledger

A machine-readable registry binding each null/kill-test to a real implementation
symbol and a test witness; a fail-closed gate refuses the build if any falsifier
"rots" into prose (missing file, renamed symbol, absent witness).

- `governance/FALSIFIER_LEDGER.yaml` (6 falsifiers) · `scripts/ci/check_falsifier_ledger.py`
- Wired into the release gate (`H.falsification`: MANUAL stub → GREEN probe).

## C2 — Wheel / artifact contract

A clean-room build contract proving the distributable is structurally honest:
every console-script target ships, no packaged module imports an unpackaged
first-party namespace, and the legacy surface only shrinks (monotone ledger).

- `scripts/ci/check_wheel_contract.py` → `artifacts/wheel_contract.json`
- `.github/bwheel_baseline.json` (transitional ledger) · `scripts/ci/check_package_boundary.py`
- Built from `git archive HEAD` to be immune to stale `build/` cache and pip cache.

## C3 — Claim-tier governance

A fail-closed boundary between admissibility and empirical claim: forbidden
promotion terms are blocked unless backed by a linked evidence-chain or negative
context; research-line claims must declare a falsifier/null to earn a PASS tier.

- `scripts/ci/lint_forbidden_terms.py`, `check_claim_boundary.py`,
  `check_claim_artifact_graph.py`, `check_claim_maturity.py`
- Documented negative finding: bare-word bans over-reject disclaimers → narrow,
  compound-pattern design (see `01` RQ1).

## C4 — Import-boundary debt ratchet

A monotone-down ledger of architectural debt (first-party `src.*` imports,
`sys.path` mutations, and non-`geosync` wheel packages): new debt fails the
build; paid-down debt must tighten the ledger.

- `scripts/ci/check_import_architecture.py` + `.github/import_architecture_baseline.json`
- `scripts/ci/check_package_boundary.py` + `.github/package_boundary_baseline.json`
- Wrapper-first re-home pattern for BLOCKED subsystems (`geosync.kuramoto.cli`,
  `geosync.runtime.server`), with a laziness invariant test
  (`tests/ci/test_wrapper_laziness.py`).

## C5 — Negative-evidence protocol

A preservation contract: negative/null results are sha-anchored, kept in the
tree, and may never be rewritten into promotion language.

- `governance/NEGATIVE_EVIDENCE.yaml` · `scripts/ci/check_negative_evidence.py`
- `scripts/ci/check_revalidation_ledger.py` (post-hoc replay interlock).
