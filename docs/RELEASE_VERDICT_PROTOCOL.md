# Release Verdict Protocol

Status: executable release decision protocol.
Scope: GeoSync repository readiness.

## Verdict states

| Verdict | Meaning |
| --- | --- |
| PASS | The claim has a command, artifact, hash, and current commit binding. |
| FAIL | The check ran and produced a negative result. |
| BLOCKED | The check could not be completed or required evidence is absent. |

## Promotion states

| State | Required basis |
| --- | --- |
| STRUCTURAL | Static structure exists. |
| TESTED | Required tests and contract checks exist and execute. |
| EXTRAPOLATED | Evaluation reports survive walk-forward and null baselines. |
| ANCHORED | Repeated runs, operational rollback, and release evidence exist. |

## Release decision

A release verdict is generated from machine-readable claims. The protocol never promotes readiness from prose alone.

Required row shape:

```json
{
  "claim_id": "tests",
  "scope": "repository",
  "check_command": "python -m pytest -q",
  "expected_artifact": "results/production_readiness/READINESS_SUMMARY.json",
  "artifact_hash": "sha256:...",
  "commit_sha": "...",
  "verdict": "PASS"
}
```

## Required artifacts

- `results/production_readiness/READINESS_SUMMARY.json`
- `results/production_readiness/RELEASE_VERDICT.md`

## Required local command

```bash
python scripts/verify_production_readiness.py --write-results
```

For promotion enforcement:

```bash
python scripts/verify_production_readiness.py --write-results --enforce
```

## Operating rule

A release is complete only when every required row is PASS and the generated verdict binds to the current commit SHA.
