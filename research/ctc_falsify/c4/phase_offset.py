# SPDX-License-Identifier: MIT
"""The privileged estimator under audit: mean gamma-band phase offset.

offset(A, B) = mean( unwrap(angle(hilbert(bp(A)))) - unwrap(angle(hilbert(bp(B)))) )

Directed: offset(B, A) = -offset(A, B) up to estimation error. This is the
exact quantity the C3 boundary probe used to claim the channel is
"recoverable in principle". C4 audits whether THAT claim is itself sound.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import hilbert

from research.ctc_falsify.generative import TwoPopSignals
from research.ctc_falsify.pipeline import _bandpass


def phase_offset(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
    pa = np.unwrap(np.angle(hilbert(_bandpass(np.asarray(sig_a, dtype=np.float64)))))
    pb = np.unwrap(np.angle(hilbert(_bandpass(np.asarray(sig_b, dtype=np.float64)))))
    return float(np.mean(pa - pb))


def offset_ab(sig: TwoPopSignals) -> float:
    return phase_offset(sig.sig_a, sig.sig_b)


def offset_ba(sig: TwoPopSignals) -> float:
    """Directional negative control: swapping the two channels must flip
    the sign of a genuinely directed estimator."""
    return phase_offset(sig.sig_b, sig.sig_a)
