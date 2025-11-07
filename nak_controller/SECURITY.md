# SECURITY

## Invariants & Safety Gates
- Hard clamps on state and outputs (bounds in config).
- RED mode enforces `risk_mult=0` or `suspend=True`.
- Rate‑limit on risk prevents abrupt leverage changes.
- Hysteresis avoids rapid toggle between suspended/active.

## Operational Recommendations
- Keep config under version control; review diffs.
- Audit logs: persist `EI,E,L,mode,risk_factor` per step for 7‑year trail.
- CI: block merge on test/mypy failures.
- Secrets: polygon/coingecko API keys must **not** be committed.
