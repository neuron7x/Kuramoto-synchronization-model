"""Cryptographically secure random number generation.

This module provides secure random number generation for security-sensitive operations,
replacing standard pseudo-random generators that are unsuitable for cryptographic purposes.

Aligned with:
- CWE-338 (Use of Cryptographically Weak Pseudo-Random Number Generator)
- NIST SP 800-90A (Recommendation for Random Number Generation)
- OWASP Cryptographic Storage Cheat Sheet
"""

from __future__ import annotations

import secrets
from typing import Sequence, TypeVar

import numpy as np

T = TypeVar("T")


class SecureRandom:
    """Cryptographically secure random number generator.

    Uses Python's secrets module which leverages OS-provided CSPRNG.
    Suitable for security-sensitive operations including:
    - Token generation
    - Key derivation
    - Cryptographic nonces
    - Security-sensitive sampling
    """

    @staticmethod
    def randint(a: int, b: int) -> int:
        """Generate a random integer in range [a, b] using CSPRNG.

        Args:
            a: Lower bound (inclusive)
            b: Upper bound (inclusive)

        Returns:
            Cryptographically secure random integer

        Example:
            >>> SecureRandom.randint(1, 100)  # doctest: +SKIP
            42
        """
        if a > b:
            raise ValueError("Lower bound must be <= upper bound")
        return secrets.randbelow(b - a + 1) + a

    @staticmethod
    def random() -> float:
        """Generate a random float in range [0.0, 1.0) using CSPRNG.

        Returns:
            Cryptographically secure random float

        Note:
            Uses 64-bit precision for uniformity across range.
        """
        # Generate 64-bit random integer and normalize to [0, 1)
        return secrets.randbits(64) / (2**64)

    @staticmethod
    def uniform(a: float, b: float) -> float:
        """Generate a random float in range [a, b) using CSPRNG.

        Args:
            a: Lower bound (inclusive)
            b: Upper bound (exclusive)

        Returns:
            Cryptographically secure random float
        """
        if a >= b:
            raise ValueError("Lower bound must be < upper bound")
        return a + (b - a) * SecureRandom.random()

    @staticmethod
    def choice(seq: Sequence[T]) -> T:
        """Choose a random element from a sequence using CSPRNG.

        Args:
            seq: Non-empty sequence to choose from

        Returns:
            Randomly selected element

        Raises:
            IndexError: If sequence is empty
        """
        if not seq:
            raise IndexError("Cannot choose from empty sequence")
        return secrets.choice(seq)

    @staticmethod
    def sample(population: Sequence[T], k: int) -> list[T]:
        """Choose k unique random elements from population using CSPRNG.

        Args:
            population: Sequence to sample from
            k: Number of elements to sample

        Returns:
            List of k unique randomly selected elements

        Raises:
            ValueError: If k > len(population)
        """
        if k > len(population):
            raise ValueError("Sample size cannot exceed population size")

        # Convert to list for index access
        pop_list = list(population)
        result = []
        indices = set()

        while len(result) < k:
            idx = secrets.randbelow(len(pop_list))
            if idx not in indices:
                indices.add(idx)
                result.append(pop_list[idx])

        return result

    @staticmethod
    def shuffle(x: list[T]) -> None:
        """Shuffle list in place using CSPRNG.

        Args:
            x: List to shuffle (modified in place)

        Note:
            Uses Fisher-Yates shuffle algorithm with secure random source.
        """
        n = len(x)
        for i in range(n - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            x[i], x[j] = x[j], x[i]

    @staticmethod
    def token_bytes(nbytes: int = 32) -> bytes:
        """Generate random bytes suitable for cryptographic use.

        Args:
            nbytes: Number of bytes to generate (default: 32)

        Returns:
            Random bytes

        Example:
            >>> token = SecureRandom.token_bytes(32)  # doctest: +SKIP
            >>> len(token)  # doctest: +SKIP
            32
        """
        return secrets.token_bytes(nbytes)

    @staticmethod
    def token_hex(nbytes: int = 32) -> str:
        """Generate random hex string suitable for cryptographic use.

        Args:
            nbytes: Number of random bytes to generate (output will be 2x length)

        Returns:
            Random hex string

        Example:
            >>> token = SecureRandom.token_hex(16)  # doctest: +SKIP
            >>> len(token)  # doctest: +SKIP
            32
        """
        return secrets.token_hex(nbytes)

    @staticmethod
    def token_urlsafe(nbytes: int = 32) -> str:
        """Generate random URL-safe text string.

        Args:
            nbytes: Number of random bytes to use

        Returns:
            URL-safe random string

        Example:
            >>> token = SecureRandom.token_urlsafe()  # doctest: +SKIP
            >>> len(token)  # doctest: +SKIP
            43
        """
        return secrets.token_urlsafe(nbytes)


class SecureNumpyRandom:
    """Cryptographically secure random number generator for NumPy arrays.

    Provides secure alternatives to numpy.random for security-sensitive operations.
    """

    @staticmethod
    def _get_secure_generator() -> np.random.Generator:
        """Get NumPy random generator seeded with cryptographically secure entropy.

        Returns:
            NumPy random generator with secure seed
        """
        # Use secrets to generate secure seed
        seed = secrets.randbits(128)
        return np.random.default_rng(seed)

    @classmethod
    def random(cls, size: int | tuple[int, ...] | None = None) -> np.ndarray:
        """Generate random floats in [0.0, 1.0).

        Args:
            size: Output shape

        Returns:
            Random array with secure entropy
        """
        rng = cls._get_secure_generator()
        return rng.random(size)

    @classmethod
    def uniform(
        cls,
        low: float = 0.0,
        high: float = 1.0,
        size: int | tuple[int, ...] | None = None,
    ) -> np.ndarray:
        """Generate random floats uniformly distributed in [low, high).

        Args:
            low: Lower bound (inclusive)
            high: Upper bound (exclusive)
            size: Output shape

        Returns:
            Random array with secure entropy
        """
        rng = cls._get_secure_generator()
        return rng.uniform(low, high, size)

    @classmethod
    def integers(
        cls,
        low: int,
        high: int | None = None,
        size: int | tuple[int, ...] | None = None,
    ) -> np.ndarray | int:
        """Generate random integers.

        Args:
            low: Lower bound (inclusive), or upper bound if high is None
            high: Upper bound (exclusive), or None
            size: Output shape, or None for scalar

        Returns:
            Random integers with secure entropy
        """
        rng = cls._get_secure_generator()
        return rng.integers(low, high, size)

    @classmethod
    def choice(
        cls,
        a: int | np.ndarray,
        size: int | tuple[int, ...] | None = None,
        replace: bool = True,
        p: np.ndarray | None = None,
    ) -> np.ndarray:
        """Generate random sample from array.

        Args:
            a: Array or int (if int, sample from np.arange(a))
            size: Output shape
            replace: Whether to sample with replacement
            p: Probabilities associated with each entry

        Returns:
            Random sample with secure entropy
        """
        rng = cls._get_secure_generator()
        return rng.choice(a, size, replace, p)

    @classmethod
    def shuffle(cls, x: np.ndarray) -> None:
        """Shuffle array in place.

        Args:
            x: Array to shuffle (modified in place)
        """
        rng = cls._get_secure_generator()
        rng.shuffle(x)


# Backward compatibility aliases
secure_random = SecureRandom()
secure_numpy_random = SecureNumpyRandom()


__all__ = [
    "SecureRandom",
    "SecureNumpyRandom",
    "secure_random",
    "secure_numpy_random",
]
