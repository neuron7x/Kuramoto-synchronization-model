# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lane D — strict input-window data contract for the X-10R reconstruction path.

Scope (deliberately narrow): this module is **input validation only**. It is the
fail-closed gate that sits in front of the existing reconstruction-capsule
machinery (``research/reconstruction/reconstruction_capsule.py``). It answers a
single question — "is this market input window structurally admissible?" — and
nothing more.

It makes NO market claim, NO predictive/alpha claim, NO product-readiness or
trade-execution claim, and it emits NO ``PRODUCT_READY`` verdict. Per issue
#1168 §7 stop rules, that promotion is blocked until the oracle (#1153) is
terminal with hashes stable across two runs; this slice does not touch that
lane. A valid window here means *admissible for downstream reconstruction*, not
*validated*, *profitable*, or *correct*.

Contract (fail-closed — every violation raises ``DataContractError``):

* timestamps present, 1-D, integer-typed, strictly monotonically increasing,
  finite, and length-matched to the value series;
* value series present, 1-D, finite (no NaN, no ±Inf), length ≥ 2;
* adjacency (when supplied) square, finite, non-negative, shape-consistent with
  the value-series node count, and zero on the diagonal (no self-loops);
* a non-empty graph (≥ 2 nodes) — an empty graph is rejected.

On a window that satisfies every clause, ``validate_input_window`` returns an
``InputWindowContract`` carrying a stable ``input_fingerprint`` (sha256 over the
canonicalised, rounded inputs). The fingerprint is deterministic across
processes and machines for byte-equal admissible inputs and changes under any
1-ULP-significant perturbation that survives the rounding quantum.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

# Rounding quanta for fingerprint canonicalisation. Mirrors the convention used
# by ``reconstruction_capsule.hash_marginals`` (9 decimals on float marginals)
# so the two surfaces hash on the same quantisation grid.
_VALUE_ROUND_DECIMALS: Final[int] = 9

# Minimum admissible node / sample count. A reconstruction over fewer than two
# nodes is structurally degenerate (matches ReconstructionCapsule.n_nodes >= 2).
_MIN_NODES: Final[int] = 2


class DataContractError(ValueError):
    """Raised when an input window violates the Lane D data contract.

    Subclasses ``ValueError`` so existing fail-closed call sites that catch
    ``ValueError`` keep working; the distinct type lets callers that care about
    the contract specifically discriminate it.
    """


@dataclass(frozen=True)
class InputWindowContract:
    """Result of a successful Lane D validation.

    Attributes:
        n_nodes: number of nodes / samples in the validated window.
        input_fingerprint: 64-char lowercase sha256 hex over the canonicalised
            inputs. Stable across processes for byte-equal admissible windows.
        has_adjacency: whether an adjacency matrix was supplied and validated.

    NON-CLAIM: a returned contract certifies structural admissibility for
    downstream reconstruction only. It is not a recovery, validation, market,
    or product-readiness verdict.
    """

    n_nodes: int
    input_fingerprint: str
    has_adjacency: bool


def _as_1d(name: str, array: object) -> NDArray[np.float64]:
    arr = np.asarray(array)
    if arr.ndim != 1:
        raise DataContractError(
            f"DATA-CONTRACT VIOLATED: {name} must be 1-D; got ndim={arr.ndim}, shape={arr.shape}."
        )
    return arr.astype(np.float64, copy=False)


def _validate_timestamps(timestamps: object, n_expected: int) -> NDArray[np.int64]:
    arr = np.asarray(timestamps)
    if arr.ndim != 1:
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: timestamps must be 1-D; "
            f"got ndim={arr.ndim}, shape={arr.shape}."
        )
    if arr.size != n_expected:
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: timestamps length "
            f"{arr.size} != values length {n_expected} (length mismatch)."
        )
    # Integer-typed timestamps only: float epoch columns hide NaN/Inf and lose
    # monotonicity guarantees at large magnitudes. Reject them fail-closed.
    if not np.issubdtype(arr.dtype, np.integer):
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: timestamps must be integer-typed "
            f"(epoch units); got dtype={arr.dtype!r}. Missing/invalid timestamps "
            "are rejected; cast deliberately upstream."
        )
    ts = arr.astype(np.int64, copy=False)
    diffs = np.diff(ts)
    if ts.size >= 2 and not bool(np.all(diffs > 0)):
        first_bad = int(np.argmax(diffs <= 0))
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: timestamps must be strictly monotonically "
            f"increasing; non-monotonic at index {first_bad + 1} "
            f"(t[{first_bad}]={int(ts[first_bad])} >= t[{first_bad + 1}]="
            f"{int(ts[first_bad + 1])})."
        )
    return ts


def _validate_values(values: object) -> NDArray[np.float64]:
    arr = _as_1d("values", values)
    if arr.size < _MIN_NODES:
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: empty/degenerate graph — values length "
            f"{arr.size} < minimum {_MIN_NODES} nodes."
        )
    if not bool(np.all(np.isfinite(arr))):
        first_bad = int(np.argmax(~np.isfinite(arr)))
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: values must be finite (no NaN/Inf); "
            f"first non-finite at index {first_bad} (value={arr[first_bad]!r})."
        )
    return arr


def _validate_adjacency(adjacency: object, n_nodes: int) -> NDArray[np.float64]:
    arr = np.asarray(adjacency)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        raise DataContractError(
            f"DATA-CONTRACT VIOLATED: adjacency must be a square 2-D matrix; got shape={arr.shape}."
        )
    if arr.shape[0] != n_nodes:
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: adjacency node count "
            f"{arr.shape[0]} != values node count {n_nodes} (shape mismatch)."
        )
    adj = arr.astype(np.float64, copy=False)
    if not bool(np.all(np.isfinite(adj))):
        raise DataContractError("DATA-CONTRACT VIOLATED: adjacency must be finite (no NaN/Inf).")
    # bounds: edge weights are non-negative strengths; a negative weight is an
    # invalid adjacency under the reconstruction contract (not a physics clamp).
    if bool(np.any(adj < 0.0)):
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: adjacency must be non-negative; found negative weight(s)."
        )
    if bool(np.any(np.diagonal(adj) != 0.0)):
        raise DataContractError(
            "DATA-CONTRACT VIOLATED: adjacency diagonal must be zero (no self-loops)."
        )
    return adj


def _fingerprint(
    timestamps: NDArray[np.int64],
    values: NDArray[np.float64],
    adjacency: NDArray[np.float64] | None,
) -> str:
    hasher = hashlib.sha256()
    # Tag each field so concatenation is unambiguous and field reordering /
    # boundary aliasing cannot collide (cf. INV-DET2 trajectory-order aliasing).
    hasher.update(b"timestamps:")
    hasher.update(np.ascontiguousarray(timestamps, dtype=np.int64).tobytes())
    hasher.update(b"|values:")
    rounded = np.round(np.ascontiguousarray(values, dtype=np.float64), _VALUE_ROUND_DECIMALS)
    # Collapse signed zero so -0.0 and +0.0 fingerprint identically.
    rounded = rounded + 0.0
    hasher.update(rounded.tobytes())
    hasher.update(b"|adjacency:")
    if adjacency is None:
        hasher.update(b"none")
    else:
        adj = np.round(np.ascontiguousarray(adjacency, dtype=np.float64), _VALUE_ROUND_DECIMALS)
        adj = adj + 0.0
        hasher.update(f"{adj.shape[0]}x{adj.shape[1]}:".encode("ascii"))
        hasher.update(adj.tobytes())
    return hasher.hexdigest()


def validate_input_window(
    *,
    timestamps: object,
    values: object,
    adjacency: object | None = None,
) -> InputWindowContract:
    """Validate a market input window fail-closed and return a stable fingerprint.

    Args:
        timestamps: 1-D integer epoch series, strictly increasing, length-matched
            to ``values``.
        values: 1-D finite value series (≥ 2 entries, no NaN/Inf).
        adjacency: optional square, finite, non-negative, zero-diagonal matrix
            whose node count matches ``len(values)``.

    Returns:
        InputWindowContract with a deterministic ``input_fingerprint``.

    Raises:
        DataContractError: on any contract violation. The window is rejected;
            no partial / repaired window is ever returned (fail-closed).

    NON-CLAIM: success means structurally admissible for downstream
    reconstruction, NOT validated, profitable, or product-ready.
    """
    vals = _validate_values(values)
    n_nodes = int(vals.size)
    ts = _validate_timestamps(timestamps, n_nodes)
    adj: NDArray[np.float64] | None = None
    if adjacency is not None:
        adj = _validate_adjacency(adjacency, n_nodes)
    fingerprint = _fingerprint(ts, vals, adj)
    return InputWindowContract(
        n_nodes=n_nodes,
        input_fingerprint=fingerprint,
        has_adjacency=adj is not None,
    )
