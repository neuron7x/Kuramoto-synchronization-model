# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic descriptor-vs-null comparison harness.

This module reads where a single observed scalar descriptor statistic
falls *relative to a declared null / surrogate ensemble*. It is a
structural locator, not a forecaster: it returns the rank / percentile of
the observed value within a null baseline (for example one produced by
:mod:`analytics.signals.null_baseline`) and nothing more. The percentile
is a position against a declared structureless baseline; it is **not** a
p-value-as-truth, **not** a significance verdict, **not** alpha, and
**not** a statement about future prices, returns, or profitability.

The single public function, :func:`compare_to_null`, takes the observed
scalar and the null sample array and returns an immutable
:class:`NullComparison` dataclass carrying:

* ``observed`` — the scalar that was located;
* ``percentile`` — the fraction of null samples ``<= observed`` times
  100, in ``[0.0, 100.0]`` (mid-rank convention for ties);
* ``rank`` — the integer count of null samples strictly below
  ``observed``;
* ``n_null`` — the number of finite null samples actually used;
* ``band`` — the symmetric tail fraction defining the reference band;
* ``is_outside_null_band`` — ``True`` iff the percentile lies in the
  lower ``band`` or upper ``band`` tail of the null distribution;
* metadata pinning ``method``, ``seed`` (passed through from the null
  generator if known), and the boundary disclaimers
  (``claim_boundary="descriptor_only_not_predictor"``,
  ``not_predictive_claim=True``, ``not_financial_advice=True``).

Determinism
-----------
The comparison is a pure function of its inputs: no randomness, no
module-level or process-global state. Two calls with equal arguments
return equal results. Sorting is stable and percentile arithmetic is
performed in ``float64``.

Fail-closed
-----------
An empty null ensemble, a null ensemble with no finite samples, a
non-finite (NaN or infinity) observed value, or a ``band`` outside the
open interval ``(0, 0.5)`` each fail closed with :class:`ValueError`
rather than returning a misleading verdict. Non-finite samples *inside*
an otherwise-usable null are dropped and the surviving count is reported
through ``n_null``, so the percentile is never silently contaminated.

Worked example
--------------
>>> import numpy as np
>>> null = np.arange(0.0, 100.0)
>>> result = compare_to_null(50.0, null, band=0.05)
>>> result.rank
50
>>> round(result.percentile, 1)
50.5
>>> result.is_outside_null_band
False
>>> result.claim_boundary
'descriptor_only_not_predictor'
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_BAND",
    "NullComparison",
    "compare_to_null",
]

#: The single declared boundary string shared with the null generator.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"

#: Default symmetric tail fraction used when no band is supplied.
DEFAULT_BAND: float = 0.05


@dataclass(frozen=True)
class NullComparison:
    """Immutable result of locating an observed scalar within a null.

    Every field is a position / count / disclaimer. None of them is a
    prediction: ``percentile`` and ``is_outside_null_band`` describe only
    where ``observed`` sits relative to the declared null baseline.
    """

    observed: float
    percentile: float
    rank: int
    n_null: int
    band: float
    is_outside_null_band: bool
    method: str
    seed: int | None
    claim_boundary: str = CLAIM_BOUNDARY
    not_predictive_claim: bool = True
    not_financial_advice: bool = True
    research_only: bool = True
    _metadata: Mapping[str, Any] = field(
        repr=False,
        compare=False,
        default_factory=lambda: MappingProxyType({}),
    )

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Return the immutable disclaimer-bearing metadata mapping."""
        return self._metadata


def _validate_band(band: float) -> float:
    """Return ``band`` as a float in the open interval ``(0, 0.5)`` or fail.

    A band of ``0`` would make every observation "outside" by vacuous tail
    logic; a band ``>= 0.5`` would make the two tails meet or overlap. Both
    are rejected so the reference band is always a proper two-sided region.
    """
    if isinstance(band, bool):
        raise ValueError(f"band must be a float in (0, 0.5), got {band!r}")
    value = float(band)
    if not np.isfinite(value):
        raise ValueError(f"band must be finite, got {band!r}")
    if not (0.0 < value < 0.5):
        raise ValueError(f"band must lie in the open interval (0, 0.5), got {value}")
    return value


def _validate_observed(observed: float) -> float:
    """Return ``observed`` as a finite float or fail closed.

    A non-finite observed value cannot be located against a null; rather
    than emit a meaningless percentile the comparison refuses to proceed.
    """
    if isinstance(observed, bool):
        raise ValueError(f"observed must be a finite scalar, got {observed!r}")
    value = float(observed)
    if not np.isfinite(value):
        raise ValueError(f"observed must be finite, got {observed!r}")
    return value


def _finite_null(null_samples: NDArray[np.float64] | object) -> NDArray[np.float64]:
    """Return the finite subset of ``null_samples`` as a 1-D float64 array.

    Fails closed if the ensemble is empty or holds no finite sample, so a
    degenerate null can never produce a confident-looking verdict. Finite
    samples surviving a partially non-finite ensemble are kept and their
    count is reported by the caller through ``n_null``.
    """
    data = np.asarray(null_samples, dtype=np.float64)
    if data.ndim != 1:
        raise ValueError(f"null_samples must be one-dimensional, got ndim={data.ndim}")
    if data.shape[0] == 0:
        raise ValueError("null_samples is empty; refusing to compare against an empty null")
    finite = data[np.isfinite(data)]
    if finite.shape[0] == 0:
        raise ValueError("null_samples holds no finite value; refusing to compare")
    return finite


def compare_to_null(
    observed: float,
    null_samples: NDArray[np.float64] | object,
    *,
    band: float = DEFAULT_BAND,
    method: str = "rank_vs_null",
    seed: int | None = None,
) -> NullComparison:
    """Locate ``observed`` within ``null_samples`` and return its position.

    Parameters
    ----------
    observed:
        The single finite scalar descriptor statistic to locate. A
        non-finite value fails closed.
    null_samples:
        A one-dimensional array (or array-like) of null / surrogate
        descriptor values — for example produced by
        :mod:`analytics.signals.null_baseline`. An empty ensemble, or one
        with no finite samples, fails closed. Non-finite samples inside an
        otherwise-usable ensemble are dropped and ``n_null`` reports the
        surviving count.
    band:
        Symmetric tail fraction in the open interval ``(0, 0.5)`` defining
        the reference band. ``is_outside_null_band`` is ``True`` iff the
        observed percentile falls in the lower ``band`` or upper ``band``
        tail.
    method:
        A label recorded in the result and its metadata. Defaults to
        ``"rank_vs_null"``.
    seed:
        Optional seed of the upstream null generator, passed through into
        the result and metadata for provenance. Not used in any computation.

    Returns
    -------
    NullComparison
        An immutable result giving the rank, percentile, surviving null
        count, the band, ``is_outside_null_band``, and the descriptor-only
        boundary disclaimers. The percentile is a structural position
        against the declared null, not a p-value-as-truth, not a
        significance verdict, and not a predictive or financial claim.
    """
    obs = _validate_observed(observed)
    band_value = _validate_band(band)
    finite = _finite_null(null_samples)
    n_null = int(finite.shape[0])

    # Mid-rank percentile: counts strictly-below plus half the ties, so the
    # location is symmetric and unbiased for discrete null ensembles.
    below = int(np.count_nonzero(finite < obs))
    equal = int(np.count_nonzero(finite == obs))
    percentile = float((below + 0.5 * equal) / n_null * 100.0)

    lower_pct = band_value * 100.0
    upper_pct = (1.0 - band_value) * 100.0
    is_outside = bool(percentile < lower_pct or percentile > upper_pct)

    metadata: dict[str, Any] = {
        "method": method,
        "seed": seed,
        "n_null": n_null,
        "band": band_value,
        "percentile": percentile,
        "rank": below,
        "is_outside_null_band": is_outside,
        "claim_boundary": CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "not_financial_advice": True,
        "research_only": True,
    }

    return NullComparison(
        observed=obs,
        percentile=percentile,
        rank=below,
        n_null=n_null,
        band=band_value,
        is_outside_null_band=is_outside,
        method=method,
        seed=seed,
        _metadata=MappingProxyType(metadata),
    )
