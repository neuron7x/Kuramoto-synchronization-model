# SPDX-License-Identifier: MIT
"""C-real — the real-data layer of CTC-FALSIFY-001 (pre-registration only).

The in-silico arc (L1→L2→C3→C4→C5) is consolidated and metric-hardened:
standard scalar CTC estimands are blind, but the channel is
information-recoverable from the full gamma cross-spectrum (estimator-
quality gap, not identifiability). The only open layer is real
electrophysiology. This package is the FROZEN pre-registration + a
fail-closed stub: no dataset is bound, no data is touched. The reference
verdict is the designed ``INADMISSIBLE_NO_PAIRED_DATA``. KILLED_SCOPED /
SURVIVED_INITIAL are unreachable until C-real-data binds a dataset under
the pre-committed selection rule.
"""

from research.ctc_falsify.c_real.config_c_real import C_REAL_ID

__all__ = ["C_REAL_ID"]
