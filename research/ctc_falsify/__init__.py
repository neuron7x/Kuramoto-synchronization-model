# SPDX-License-Identifier: MIT
"""CTC-FALSIFY-001 — fail-closed falsification engine for Communication-through-Coherence.

This package does NOT prove or disprove the CTC canon. It is a pre-registered,
fail-closed instrument that asks one bounded question with a physics-grounded
generative ground truth (two-population Sakaguchi-Kuramoto):

    Does the *standard* CTC analysis pipeline (gamma PLV + coherence) label
    confound-only signals (common drive / rate / SNR — NO communication
    channel) as "CTC-positive" at the canonical effect size, while a true
    phase-gated channel is recoverable?

A clean ``INADMISSIBLE_*`` verdict is the designed success at the pre-data
stage. ``KILLED_SCOPED`` / ``SURVIVED_INITIAL`` are unreachable until a real
electrophysiology dataset is bound (L2); the engine never fabricates a kill
and never rescues the canon.
"""

from research.ctc_falsify.config import EXPERIMENT_ID

__all__ = ["EXPERIMENT_ID"]
