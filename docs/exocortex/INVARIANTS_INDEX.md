# Invariants Index

Authoritative source: [`.claude/physics/INVARIANTS.yaml`](../../.claude/physics/INVARIANTS.yaml).
This file is a derived overview; if it disagrees with the YAML, the YAML wins.

## Summary

| Total | P0 | P1 | P2 | Categories |
| ---: | ---: | ---: | ---: | ---: |
| **60** | 40 | 17 | 3 | 16 |

Regenerate this summary via `python .claude/physics/validate_tests.py --summary`
(see [`VALIDATION.md`](./VALIDATION.md)).

## By category

| Category | Theory doc | P0 | P1 | P2 | IDs |
| --- | --- | ---: | ---: | ---: | --- |
| **kuramoto** | [KURAMOTO_THEORY.md](../../.claude/physics/KURAMOTO_THEORY.md) | 3 | 3 | 1 | INV-K1 … INV-K7 |
| **explosive_sync** | [KURAMOTO_THEORY.md](../../.claude/physics/KURAMOTO_THEORY.md) | 1 | 1 | 0 | INV-ES1, INV-ES2 |
| **serotonin** | [SEROTONIN_THEORY.md](../../.claude/physics/SEROTONIN_THEORY.md) | 5 | 2 | 0 | INV-5HT1 … INV-5HT7 |
| **dopamine** | [DOPAMINE_THEORY.md](../../.claude/physics/DOPAMINE_THEORY.md) | 3 | 3 | 1 | INV-DA1 … INV-DA7 |
| **gaba** | [GABA_THEORY.md](../../.claude/physics/GABA_THEORY.md) | 3 | 2 | 0 | INV-GABA1 … INV-GABA5 |
| **free_energy** | — | 2 | 0 | 0 | INV-FE1, INV-FE2 |
| **thermodynamics** | — | 0 | 2 | 0 | INV-TH1, INV-TH2 |
| **ricci** | — | 1 | 1 | 1 | INV-RC1 … INV-RC3 |
| **kelly** | — | 2 | 1 | 0 | INV-KELLY1 … INV-KELLY3 |
| **oms** | — | 3 | 0 | 0 | INV-OMS1, INV-OMS2, INV-OMS3 |
| **signalbus** | — | 2 | 0 | 0 | INV-SB1, INV-SB2 |
| **hpc** | — | 2 | 0 | 0 | INV-HPC1, INV-HPC2 |
| **cryptobiosis** | [CRYPTOBIOSIS_THEORY.md](../../.claude/physics/CRYPTOBIOSIS_THEORY.md) | 6 | 2 | 0 | INV-CB1 … INV-CB8 |
| **lyapunov_exponent** | [LYAPUNOV_EXPONENT_THEORY.md](../../.claude/physics/LYAPUNOV_EXPONENT_THEORY.md) | 2 | 0 | 0 | INV-LE1, INV-LE2 |
| **spectral_gap** | — | 2 | 0 | 0 | INV-SG1, INV-SG2 |
| **ott_antonsen** | — | 3 | 0 | 0 | INV-OA1, INV-OA2, INV-OA3 |

## Parallel layer: `physics_contracts/`

The `.claude/physics/` registry above is the *theory-anchored* layer. A second,
*module-anchored* layer lives in
[`physics_contracts/catalog.yaml`](../../physics_contracts/catalog.yaml) and
currently contains **26 laws**. The two layers serve different purposes:

| Layer | Anchor | Audience | Test reference |
| --- | --- | --- | --- |
| `.claude/physics/INVARIANTS.yaml` | Physical theory (Kuramoto 1975, Ott-Antonsen 2008, …) | Theorists, reviewers | `INV-*` IDs in test docstrings |
| `physics_contracts/catalog.yaml` | Module of origin (`kuramoto.*`, `oms.*`, …) | Module owners, integrators | dotted IDs in test markers |

Both must stay in sync; mass-deleting either is forbidden (see
`feedback_geosync_physics_layers` in the contributor playbook).

## How to add a new invariant

1. Append the entry to `.claude/physics/INVARIANTS.yaml` with `id`, `type`,
   `statement`, `falsification`, `priority`, and (where relevant) `parameters`
   and `common_mistake`.
2. If the invariant is module-anchored, add the matching law to
   `physics_contracts/catalog.yaml` with the same numeric tolerance derivation.
3. Add at least one witness test that references the new `INV-*` ID.
4. Update this file's category row.
5. Re-run `python .claude/physics/validate_tests.py` and the `pytest` heavy
   gate to confirm the witness fires under falsification inputs.

A new invariant lands only when steps 1–5 are complete in the same PR.
