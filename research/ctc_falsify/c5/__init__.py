# SPDX-License-Identifier: MIT
"""C5 — decisive identifiability oracle probe (closes the C4 OPEN).

C4 retracted C3's claim that the channel was "recoverable in principle".
The residual OPEN: is the standard-estimand blindness an *identifiability
limit* of these observables at this regime, or merely an
*estimator-quality* gap? C5 puts a near-oracle upper bound on it: the best
out-of-sample linear discriminant over the FULL gamma cross-spectral
representation (magnitude + phase), train/test seed-disjoint. If even that
cannot separate N⁺ from confounds -> identifiability limit (a strong
boundary result). If it separates cleanly -> estimator-quality gap. This
is the one decisive cycle; it terminates the OPEN, then the arc
consolidates.
"""

__all__: list[str] = []
