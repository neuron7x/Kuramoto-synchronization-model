# Claim-driven audit engine — roadmap steps 2 + 3 (2026-07-22)

`geosync/proof/audit.py` + `python -m geosync.proof.audit` closes gaps 2 (claim-driven proof)
and 3 (unified auditor CLI) of the proof-kernel elevation roadmap. An external auditor runs ONE
command and gets a machine-readable verdict on EVERY claim in `docs/CLAIMS.yaml` — **without
trusting the author**. Designed + adversarially hardened by a 10-agent orchestrated workflow
(3 scouts → 3 judged design drafts → 3 skeptics), then integrated + re-verified here.

## What it does (honesty core)
- Re-derives every input from repo bytes: parses `docs/CLAIMS.yaml`, parses the banned-phrase
  firewall LIVE from `FORBIDDEN_CLAIMS.md` (never hardcoded), and itself COLLECTS then RUNS each
  `falsifier.test_id`. It never reads an author-produced verdict for outcomes.
- Cross-checks the subprocess return code against a `--junitxml` outcome (NEVER rc alone), so a
  green exit cannot launder a skipped/errored/empty run into support.
- Per-claim verdict — deterministic first-match over five values: `FORBIDDEN_LANGUAGE`
  (banned status phrase) / `REFUTED` (falsifier fired — loudest signal, never hidden) /
  `DANGLING` (named but cannot be collected/run — a test that cannot fail) / `NOT_TESTED`
  (admissible-by-design absence) / `SUPPORTED` (rc 0 AND junit 'passed').
- Aggregate = weakest-link: any REJECT-class → REJECT; else PARTIAL if any NOT_TESTED; else
  ACCEPT. Exit 1 iff REJECT (`--strict` also fails PARTIAL for release signoff).
- Report `artifacts/geosync_proof/audit.json` is **provenance-bound + tamper-evident** — reuses
  `geosync/proof/run.py` helpers verbatim (`code_version=git:<sha>`, `dataset_sha256`,
  `content_digest`). `--verify <report>` recomputes the digest + re-hashes the pinned
  policy/claims files: an external party trusts the bytes on disk, not the author.

## Modes
- `--resolve-only` — fast static tier (CI `claim-audit-resolve` job, fail-closed): collect every
  falsifier + scan banned language in seconds; catches DANGLING + FORBIDDEN_LANGUAGE.
- default — execute every RESOLVED non-heavy falsifier (earns SUPPORTED/REFUTED); heavy-marked
  nodes parked NOT_TESTED.
- `--deep` — execute everything (nightly lane).

## Verification (this integration)
- 29/29 teeth pass (25 fast dependency-injected + 4 real e2e: a genuine REFUTED, a SUPPORTED
  positive control, the real CLI). `--resolve-only` over the live 27 claims → aggregate PARTIAL,
  **0 DANGLING** (every falsifier resolves — consistent with `check_falsifier_nodes` green).
- **Determinism fixed post-workflow:** the draft recorded per-node `time.monotonic()` durations
  in the digested report — ambient nondeterminism (tripped `check_code_hygiene`) AND it made the
  "tamper-evident deterministic" artifact non-reproducible (digest changed run-to-run). Removed
  timing entirely; two resolve-only runs now yield an identical `content_digest`; hygiene GREEN.
- `--verify`: OK on a fresh report (exit 0), TAMPERED (exit 1) on a one-byte edit.
- Wired into CI (`claim-audit-resolve`, fail-closed). ruff + mypy clean.

Remaining roadmap: step 4 (promotion lifecycle HYPOTHESIS→ANCHORED→RETIRED, RES-020), step 5
(packaging/external-reviewer packet). Stated open, not claimed done.
