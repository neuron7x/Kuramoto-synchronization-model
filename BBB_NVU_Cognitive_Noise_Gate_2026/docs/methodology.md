# Methodology

## Problem

Detect and control CNS risk signals without converting noisy BBB/NVU proxies into hidden clinical claims.

## Falsifiable hypothesis

If deterministic BBB/NVU, neuroinflammatory, vascular-metabolic, glymphatic-sleep, and cognitive proxy thresholds are applied to normalized inputs, then convergent multi-domain stress should produce non-green control states. The hypothesis is falsified if frozen golden vectors, independent datasets, or domain-expert review show that the rule set repeatedly hides critical invalid data, misses boundary risks, or promotes unsupported clinical claims.

## Scientific frame

The blood-brain barrier is modeled as part of a dynamic neurovascular unit rather than a passive wall. The operational proxy model combines selective permeability, immune sensing, molecular export, vascular-metabolic support, sleep-linked clearance, and cognitive performance monitoring.

## Operational goals

| Goal | Metric |
| --- | --- |
| Detect | recall / sensitivity in validation mode |
| Gate | fail-closed rate |
| Explain | rule coverage |
| Control | human-review acceptance |
| Audit | hash-stable rerun |
| Adapt | drift-alert quality |
