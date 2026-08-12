# 10 — Artifact Reproducibility Package

Copy-paste executable steps to reproduce the governance evidence from a clean
checkout. Target readiness: ACM *Artifacts Evaluated — Functional* (documented,
consistent, complete, exercisable, evidence-bound). No market result is
reproduced — none is claimed.

## Environment setup

```bash
git clone https://github.com/neuron7xLab/GeoSync.git
cd GeoSync
python -m venv .venv && . .venv/bin/activate
python -m pip install --upgrade pip build wheel setuptools setuptools_scm
python -m pip install -e ".[dev]"
```

## Build + clean-room install

```bash
# clean-room wheel (immune to stale build/ cache)
python -m build --wheel
python -m venv /tmp/geosync-clean && /tmp/geosync-clean/bin/python -m pip install dist/*.whl
/tmp/geosync-clean/bin/python -c "import geosync; print('import geosync OK')"
```

## Run the governance gates

```bash
python scripts/ci/check_wheel_contract.py            # ratchet (PASS); writes artifacts/wheel_contract.json
python scripts/ci/check_wheel_contract.py --strict   # target verdict (FAIL — B.wheel=0 NOT achieved)
python scripts/ci/check_package_boundary.py          # package ratchet (PASS at 13)
python scripts/ci/check_import_architecture.py       # import ratchet (PASS, no new debt)
python scripts/ci/check_falsifier_ledger.py          # 6/6 falsifiers resolve
python scripts/ci/check_claim_boundary.py            # no unreviewed product-category claim
python scripts/ci/check_phd_traceability.py          # every chapter bound; writes artifacts/phd_traceability.json
```

## Inspect the evidence artifacts

```bash
python -c "import json;d=json.load(open('artifacts/wheel_contract.json'));print(d['verdict'], len(d['non_geosync_packages']),'pkgs', len(d['import_failures']),'debt')"
cat artifacts/import_graph/tp_kuramoto.json     | python -m json.tool | head
cat artifacts/import_graph/geosync_server.json  | python -m json.tool | head
cat artifacts/phd_traceability.json             | python -m json.tool | head
```

## Reproduce the PR evidence table

The dissertation artifact table is in `docs/phd/03_evidence_matrix.md`; the
governance PRs are #1302 (gates + drains + wrapper-first), #1303 (laziness
invariant), #1304 (dissertation layer 00–05). Each is verifiable via:

```bash
gh pr view <N> --repo neuron7xLab/GeoSync --json state,mergeCommit
gh api repos/neuron7xLab/GeoSync/commits/<HEAD_SHA>/check-runs \
  --jq '.check_runs | group_by(.conclusion) | map({c:.[0].conclusion,n:length})'
```

## Expected outcomes (admissibility, not empirical truth)

- `import geosync` succeeds in a clean venv.
- `check_wheel_contract.py` ratchet → PASS; `--strict` → FAIL (honest: 13
  packages, 70 import debt remain).
- All ratchets hold; `check_phd_traceability.py` → PASS.
- **No** market, profitability, or B.wheel=0 outcome is produced or claimed.
