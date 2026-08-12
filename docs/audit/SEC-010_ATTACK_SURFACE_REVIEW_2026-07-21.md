# SEC-010 — Attack-surface review (API / CLI / filesystem) 2026-07-21

Enumeration of every externally- or operator-reachable entry point into GeoSync, with the
trust boundary and residual risk of each. This is a **research-verification** system with the
live-capital/production path frozen (OPS-001), so "external" here means: an operator running
the CLI/gates, a file the process reads, and the (currently minimal) HTTP API — not an
internet-exposed trading endpoint.

## 1. Console entry points (14) — `[project.scripts]` in pyproject.toml
`geosync-scripts`, `geosync-release-gate`, `geosync-import-architecture`, `geosync-pai`,
`geosync-sync`, `geosync-db`, `geosync-server`, `tp-kuramoto`, `geosync-research`, `mfn`,
`mfn-api`, `mfn-validate`, plus 2 module mains. **Trust boundary:** operator-invoked, local.
**Residual:** args are argparse-typed; no shell interpolation of args found. LOW.

## 2. HTTP API — `application/api/` (3 route-bearing modules)
Route handlers gated by `application/api/authorization.py`, `rate_limit.py`, `idempotency.py`.
`geosync-server` / `mfn-api` expose it. **Trust boundary:** the only network surface.
**Residual:** authorization + rate-limit + idempotency middleware present; not internet-exposed
by default. MEDIUM — a deployment decision, tracked under OPS/SEC-013 (container hardening).

## 3. Subprocess surface (77 files) — mostly list-argv, but **2 real `shell=True` sites**
Most gates/CLIs shell out to `pytest`/`git`/`pip` via `subprocess.run([...])` (list argv, no
interpolation). `os.system`: 0 in first-party. `eval()`/`exec()` on untrusted input: 0 (the one
`exec(` is a method named `exec` in `geosync/cli/geosync_cli.py:973`). **Correction (independent
review caught my first draft's false "no shell=True" claim):** there ARE 2 first-party
`shell=True` sites, both executing a **command STRING from committed config**:
- `tools/commit_acceptor/run_evidence.py:143` — runs the acceptor-YAML `command` via
  `subprocess.run(command, shell=True)` (documented `# nosec B602`, "trusts maintainer-committed
  acceptor YAML").
- `scripts/ci/run_rust_accel_contract.py:167` — runs `criterion.command` via `shell=True`.
**Trust boundary:** repo-commit access — a malicious *committed* config file could run arbitrary
shell. Not a runtime/external-input injection (the strings are not user-supplied at run time), but
it collapses "config" and "code" trust levels. **Residual: MEDIUM** — mitigated only by code-review
of `acceptor` / `criterion` YAML; remediation = allow-list the command verbs or drop `shell=True`
for a list argv. Tracked as a SEC-016 follow-up.

## 4. Deserialization surface — smaller than first assessed (already hardened)
- `yaml.load(` unsafe: **0** — every YAML read is `safe_load`. GOOD.
- `pickle`: **3 first-party sites, and the loads are guarded** (independent review corrected my
  overstatement): `runtime/recovery_agent.py:183` and `core/indicators/cache.py:438` both load via
  a **RestrictedUnpickler / _SafeUnpickler** whose `find_class` admits only primitive types and
  raises `UnpicklingError` otherwise — a tampered blob cannot instantiate arbitrary classes;
  `core/neuro/training.py:581` is **dump-side** only. So this is NOT plain `pickle.load` code-exec.
  **Residual: LOW** (already the recommended hardening). A defense-in-depth HMAC integrity tag on
  the blobs remains a nice-to-have SEC-016 follow-up, not a live hole.

## 5. Filesystem write surface (51 sites: core 28, runtime 11, execution 6, geosync 5, application 1)
Writes are to artifact/cache/state paths; the manifest + inventory + artifact-freshness gates
already detect tampering of the tracked/generated tree. **Residual:** LOW for tracked outputs;
the pickle state-files (§4) are the exception.

## Verdict
Attack surface is **small and mostly hardened**: no unsafe yaml, no os.system, no eval on
untrusted input, guarded (restricted-unpickler) pickle loads, auth+rate-limit on the HTTP surface.
**The one actionable residual is the subprocess surface:** 2 first-party `shell=True` sites execute
command strings from committed config (repo-commit trust boundary) — remediation (allow-list verbs
or drop `shell=True`) filed as a SEC-016 follow-up. This document is the SEC-010 evidence artifact;
the `shell=True` surface and the correct (hardened) pickle characterization are both stated —
including that an independent review corrected an earlier draft that had wrongly claimed zero
`shell=True` and overstated the pickle risk. The audit's own error being caught and recorded is
the two-signature discipline working.
