# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the HPC seeded-reproducibility law in the catalog.

Binds the catalog law ``hpc.seeded_reproducibility`` to an executable ``@law``
witness, citing the EXISTING registry invariant INV-HPC1 (no new invariant, no
count change):

* ``hpc.seeded_reproducibility`` — a seeded kernel returns bit-identical output
  for identical inputs: kernel(seed, x) == kernel(seed, x) bit-for-bit
  (INV-HPC1). Witnessed on ``geosync_hpc.indexed_rng.IndexedRNG``.

The seeded kernel here is the content-addressable ``IndexedRNG``: each draw is a
pure function of (seed, stream_id, event_id, event_index), so reproducibility is
stronger than mere replay determinism — it is order-independent. The witness
proves three facts: (1) identical coordinates give bit-identical draws across
fresh instances; (2) a different seed perturbs the stream; (3) the draw depends
on the event coordinate, not on call order (content-addressability).

Nothing here is a market claim — these are determinism-kernel contract facts.
"""

from __future__ import annotations

import numpy as np

from geosync_hpc.indexed_rng import IndexedRNG
from physics_contracts.law import law

N_DRAWS = 1000
SEED = 42
ALT_SEED = 43
STREAM = "witness-stream"
EVENT = "evt"


@law("hpc.seeded_reproducibility", n_draws=N_DRAWS, seed=SEED)
def test_indexed_rng_is_bit_identical_and_content_addressable() -> None:
    """INV-HPC1: identical (seed, stream, event, index) ⇒ bit-identical draw.

    Draws the same coordinate stream from two fresh IndexedRNG instances and
    requires every value to match bit-for-bit. A different seed must perturb at
    least one draw (the kernel actually depends on the seed), and replaying the
    coordinates in reverse order must reproduce the same per-coordinate values
    (content-addressability: the draw is a pure function of its coordinate).
    """
    n_draws = N_DRAWS
    first = IndexedRNG(seed=SEED, stream_id=STREAM)
    second = IndexedRNG(seed=SEED, stream_id=STREAM)
    forward = np.array([first.normal(EVENT, i) for i in range(n_draws)])
    replay = np.array([second.normal(EVENT, i) for i in range(n_draws)])

    altered = IndexedRNG(seed=ALT_SEED, stream_id=STREAM)
    altered_draws = np.array([altered.normal(EVENT, i) for i in range(n_draws)])

    reverse_engine = IndexedRNG(seed=SEED, stream_id=STREAM)
    reverse_map = {i: reverse_engine.normal(EVENT, i) for i in reversed(range(n_draws))}
    reverse_ordered = np.array([reverse_map[i] for i in range(n_draws)])

    assert bool(np.all(forward == replay)), (
        "INV-HPC1 violated: observed mismatched draws between identical instances = "
        f"{int(np.sum(forward != replay))} must be 0 over n_draws={n_draws} "
        f"with seed={SEED}; identical coordinates must give bit-identical output"
    )
    assert bool(np.any(forward != altered_draws)), (
        "INV-HPC1 violated: observed seed-sensitivity count = "
        f"{int(np.sum(forward != altered_draws))} must be > 0 over n_draws={n_draws} "
        f"with seed={SEED}; a different seed must perturb the stream"
    )
    assert bool(np.all(forward == reverse_ordered)), (
        "INV-HPC1 violated: observed order-dependence count = "
        f"{int(np.sum(forward != reverse_ordered))} must be 0 over n_draws={n_draws} "
        f"with seed={SEED}; the draw must be content-addressable, not call-order dependent"
    )
