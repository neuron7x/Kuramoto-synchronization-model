# Calibration

This file defines control thresholds for delivery decisions.

## Rule

A state can move forward only when the current artifact is inspectable and the required checks are complete.

## Thresholds

1. Freshness: the branch must not be behind the current main line.
2. Observer: workflow runs and jobs are the source of truth.
3. Unknown: missing or pending checks stop the decision.
4. Required checks: every required check must finish with success.
5. Scope: documentation changes must stay in documentation paths.
6. Drift: stale evidence is discarded after main moves.
7. Decision: merge is allowed only after the above thresholds hold together.
