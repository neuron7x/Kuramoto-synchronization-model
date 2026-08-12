# RIP — Engineering Graveyard

A sober memorial register of dead hypotheses and engineering failures in
GeoSync's Kuramoto / Sakaguchi inverse-problem stack, with a sharply
separated block (`HONORS.md`) for the genuinely defensible
engineering / methodological results.

This is a technical register. The only levity is the word "RIP". Every
tombstone is sha-anchored and falsifiable. Where success was literally
zero, it says so in plain words: **успіх: 0**.

## The governing postulate

> **A positive result is a negative one not yet falsified. The negative
> artifact is the conserved asset; this directory is where they are
> honored, not hidden.**

This is stated as an *engineering principle*, not a scientific law. It
is the operating reason this directory exists: a falsified hypothesis
that is recorded, sha-pinned and reusable is worth more than an
unfalsified claim with no boundary. The graveyard conserves the
information content of every kill.

## Why this directory exists

The CALIB-GRID lineage ran an external-ground-truth calibration of the
Kuramoto coupling estimator against a *proven* reference (WSCC-9 swing
model, Dörfler–Bullo critical coupling). The honest outcome was a chain
of `NEGATIVE` artifacts. Those artifacts are the deliverable. Without a
register they decay into folklore, get silently re-attempted, or — worse
— get read as ground truth when a *later* lineage has already falsified
their causal attribution.

`RIP/` makes the conservation explicit:

- `README.md` — this file: the postulate and the contract.
- `TOMBSTONES.md` — one canonical entry per dead hypothesis / failure.
- `manifest.yaml` — machine-readable mirror of the tombstones.
- `HONORS.md` — sharply separated, admissibility-honest, no promotion
  language: only the defensible engineering / methodological wins.

## Non-interference contract (by design, inert)

`RIP/` interferes with **nothing**. This is a hard invariant, not an
aspiration:

- **Zero Python.** No `.py` file anywhere under `RIP/`. Nothing to
  lint, type-check or import.
- **Zero imports.** No module, test, build step or runtime path
  references `RIP/`.
- **Not collected by pytest.** `pytest.ini` `testpaths` is
  `tests, core/neuro/tests`; `RIP/` is outside both. `pytest
  --collect-only` is byte-for-byte unchanged by this directory.
- **Zero behavior change.** No frozen sha-pinned calibration artifact is
  edited, recomputed or rewritten. `tests/research/calibration/
  test_grid_kuramoto.py` is untouched; every drift / no-peek /
  bit-stability / forcing-function test stays green unmodified.
- **Markdown + one manifest YAML only.** `manifest.yaml` is a passive
  data mirror, loaded by no code path in the repository.

If any future change would make `RIP/` interfere with the system, the
correct action is to revert that change, not to weaken this contract.

## What this directory is NOT

It is not a changelog, not a roadmap, not a results dashboard, and not a
place where failures are softened into "learnings". A tombstone records
what was claimed, what killed it, and the exact metric + procedure of
the kill. The supersession discipline is append-only: a falsified causal
attribution is superseded **forward**, never edited in place. The
historical record stays honest as written.
