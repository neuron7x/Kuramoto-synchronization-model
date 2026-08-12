# README Claim Surfaces

Date: 2026-05-29

This document defines allowed surfaces for user-facing README statements.

## Surface 1: Verified kernel

Allowed:

- invariant registry counts;
- strict witness files;
- TLA+ model-checking status;
- CI gates with blocking behavior;
- links to claim boundaries and retired statements.

Required:

- source file;
- test or formal model;
- workflow or validator;
- ledger row.

## Surface 2: Measured experiments

Allowed:

- reproducible experiment outputs;
- signed artifacts;
- declared seeds and hashes;
- uncertainty intervals;
- explicit baselines and null comparisons.

Required:

- machine-readable result artifact;
- data provenance;
- exact command or CI job;
- claim tier in `CLAIMS.md`.

## Surface 3: Hypothesis sandbox

Allowed:

- falsifiable hypotheses;
- preregistered experiment plans;
- non-promoting diagrams;
- recovery paths for retired statements.

Required:

- label as HYPOTHESIS, PREREGISTERED, RETIRED, or NOT_RUN;
- no headline promotion without accepted evidence.

## Promotion rule

A README statement may be promoted only when it has an active `CLAIMS.md` row, a verifiable artifact, a comparison surface, validator acceptance, and an explicit boundary statement.
