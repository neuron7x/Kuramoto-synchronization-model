r"""Quantum-inspired utilities for the advanced neuroeconomic toolkit.

The helpers contained in this module provide lightweight linear-algebra based
approximations of quantum-information metrics that are tractable inside the
existing analytics runtime.  They intentionally avoid heavyweight third-party
dependencies so that researchers can experiment with quantum-active inference
ideas in environments where packages such as :mod:`qutip` may be unavailable.

The implementation follows three guiding principles:

``Density matrices``
    Price and indicator gradients are embedded as pure quantum states by
    normalising the vectors and constructing outer products.  Degenerate cases
    (e.g. a vector with negligible norm) are mapped to the maximally mixed
    state to keep the computations well-defined.

``Entropy``
    Von Neumann entropy is evaluated via the eigenvalues of the density matrix,
    :math:`S(\rho) = -\sum_i \lambda_i \log \lambda_i`.  The eigenvalues are
    clipped at ``1e-12`` to preserve numerical stability.

``Relative entropy``
    The quantum relative entropy leverages the identity
    :math:`S(\rho_1\|\rho_2) = \mathrm{Tr}(\rho_1 (\log \rho_1 - \log \rho_2))`
    where the matrix logarithms are reconstructed from the eigen-decompositions
    of ``rho_1`` and ``rho_2`` respectively.

All routines are extensively type hinted to make their behaviour explicit and
facilitate static analysis using tools such as ``mypy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

_EPSILON = 1e-12


def _normalise(vector: np.ndarray) -> np.ndarray:
    """Return a safely normalised copy of ``vector``.

    The function maps zero vectors to the unit basis vector of matching
    dimensionality to avoid division-by-zero artefacts.  For non-zero vectors
    the components are scaled by their Euclidean norm.
    """

    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm < _EPSILON:
        basis = np.zeros_like(vector, dtype=float)
        if basis.size:
            basis[0] = 1.0
        return basis
    return (vector / norm).astype(float)


def to_density_matrix(vector: Iterable[float]) -> np.ndarray:
    r"""Map ``vector`` onto a pure-state density matrix.

    Parameters
    ----------
    vector:
        Sequence of real numbers representing a signal gradient.  The values
        are normalised prior to generating the outer product.

    Returns
    -------
    numpy.ndarray
        Square, Hermitian, positive semi-definite matrix describing the state.
    """

    arr = np.asarray(vector, dtype=float)
    normalised = _normalise(arr)
    return np.outer(normalised, normalised.conj())


def von_neumann_entropy(rho: np.ndarray) -> float:
    r"""Compute the Von Neumann entropy :math:`S(\rho)` of ``rho``.

    The input matrix is expected to be Hermitian and positive semi-definite.  A
    defensive ``np.clip`` ensures the logarithm remains numerically stable.
    """

    eigenvalues = np.linalg.eigvalsh(rho)
    clipped = np.clip(eigenvalues, _EPSILON, 1.0)
    entropy = -float(np.sum(clipped * np.log(clipped)))
    return entropy


def _matrix_log(rho: np.ndarray) -> np.ndarray:
    """Return the matrix logarithm for a Hermitian positive matrix."""

    eigvals, eigvecs = np.linalg.eigh(rho)
    clipped = np.clip(eigvals, _EPSILON, None)
    log_diag = np.diag(np.log(clipped))
    return eigvecs @ log_diag @ eigvecs.conj().T


def quantum_relative_entropy(rho_p: np.ndarray, rho_f: np.ndarray) -> float:
    r"""Evaluate the quantum relative entropy :math:`S(\rho_p\|\rho_f)`.

    Both matrices are treated as density operators.  The computation uses the
    trace identity ``Tr(rho_p (log rho_p - log rho_f))`` which provides a stable
    and differentiable objective for divergence-aware learning.
    """

    log_rho_p = _matrix_log(rho_p)
    log_rho_f = _matrix_log(rho_f)
    delta = log_rho_p - log_rho_f
    return float(np.trace(rho_p @ delta).real)


@dataclass(frozen=True, slots=True)
class QuantumBeliefUpdate:
    """Container for the results of a quantum-active inference step."""

    phi: float
    entropy: float


def quantum_active_update(
    phi: float,
    convergence: float,
    divergence: float,
    *,
    learning_rate: float,
    entropy_weight: float,
    state_vector: Iterable[float],
) -> QuantumBeliefUpdate:
    r"""Perform a quantum-inspired active inference update.

    The belief state ``phi`` is nudged towards trajectories that increase
    convergence while penalising divergence and entropy of the latent state.
    The update rule follows the heuristic

    .. math::

        \Delta \phi = \eta \left[(\mathrm{Conv} - \mathrm{Div})
        - \lambda S(\rho_{\phi})\right]

    where ``eta`` is ``learning_rate`` and ``lambda`` is ``entropy_weight``.

    Parameters
    ----------
    phi:
        Previous belief value.
    convergence / divergence:
        Scalars describing local synchrony and mismatch between price and
        factor gradients.
    learning_rate:
        Step size :math:`\eta` for the belief update.
    entropy_weight:
        Weight :math:`\lambda` applied to the entropy penalty.
    state_vector:
        Iterable describing the latent quantum state, typically built from the
        latest ``phi`` and observable gradients.

    Returns
    -------
    QuantumBeliefUpdate
        Updated belief and the entropy term applied during the step.
    """

    baseline = float(convergence - divergence)
    rho_phi = to_density_matrix(tuple(float(x) for x in state_vector))
    entropy = von_neumann_entropy(rho_phi)
    delta = learning_rate * (baseline - entropy_weight * entropy)
    updated_phi = float(phi + delta)
    return QuantumBeliefUpdate(phi=updated_phi, entropy=entropy)


__all__ = [
    "QuantumBeliefUpdate",
    "quantum_active_update",
    "quantum_relative_entropy",
    "to_density_matrix",
    "von_neumann_entropy",
]
