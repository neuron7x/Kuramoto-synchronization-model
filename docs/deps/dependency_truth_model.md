# GeoSync dependency-truth model

Source-of-truth: [`tools/deps/validate_dependency_truth.py`](../../tools/deps/validate_dependency_truth.py)
Tests: [`tests/deps/test_validate_dependency_truth.py`](../../tests/deps/test_validate_dependency_truth.py)

## Why this exists

GeoSync maintains seven parallel dependency manifests:

```
pyproject.toml                  # canonical declared floor
requirements.txt                # runtime install (root + cortex_service Dockerfiles, l2-demo-gate.yml)
requirements-dev.txt            # extends requirements.txt with dev tools
requirements-scan.txt           # lightweight scan-only manifest
requirements.lock               # pinned production install (root Dockerfile, security-deep.yml)
requirements-dev.lock           # pinned dev install (security-deep.yml)
requirements-scan.lock          # pinned scan install
constraints/security.txt        # exact pins for security-critical packages
```

Each pair can drift in a different direction. The 2026-04-26 audit
identified two such drifts (F01: torch range; F03: strawberry-graphql
lock vs floor). The unifier mechanically detects every kind of drift the
audit found, plus four more.

## Six drift classes

| Class | Pattern | Example |
|---|---|---|
| **D1** | `pyproject` lower bound stricter than `requirements.txt` lower bound | `pyproject: torch>=2.11.0` vs `requirements.txt: torch>=2.1.0` (F01) |
| **D2** | Lockfile pin below the manifest floor | `requirements-scan.lock: fastapi==0.128.0` vs floor `>=0.135.3` |
| **D3** | Scan-path lockfile differs from runtime lockfile | `requirements.lock: aiodns==3.5.0` vs `requirements-scan.lock: aiodns==3.6.1` |
| **D4** | Dockerfile installs an unscanned manifest | `cortex_service/Dockerfile: pip install -r requirements.txt` while only `requirements.lock` is pip-audited |
| **D5** | `constraints/security.txt` weaker than the matching manifest floor | `constraints: pkg==1.0.0` while `pyproject: pkg>=2.0.0` |
| **D6** | Direct import of a transitively-declared package | (delegated to `deptry`) |

A drift is "scanned" only when a CI workflow passes the manifest to a
real security scanner (`pip-audit`, `safety`, `osv-scanner`, `trivy`,
`snyk`). Plain `pip install -r foo.txt` does NOT count as scanned.

## Output shape

The validator emits a deterministic JSON document with three top-level
sections plus the drifts list:

```json
{
  "drifts": [
    {
      "package": "torch",
      "drift_class": "D1",
      "detail": "requirements.txt floor 2.1.0 is below pyproject floor 2.11.0",
      "priority": "MEDIUM",
      "fix": "raise requirements.txt to match pyproject lower bound",
      "manifests": ["pyproject.toml", "requirements.txt"]
    }
  ],
  "install_paths_dockerfile": {
    "Dockerfile": ["requirements.lock"],
    "cortex_service/Dockerfile": ["requirements.txt"]
  },
  "install_paths_ci": {
    ".github/workflows/security-deep.yml": ["requirements.lock", "requirements-dev.lock"]
  },
  "accepted_backlog": ["fastapi", "prometheus-client", "pydantic", "requests", "streamlit", "uvicorn"]
}
```

`install_paths_dockerfile` and `install_paths_ci` are surfaced even when
no drift is reported, because that mapping itself is auditable evidence.

## Priority bands

| Priority | Trigger |
|---|---|
| **HIGH** | D2/D4/D5 (lockfile or deploy path admits a vulnerable version) |
| **MEDIUM** | D1 outside the accepted backlog; D3 (scan-vs-runtime divergence) |
| **MEDIUM** | D1 inside the accepted backlog (e.g. `fastapi`) — TRACKED, not BLESSED |
| **LOW** | D6 (deptry pointer; this validator does not duplicate deptry) |

There is no decimal score. Priorities are ordinal, by design.

## Accepted backlog

The validator carries a small set of known D1 drifts that the audit
identified as pre-existing. They are NOT silenced — they still appear
in the report — but they do not flip the validator's exit code.

Current backlog:

- `fastapi`           (pyproject>=0.135.3 vs requirements>=0.120.0)
- `prometheus-client` (pyproject>=0.25.0  vs requirements>=0.23.1)
- `pydantic`          (pyproject>=2.13.0  vs requirements>=2.12.4)
- `requests`          (pyproject>=2.33.0  vs requirements>=2.32.5)
- `streamlit`         (pyproject>=1.54.0  vs requirements>=1.31.0)
- `uvicorn`           (pyproject>=0.44.0  vs requirements>=0.37.0)

Adding to this list requires a comment with rationale and gets review
pushback. Removing from this list requires a focused PR that either
raises the requirements floor or documents why the gap is intentional.

## Running

```bash
# Report mode (always exits 0):
python tools/deps/validate_dependency_truth.py

# Gate mode (exits non-zero on actionable drift):
python tools/deps/validate_dependency_truth.py --exit-on-drift

# Persist report to disk:
python tools/deps/validate_dependency_truth.py --output reports/deps-truth.json
```

## What this does NOT do

- It does not install or resolve packages. It is a pure manifest-level
  structural check that runs in milliseconds.
- It does not replace `pip-audit` or `osv-scanner`. Those tools answer
  "is this version vulnerable?"; this tool answers "are our manifests
  consistent with each other and with the actual scan paths?".
- It does not handle wheel-platform differences. If `requirements.lock`
  pins different wheels for different OSes, the unifier sees only the
  rendered text.
- It does not call `deptry`; the D6 entry is a static pointer that the
  user should run deptry to cover that axis.

## Regression cases

`tests/deps/test_validate_dependency_truth.py` proves:

- F01 (torch) reports zero drifts in the live tree (closure regression test)
- F03 (strawberry-graphql) reports zero drifts in the live tree
- Each of D1/D2/D3/D4/D5/D6 is mechanically detectable on a synthetic
  tree planted with the exact pattern
- A workflow that runs `pip-audit` against a manifest is correctly
  treated as "scanned" — D4 does NOT fire
- The `--exit-on-drift` flag exits non-zero when an actionable D1 is
  planted on a NEW (non-backlog) package
- The JSON output is deterministic when the input is stable

## Origin

Same arc as the rest of the calibration layer:

- F01 trap: range drift was conflated with active vulnerable install.
- F03 trap: lockfile pin was conflated with reachable exploit.

The unifier's job is to make the *manifest-level* facts visible without
tipping into either conflation. The reachability question lives in
`tools/security/reachability_graph.py`. The exploitability question
lives in `pip-audit`. This tool answers only the question it is
qualified to answer: do our manifests agree?
