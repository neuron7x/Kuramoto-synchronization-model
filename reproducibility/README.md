# Reproducibility Package

**One command reproduces every canonical artefact of the formal-verification + CNS ontology surface.**

```bash
docker build -t geosync-repro -f reproducibility/Dockerfile .
docker run --rm geosync-repro
```

Exit 0 ⟺ every artefact matches its pinned sha256 and TLC reports no invariant violation.

## What the reproduction covers

| Step | Artefact | Verdict if drift |
|------|----------|------------------|
| 1 | CNS control ontology + stream registry + schema | guard exits non-zero, ``make lint-python`` would fail |
| 2 | TLA⁺ admission-gate model check | TLC counterexample trace printed, non-zero exit |
| 3 | ``manifest.sha256`` — pinned hashes of 6 canonical files | specific line shows ``FAILED`` |

## Why this package exists

Numbers scattered across documentation are weak evidence. The repository's
operator-facing surface should be able to say **"here is exactly what I
claim, here is exactly how to reproduce it, here is exactly what counts
as drift"** — not "run pytest and trust". A third party pulling this
repo should be able to `docker run` and witness the same three greens
we see on our laptop.

Reproducibility is the axis that graduates a solid industry codebase
into a research artefact.

## Manifest update policy

Any PR that modifies one of the pinned files MUST include the new sha256
in ``manifest.sha256``. The sha256s for the current main are:

```
$ cat reproducibility/manifest.sha256
```

## Troubleshooting

* **TLC exits with a counterexample.** Read the trace: TLC prints the
  state sequence leading to the invariant violation. Fix the spec or
  the code — whichever drifted.
* **``manifest.sha256`` mismatch.** Either a tracked file changed
  legitimately (update the manifest in the same PR) or an attacker
  modified it (investigate).
* **Docker build fails on TLC download.** The Dockerfile pulls from the
  official TLA⁺ release. For hermetic offline builds, download
  ``tla2tools.jar`` separately and pass via build-arg.

## Contract

* The image **never** reaches the network at runtime.
* The reproduction script **never** reads from outside the repo tree.
* Every invariant in this package is checked **without randomness**
  — the expected state-space size (``853 / 547 distinct``) is pinned
  along with the hashes.
