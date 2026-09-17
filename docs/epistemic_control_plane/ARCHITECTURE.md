# Architecture

```text
Research Plane
  hypothesis / code / experiments / analysis
                 |
                 v
Epistemic Control Plane
  Claim -> Contract -> Evidence -> Falsifier -> Oracle Independence
        -> Negative Evidence -> Admission -> Certificate
                 |
           +-----+------+
           |            |
        PROMOTE        HOLD
           |            |
           +------ FALSIFY (future explicit adjudication path)
```

The critical separation is authority: research agents may propose evidence but do not directly mutate claim maturity.
