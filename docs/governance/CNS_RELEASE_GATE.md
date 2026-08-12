# CNS Release Gate

## Claim boundary

This component is a deterministic release-readiness gate for CNS governance artifacts. It does not claim biological validity, therapeutic effect, trading performance, or production profitability.

## Production claim

GeoSync can build and verify a CNS release evidence bundle containing protocol validation, manifest hashes, report-contract status, and a weighted quality verdict.

## Falsification condition

The claim is falsified if any of the following occurs on a clean checkout:

1. `python tools/cns_program/deploy_release_gate.py` exits non-zero.
2. `python tools/cns_program/build_release_manifest.py` cannot create the manifest.
3. `python tools/cns_program/verify_release_manifest.py` fails on the freshly generated manifest.
4. `python tools/cns_program/quality_gate.py` returns `passed: false`.

## One-command local gate

```bash
python tools/cns_program/deploy_release_gate.py && \
python tools/cns_program/build_release_manifest.py && \
python tools/cns_program/verify_release_manifest.py && \
python tools/cns_program/verify_reports_contract.py && \
python tools/cns_program/quality_gate.py && \
python -m pytest -q tests/cns_program
```

## Evidence artifacts

- `results/cns_deploy_gate.json`
- `results/cns_release_manifest.json`
- `results/cns_manifest_verification.json`
- `results/cns_reports_contract.json`
- `results/cns_quality_gate.json`

## Proof boundary

The generated JSON files are transient evidence for the current checkout. They are not permanent truth, not a release certificate, and not a substitute for rerunning the gate after any relevant source change.

## Merge policy

Merge is valid only when the GitHub Actions CNS Release Gate is green on Python 3.11 and 3.12.
