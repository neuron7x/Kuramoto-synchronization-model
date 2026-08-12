# Negative Results

`HYPOTHESIS_NOT_SUPPORTED` is a successful falsification outcome, not a pipeline failure.

The result must be preserved in:

- `artifact.json`
- evidence bundle
- `CLAIMS.md`

A signal is supported only when:

```text
p_value < 0.01 AND abs(cliffs_delta) >= 0.147
```

Anything weaker remains T3 exploratory evidence. This protects the repo from the ancient human ritual of discovering alpha by staring at a noisy plot until it apologizes.
