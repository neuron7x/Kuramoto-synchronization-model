<!--
Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
SPDX-License-Identifier: MIT
-->
# Secret & Sensitive-Data Boundary Policy (SEC-006)

## Purpose

A repository has a **secret boundary** only if it can be *mechanically proven*
that no live credential has crossed it into the committable tree — and that the
prover itself has **teeth** (a planted fake credential is actually detected).

This policy defines that boundary and is enforced by the fail-closed gate
`scripts/ci/check_secret_boundary.py` (tests in
`tests/ci/test_secret_boundary.py`, machine-readable evidence in
`artifacts/security/secret_audit.json`).

## Invariants (fail-closed)

The gate enforces four independent invariants; violating any one exits non-zero:

1. **NO HIGH-CONFIDENCE SECRET** — after subtracting the documented allowlist of
   placeholder / fixture / baseline surfaces (below), the scanner finds **zero**
   credentials in the working tree.
2. **ENV EXAMPLE IS PLACEHOLDER-ONLY** — `.env.example` carries no real-looking
   value; every credential slot is a visible placeholder
   (`your_..._here`, `change_me...`, `<...>`, `${...}`, …).
3. **SCANNER HAS TEETH** — a negative fixture (a planted fake, **non-example**
   AWS access key + a PEM `PRIVATE KEY` block) is **detected** by the same scan
   path. A scanner that cannot catch a planted secret cannot vouch for a clean
   tree, so failure here fails the gate.
4. **NO SECRET IN THE AUDIT ARTIFACT** — findings record only path + rule + a
   redacted match (or a non-reversible `sha256:` fingerprint). A raw secret value
   is never printed, persisted, or committed.

## Scanner

* **Preferred:** the `gitleaks` binary with the repo's own `.gitleaks.toml`
  (mature ruleset; the repo's `.gitleaksignore` allowlist is honored by gitleaks
  itself). Invoked as `gitleaks detect --no-git --redact`.
* **Fallback** (when the binary is absent): a focused, high-signal regex scan —
  AWS access keys, PEM private-key blocks, bearer tokens, and
  `api_key=` / `secret=` / `password=` assignments with real-looking values.
  The fallback is deliberately conservative and skips placeholder values.

The gate restricts findings to the **committable** tree: paths that `git`
ignores (`__pycache__` bytecode, caches, a local `.env`) are out of scope. This
also prevents the gate from flagging its own `.pyc` — the Python compiler
constant-folds the negative fixture's split fragments back into an intact PEM
header inside bytecode.

## Allowlist (by surface root)

The following surfaces are **trusted to contain only placeholder or
planted-fake tokens** and are excluded from the high-confidence set:

| Surface root                       | Why it is allowlisted                                   |
|------------------------------------|---------------------------------------------------------|
| `.github/detect-secrets.baseline`  | detect-secrets' own hashed baseline (one-way digests).  |
| `docs/`                            | Documentation examples (`api.geosync.example`, redacted headers). |
| `tests/`                           | Test fixtures — planted fakes for the security suites.  |
| `scripts/eval/fixtures/`           | Red-team fixtures (deliberately fake credentials).      |

A credential found in **any other path** (application, runtime, `configs/`,
`core/`, a stray `.env`) is high-confidence and fails the gate. This is where a
real leak would land, and the gate has full teeth there.

## `.env.example` contract

`.env.example` is the committed template; the real `.env` is git-ignored and
never committed. Every value in `.env.example` MUST be a placeholder. One-way
hashes shipped as demo defaults (e.g. a bcrypt `DASHBOARD_ADMIN_PASSWORD_HASH`)
are surfaced as **advisories** (not live credentials, but prefer a placeholder);
any value that trips the secret scanner is a **blocking** leak.

## Running the gate

```bash
python scripts/ci/check_secret_boundary.py        # full gate; writes secret_audit.json
python scripts/ci/check_secret_boundary.py --self-test   # negative-fixture teeth check only
python scripts/ci/check_secret_boundary.py --target PATH  # scan an arbitrary path, no allowlist
python -m pytest tests/ci/test_secret_boundary.py -q
```

Exit codes: `0` clean · `1` secret found / real value in `.env.example` /
negative fixture not detected · `2` required file or tooling missing.

## If a real credential is found

Do **not** commit it. Record it **redacted** (path + type + `sha256:` fingerprint)
and **flag it for rotation** — a secret that reached the working tree must be
considered compromised and rotated at its source of truth, not merely deleted
from the file.

## Residuals (honest scope)

* **Git history is not scanned** (`--no-git`). A credential that existed only in a
  rewritten past commit, the reflog, or packed objects would be missed. For
  deep-history coverage run `gitleaks detect` in git mode on a full clone.
* **Allowlisted surfaces are trusted, not deep-verified.** A real secret committed
  into `docs/`, `tests/`, `scripts/eval/fixtures/`, or the detect-secrets baseline
  would be allowlisted. The teeth are on every other path.
* **Bundles / `.pack` files are not present** and are not deep-inspected.
