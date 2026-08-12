<!-- SPDX-License-Identifier: MIT -->
# Scan Toolchain Policy (SEC-002)

**Gate:** `G-SCAN-TOOLCHAIN` — `scripts/ci/check_scan_toolchain.py`
**Receipt:** `artifacts/security/scan_toolchain_receipt.json`
**Tests:** `tests/ci/test_scan_toolchain.py`
**Lock:** `requirements-scan.lock`

## Why

A vulnerability scan is only as trustworthy as the scanner. If `pip-audit` is
resolved **latest-at-runtime** (an unpinned `pip-audit` line, a `pip-audit>=x`
range, or absent from the lock), the audit result is unreproducible and an
attacker — or a broken index — can silently swap the auditor for one that
reports clean. SEC-002 pins the **scan toolchain itself**.

## Contract

1. **Pinned + hashed scanner.** `requirements-scan.lock` MUST pin `pip-audit`
   (and `pip`) to an **exact `==` version** carrying at least one well-formed
   `--hash=sha256:<64-hex>` entry. Currently `pip-audit==2.10.1`. An unpinned /
   range / hash-less scanner line is a **HARD, fail-closed** failure.
   `pip-audit==2.10.1` is the same version pinned in `requirements-dev.txt`, so
   the auditor is identical across the dev and scan environments.

2. **No false GREEN.** A scan **run** that could not actually reach the advisory
   database — offline, unreachable DB, a non-zero/absent auditor exit code, an
   error string, or simply no evidence the network was reached — MUST NOT be
   classified GREEN. `classify_scan_outcome` fails closed to **RED** (or
   **MANUAL** when a run is explicitly flagged `requires_manual`). A record that
   *claims* `status: GREEN` while the evidence says otherwise is flagged by
   `is_false_green`. The claimed status is deliberately ignored — the verdict is
   computed from evidence, so a lying record cannot pass.

   `GREEN` is returned **only** when: `online is True` **and** `db_reachable`
   is not `False` **and** `exit_code == 0` **and** no `error` **and**
   `vulnerabilities_found == 0`.

## How the scanner enters the lock

`pip-audit` is not a dependency of the scanned application, so `pip-compile`
does not emit it from `requirements-scan.txt`. It is added as a **curated
addendum** (an extra `pip-audit==2.10.1` input) during regeneration and receives
`--hash` entries like everything else. The scan lock is regenerated with
`--allow-unsafe` (pins the `pip`/`setuptools` backends) and constrained to
`requirements.lock` so the scan environment can never drift below the deploy
floors. See `docs/DEPENDENCY_LOCK_POLICY.md` for the regeneration recipe and the
no-drift discipline.

## Verification (CI)

```bash
python scripts/ci/check_scan_toolchain.py \
    --emit-receipt artifacts/security/scan_toolchain_receipt.json
python -m pytest tests/ci/test_scan_toolchain.py -q
```

The gate is **verify-only**: it never regenerates the lock and never runs
pip-audit. It reads the committed scan lock, asserts the scanner is pinned +
hashed, and records the scanner version and sha256 digests in the receipt.

## Receipt schema (`scan_toolchain_receipt/v1`)

| Field | Meaning |
|-------|---------|
| `pinned_tools.pip-audit.version` | exact pinned scanner version (`2.10.1`) |
| `pinned_tools.pip-audit.sha256` | sorted sha256 digests of the pinned wheel(s)/sdist |
| `pinned_tools.*.exact_pin` / `hashed` | fail-closed booleans per required tool |
| `offline_policy` | the no-false-GREEN rule (see contract §2) |
| `ok` / `errors` | overall verdict and any fail-closed findings |
