# SPDX-License-Identifier: MIT
"""CTC-FALSIFY-001 L2 — real-data residual layer (pre-data, fail-closed).

L1 proved in-silico that the naive PLV+coherence pipeline confuses confounds
with a channel. L2 adds the machinery that can finally reach
``KILLED_SCOPED`` / ``SURVIVED_INITIAL`` on real electrophysiology — but only
after a dataset is bound (C3). Pre-data, the reference verdict is the designed
``INADMISSIBLE_NO_PAIRED_DATA``.

All eight self-audit fixes (see docs/research/CTC_FALSIFY_001_L2_PREREGISTRATION.md)
are wired as gates here, not as prose.
"""

from research.ctc_falsify.l2.config_l2 import L2_ID

__all__ = ["L2_ID"]
