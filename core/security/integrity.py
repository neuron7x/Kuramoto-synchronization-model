# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Cryptographic integrity verification for artifacts and AI models.

This module implements cryptographic controls aligned with:
- ISO/IEC 42001:2023 Clause 7.4 (AI System Security)
- NIST SP 800-57 (Key Management Recommendations)
- CWE-494 (Download of Code Without Integrity Check)
- NIST FIPS 180-4 (Secure Hash Standard)
- NIST FIPS 198-1 (Keyed-Hash Message Authentication Code)
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import BaseModel, Field


class IntegrityError(Exception):
    """Raised when integrity verification fails."""

    pass


class ChecksumManifest(BaseModel):
    """Manifest containing checksums and metadata for artifact verification.

    Implements cryptographic integrity verification aligned with NIST FIPS 180-4.
    """

    artifact_name: str = Field(..., description="Name of the artifact")
    artifact_version: str = Field(..., description="Version of the artifact")
    algorithm: str = Field(default="sha256", description="Hash algorithm used")
    checksum: str = Field(..., description="Hex-encoded checksum")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Timestamp when checksum was created",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class IntegrityVerifier:
    """Cryptographic integrity verifier for artifacts and models.

    Provides defense against:
    - Supply chain attacks (CWE-494)
    - File tampering
    - Model poisoning
    - Configuration corruption
    """

    SUPPORTED_ALGORITHMS = frozenset(
        {
            "sha256",  # NIST FIPS 180-4 recommended
            "sha384",
            "sha512",
            "sha3_256",
            "sha3_384",
            "sha3_512",
        }
    )

    DEFAULT_ALGORITHM = "sha256"

    @classmethod
    def compute_file_checksum(
        cls,
        file_path: Path,
        algorithm: str = DEFAULT_ALGORITHM,
        buffer_size: int = 65536,
    ) -> str:
        """Compute cryptographic checksum of a file.

        Args:
            file_path: Path to file
            algorithm: Hash algorithm to use (default: sha256)
            buffer_size: Size of read buffer in bytes

        Returns:
            Hex-encoded checksum

        Raises:
            ValueError: If algorithm is not supported
            FileNotFoundError: If file doesn't exist
            IntegrityError: If checksum computation fails
        """
        if algorithm not in cls.SUPPORTED_ALGORITHMS:
            raise ValueError(
                f"Unsupported algorithm '{algorithm}'. "
                f"Supported: {', '.join(sorted(cls.SUPPORTED_ALGORITHMS))}"
            )

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise IntegrityError(f"Path is not a file: {file_path}")

        try:
            hasher = hashlib.new(algorithm)

            with open(file_path, "rb") as f:
                while chunk := f.read(buffer_size):
                    hasher.update(chunk)

            return hasher.hexdigest()
        except Exception as e:
            raise IntegrityError(f"Failed to compute checksum for {file_path}: {e}") from e

    @classmethod
    def verify_file_checksum(
        cls,
        file_path: Path,
        expected_checksum: str,
        algorithm: str = DEFAULT_ALGORITHM,
    ) -> bool:
        """Verify file checksum matches expected value.

        Args:
            file_path: Path to file
            expected_checksum: Expected checksum (hex-encoded)
            algorithm: Hash algorithm to use

        Returns:
            True if checksum matches, False otherwise

        Raises:
            IntegrityError: If verification process fails
        """
        try:
            actual_checksum = cls.compute_file_checksum(file_path, algorithm)

            # Constant-time comparison to prevent timing attacks
            return hmac.compare_digest(actual_checksum.lower(), expected_checksum.lower())
        except Exception as e:
            raise IntegrityError(f"Checksum verification failed for {file_path}: {e}") from e

    @classmethod
    def create_manifest(
        cls,
        artifact_path: Path,
        artifact_name: str | None = None,
        artifact_version: str = "1.0.0",
        algorithm: str = DEFAULT_ALGORITHM,
        metadata: dict[str, Any] | None = None,
    ) -> ChecksumManifest:
        """Create checksum manifest for an artifact.

        Args:
            artifact_path: Path to artifact file
            artifact_name: Name of artifact (defaults to filename)
            artifact_version: Version of artifact
            algorithm: Hash algorithm to use
            metadata: Additional metadata to include

        Returns:
            ChecksumManifest object

        Raises:
            IntegrityError: If manifest creation fails
        """
        if artifact_name is None:
            artifact_name = artifact_path.name

        checksum = cls.compute_file_checksum(artifact_path, algorithm)

        manifest = ChecksumManifest(
            artifact_name=artifact_name,
            artifact_version=artifact_version,
            algorithm=algorithm,
            checksum=checksum,
            metadata=metadata or {},
        )

        return manifest

    @classmethod
    def verify_manifest(cls, artifact_path: Path, manifest: ChecksumManifest) -> bool:
        """Verify artifact against its manifest.

        Args:
            artifact_path: Path to artifact file
            manifest: ChecksumManifest to verify against

        Returns:
            True if verification succeeds

        Raises:
            IntegrityError: If verification fails
        """
        if not cls.verify_file_checksum(artifact_path, manifest.checksum, manifest.algorithm):
            raise IntegrityError(
                f"Checksum mismatch for {artifact_path}. "
                f"Expected: {manifest.checksum}, "
                f"Got: {cls.compute_file_checksum(artifact_path, manifest.algorithm)}"
            )

        return True

    @classmethod
    def save_manifest(cls, manifest: ChecksumManifest, output_path: Path) -> None:
        """Save manifest to JSON file.

        Args:
            manifest: ChecksumManifest to save
            output_path: Path to output file

        Raises:
            IntegrityError: If save fails
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(manifest.model_dump(), f, indent=2, sort_keys=True)
        except Exception as e:
            raise IntegrityError(f"Failed to save manifest to {output_path}: {e}") from e

    @classmethod
    def load_manifest(cls, manifest_path: Path) -> ChecksumManifest:
        """Load manifest from JSON file.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Loaded ChecksumManifest

        Raises:
            IntegrityError: If load fails
        """
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ChecksumManifest(**data)
        except Exception as e:
            raise IntegrityError(f"Failed to load manifest from {manifest_path}: {e}") from e


class HMACVerifier:
    """HMAC-based message authentication for sensitive artifacts.

    Implements keyed-hash message authentication aligned with NIST FIPS 198-1.
    Provides stronger authentication than simple checksums by requiring a secret key.
    """

    DEFAULT_ALGORITHM = "sha256"

    @classmethod
    def compute_hmac(
        cls,
        data: bytes | BinaryIO,
        key: bytes,
        algorithm: str = DEFAULT_ALGORITHM,
    ) -> str:
        """Compute HMAC for data.

        Args:
            data: Data to authenticate (bytes or file-like object)
            key: Secret key for HMAC (must be kept secure)
            algorithm: Hash algorithm to use

        Returns:
            Hex-encoded HMAC

        Raises:
            ValueError: If algorithm is not supported
        """
        if algorithm not in IntegrityVerifier.SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # Handle file-like objects
        if hasattr(data, "read"):
            h = hmac.new(key, digestmod=algorithm)
            while chunk := data.read(65536):
                h.update(chunk)
            return h.hexdigest()

        # Handle bytes directly
        return hmac.new(key, data, digestmod=algorithm).hexdigest()

    @classmethod
    def verify_hmac(
        cls,
        data: bytes | BinaryIO,
        key: bytes,
        expected_hmac: str,
        algorithm: str = DEFAULT_ALGORITHM,
    ) -> bool:
        """Verify HMAC for data.

        Args:
            data: Data to verify
            key: Secret key for HMAC
            expected_hmac: Expected HMAC (hex-encoded)
            algorithm: Hash algorithm to use

        Returns:
            True if HMAC matches

        Raises:
            ValueError: If algorithm is not supported
        """
        actual_hmac = cls.compute_hmac(data, key, algorithm)

        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(actual_hmac.lower(), expected_hmac.lower())

    @classmethod
    def compute_file_hmac(
        cls,
        file_path: Path,
        key: bytes,
        algorithm: str = DEFAULT_ALGORITHM,
    ) -> str:
        """Compute HMAC for a file.

        Args:
            file_path: Path to file
            key: Secret key for HMAC
            algorithm: Hash algorithm to use

        Returns:
            Hex-encoded HMAC

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            return cls.compute_hmac(f, key, algorithm)

    @classmethod
    def verify_file_hmac(
        cls,
        file_path: Path,
        key: bytes,
        expected_hmac: str,
        algorithm: str = DEFAULT_ALGORITHM,
    ) -> bool:
        """Verify HMAC for a file.

        Args:
            file_path: Path to file
            key: Secret key for HMAC
            expected_hmac: Expected HMAC (hex-encoded)
            algorithm: Hash algorithm to use

        Returns:
            True if HMAC matches
        """
        actual_hmac = cls.compute_file_hmac(file_path, key, algorithm)
        return hmac.compare_digest(actual_hmac.lower(), expected_hmac.lower())


class ModelIntegrityChecker:
    """Specialized integrity checker for AI/ML models.

    Implements security controls from ISO/IEC 42001:2023 for AI model security.
    Prevents model poisoning and supply chain attacks.
    """

    @staticmethod
    def verify_model_file(
        model_path: Path,
        manifest_path: Path | None = None,
        expected_checksum: str | None = None,
    ) -> bool:
        """Verify integrity of a model file.

        Args:
            model_path: Path to model file
            manifest_path: Path to manifest file (optional)
            expected_checksum: Expected checksum if not using manifest

        Returns:
            True if verification succeeds

        Raises:
            IntegrityError: If verification fails
            ValueError: If neither manifest nor checksum provided
        """
        if manifest_path is not None:
            manifest = IntegrityVerifier.load_manifest(manifest_path)
            return IntegrityVerifier.verify_manifest(model_path, manifest)
        elif expected_checksum is not None:
            return IntegrityVerifier.verify_file_checksum(model_path, expected_checksum)
        else:
            raise ValueError("Either manifest_path or expected_checksum must be provided")

    @staticmethod
    def create_model_manifest(
        model_path: Path,
        model_name: str,
        model_version: str,
        framework: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChecksumManifest:
        """Create integrity manifest for a model.

        Args:
            model_path: Path to model file
            model_name: Name of the model
            model_version: Version of the model
            framework: ML framework (e.g., 'pytorch', 'tensorflow', 'sklearn')
            metadata: Additional metadata (training metrics, dataset info, etc.)

        Returns:
            ChecksumManifest for the model
        """
        model_metadata = {
            "framework": framework,
            "model_type": "machine_learning",
            **(metadata or {}),
        }

        return IntegrityVerifier.create_manifest(
            artifact_path=model_path,
            artifact_name=model_name,
            artifact_version=model_version,
            metadata=model_metadata,
        )


__all__ = [
    "IntegrityError",
    "ChecksumManifest",
    "IntegrityVerifier",
    "HMACVerifier",
    "ModelIntegrityChecker",
]
