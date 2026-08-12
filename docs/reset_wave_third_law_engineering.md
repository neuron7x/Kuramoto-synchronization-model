# Third-law engineering interpretation for reset-wave

## FACT
The numerical model is finite-step relaxation on a phase manifold.
Exact zero computational noise is not guaranteed nor required for stable operation.

## ENGINEERING RULE
Use a **residual potential floor** (`residual_potential_floor >= 0`) as a controlled lower bound proxy for residual fluctuations.

- If floor is positive, solver targets asymptotic ordering with nonzero residual activity.
- This avoids brittle "perfect stillness" configurations and preserves adaptive responsiveness.

## IMPLEMENTED CONTRACT
- Config field: `residual_potential_floor`
- Validation: negative floor is rejected
- Convergence condition includes both:
  - phase error tolerance,
  - potential floor criterion.

## FALSIFIABLE CHECKS
1. Negative floor must raise error.
2. For nontrivial initial phase mismatch and positive floor, final potential remains nonzero in practical runs.
