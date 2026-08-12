# RIEE Production Runbook (2026-05-26)

Single-command production readiness gate for the full fail-closed stack.

## Command
```bash
python scripts/production_readiness_riee.py
```

## Included checks
1. Epistemic drift parity.
2. Financial DFV-EP validation.
3. Claim graph regeneration.
4. Claim hash integrity verification.
5. Guard-surface completeness.
6. RIEE runtime test suite.

## Pass criterion
All checks return `0`; first failure hard-stops the run.
