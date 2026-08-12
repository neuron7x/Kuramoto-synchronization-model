# PR financial valuation method (objective / auditable)

## Verified industry frameworks used
1. **Cost-of-effort model (LOC -> hours -> money)**
   Transparent baseline for implementation valuation.
2. **Scenario analysis**
   Low / mid / high market-rate envelopes to avoid single-point bias.
3. **Risk multiplier**
   Captures uncertainty premium for R&D/system-critical changes.

## Local reproducible tool
Run:

```bash
python tools/pr_value_estimator.py
```

Output:
- `reports/pr_value_estimate.json`

## What the numbers mean
- Not market cap or company valuation.
- Not guaranteed revenue.
- Engineering replacement-cost estimate for implemented PR scope.
