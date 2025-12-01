"""Tests for cryptographic integrity verification."""

import io
import json
from pathlib import Path

import pytest

from core.security.integrity import (
    ChecksumManifest,
    HMACVerifier,
    IntegrityError,
    IntegrityVerifier,
    ModelIntegrityChecker,
)


class TestIntegrityVerifier:
    """Tests for integrity verification."""

    def test_compute_file_checksum(self, tmp_path):
        """Test computing file checksums."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        # Compute checksum
        checksum = IntegrityVerifier.compute_file_checksum(test_file)

        # Verify it's a valid hex string
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA-256 produces 64 hex characters
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_compute_checksum_different_algorithms(self, tmp_path):
        """Test different hash algorithms."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test data")

        algorithms = ["sha256", "sha384", "sha512", "sha3_256"]
        expected_lengths = {
            "sha256": 64,
            "sha384": 96,
            "sha512": 128,
            "sha3_256": 64,
        }

        for algo in algorithms:
            checksum = IntegrityVerifier.compute_file_checksum(test_file, algo)
            assert len(checksum) == expected_lengths[algo]

    def test_unsupported_algorithm(self, tmp_path):
        """Test rejection of unsupported algorithms."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test")

        with pytest.raises(ValueError, match="Unsupported algorithm"):
            IntegrityVerifier.compute_file_checksum(test_file, "md5")

    def test_file_not_found(self):
        """Test error handling for non-existent files."""
        with pytest.raises(FileNotFoundError):
            IntegrityVerifier.compute_file_checksum(Path("/nonexistent/file.txt"))

    def test_directory_raises_integrity_error(self, tmp_path):
        """Test that computing checksum on a directory raises IntegrityError."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with pytest.raises(IntegrityError, match="Path is not a file"):
            IntegrityVerifier.compute_file_checksum(test_dir)

    def test_verify_file_checksum_success(self, tmp_path):
        """Test successful checksum verification."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")

        # Compute checksum
        expected_checksum = IntegrityVerifier.compute_file_checksum(test_file)

        # Verify
        assert IntegrityVerifier.verify_file_checksum(test_file, expected_checksum)

    def test_verify_file_checksum_failure(self, tmp_path):
        """Test checksum verification failure."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")

        # Wrong checksum
        wrong_checksum = "0" * 64

        assert not IntegrityVerifier.verify_file_checksum(test_file, wrong_checksum)

    def test_verify_file_checksum_case_insensitive(self, tmp_path):
        """Test checksum verification is case-insensitive."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")

        expected_checksum = IntegrityVerifier.compute_file_checksum(test_file)

        # Test with uppercase checksum
        assert IntegrityVerifier.verify_file_checksum(
            test_file, expected_checksum.upper()
        )

        # Test with mixed case
        mixed_case = expected_checksum[:16].upper() + expected_checksum[16:].lower()
        assert IntegrityVerifier.verify_file_checksum(test_file, mixed_case)

    def test_create_manifest(self, tmp_path):
        """Test manifest creation."""
        test_file = tmp_path / "artifact.bin"
        test_file.write_bytes(b"artifact content")

        manifest = IntegrityVerifier.create_manifest(
            artifact_path=test_file,
            artifact_name="test_artifact",
            artifact_version="1.0.0",
            metadata={"author": "test", "purpose": "testing"},
        )

        assert isinstance(manifest, ChecksumManifest)
        assert manifest.artifact_name == "test_artifact"
        assert manifest.artifact_version == "1.0.0"
        assert manifest.algorithm == "sha256"
        assert len(manifest.checksum) == 64
        assert manifest.metadata["author"] == "test"

    def test_verify_manifest_success(self, tmp_path):
        """Test successful manifest verification."""
        test_file = tmp_path / "artifact.bin"
        test_file.write_bytes(b"artifact content")

        # Create manifest
        manifest = IntegrityVerifier.create_manifest(test_file)

        # Verify
        assert IntegrityVerifier.verify_manifest(test_file, manifest)

    def test_verify_manifest_failure(self, tmp_path):
        """Test manifest verification failure on file modification."""
        test_file = tmp_path / "artifact.bin"
        test_file.write_bytes(b"original content")

        # Create manifest
        manifest = IntegrityVerifier.create_manifest(test_file)

        # Modify file
        test_file.write_bytes(b"modified content")

        # Verification should fail
        with pytest.raises(IntegrityError, match="Checksum mismatch"):
            IntegrityVerifier.verify_manifest(test_file, manifest)

    def test_save_and_load_manifest(self, tmp_path):
        """Test saving and loading manifests."""
        # Create test file and manifest
        test_file = tmp_path / "artifact.bin"
        test_file.write_bytes(b"test content")

        manifest = IntegrityVerifier.create_manifest(
            test_file, artifact_name="test", artifact_version="1.0.0"
        )

        # Save manifest
        manifest_file = tmp_path / "manifest.json"
        IntegrityVerifier.save_manifest(manifest, manifest_file)

        assert manifest_file.exists()

        # Load manifest
        loaded_manifest = IntegrityVerifier.load_manifest(manifest_file)

        assert loaded_manifest.artifact_name == manifest.artifact_name
        assert loaded_manifest.checksum == manifest.checksum
        assert loaded_manifest.algorithm == manifest.algorithm

    def test_manifest_json_format(self, tmp_path):
        """Test manifest JSON format."""
        test_file = tmp_path / "artifact.bin"
        test_file.write_bytes(b"test")

        manifest = IntegrityVerifier.create_manifest(test_file)
        manifest_file = tmp_path / "manifest.json"
        IntegrityVerifier.save_manifest(manifest, manifest_file)

        # Verify JSON is properly formatted
        with open(manifest_file, "r") as f:
            data = json.load(f)

        assert "artifact_name" in data
        assert "checksum" in data
        assert "algorithm" in data
        assert "created_at" in data


class TestHMACVerifier:
    """Tests for HMAC verification."""

    def test_compute_hmac_bytes(self):
        """Test computing HMAC for bytes."""
        data = b"test data"
        key = b"secret key"

        hmac_value = HMACVerifier.compute_hmac(data, key)

        assert isinstance(hmac_value, str)
        assert len(hmac_value) == 64  # SHA-256 HMAC
        assert all(c in "0123456789abcdef" for c in hmac_value)

    def test_compute_hmac_file_like_object(self, tmp_path):
        """Test computing HMAC for file-like objects."""
        data = b"test data for file object"
        key = b"secret key"

        # Test with BytesIO
        file_obj = io.BytesIO(data)
        hmac_value = HMACVerifier.compute_hmac(file_obj, key)

        # Should match the HMAC for raw bytes
        expected_hmac = HMACVerifier.compute_hmac(data, key)
        assert hmac_value == expected_hmac

    def test_compute_file_hmac(self, tmp_path):
        """Test computing HMAC for files."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")
        key = b"secret key"

        hmac_value = HMACVerifier.compute_file_hmac(test_file, key)

        assert isinstance(hmac_value, str)
        assert len(hmac_value) == 64

    def test_verify_hmac_success(self):
        """Test successful HMAC verification."""
        data = b"test data"
        key = b"secret key"

        expected_hmac = HMACVerifier.compute_hmac(data, key)
        assert HMACVerifier.verify_hmac(data, key, expected_hmac)

    def test_verify_hmac_failure(self):
        """Test HMAC verification failure with wrong key."""
        data = b"test data"
        correct_key = b"correct key"
        wrong_key = b"wrong key"

        hmac_with_correct_key = HMACVerifier.compute_hmac(data, correct_key)

        # Verification with wrong key should fail
        assert not HMACVerifier.verify_hmac(data, wrong_key, hmac_with_correct_key)

    def test_verify_file_hmac(self, tmp_path):
        """Test file HMAC verification."""
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(b"test content")
        key = b"secret key"

        expected_hmac = HMACVerifier.compute_file_hmac(test_file, key)
        assert HMACVerifier.verify_file_hmac(test_file, key, expected_hmac)

    def test_verify_hmac_case_insensitive(self):
        """Test HMAC verification is case-insensitive."""
        data = b"test data"
        key = b"secret key"

        expected_hmac = HMACVerifier.compute_hmac(data, key)

        # Test with uppercase
        assert HMACVerifier.verify_hmac(data, key, expected_hmac.upper())

        # Test with mixed case
        mixed_case = expected_hmac[:16].upper() + expected_hmac[16:].lower()
        assert HMACVerifier.verify_hmac(data, key, mixed_case)

    def test_hmac_unsupported_algorithm(self):
        """Test HMAC rejects unsupported algorithms."""
        with pytest.raises(ValueError, match="Unsupported algorithm"):
            HMACVerifier.compute_hmac(b"test", b"key", "md5")

    def test_hmac_file_not_found(self):
        """Test HMAC file verification with non-existent file."""
        with pytest.raises(FileNotFoundError):
            HMACVerifier.compute_file_hmac(Path("/nonexistent/file.txt"), b"key")

    def test_hmac_different_algorithms(self):
        """Test HMAC with different algorithms."""
        data = b"test"
        key = b"key"

        algorithms = ["sha256", "sha384", "sha512"]
        for algo in algorithms:
            hmac_value = HMACVerifier.compute_hmac(data, key, algo)
            assert isinstance(hmac_value, str)
            assert HMACVerifier.verify_hmac(data, key, hmac_value, algo)


class TestModelIntegrityChecker:
    """Tests for model integrity checking."""

    def test_create_model_manifest(self, tmp_path):
        """Test creating model manifest."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"model weights")

        manifest = ModelIntegrityChecker.create_model_manifest(
            model_path=model_file,
            model_name="trading_strategy_v1",
            model_version="1.2.3",
            framework="pytorch",
            metadata={
                "accuracy": 0.95,
                "training_samples": 100000,
            },
        )

        assert manifest.artifact_name == "trading_strategy_v1"
        assert manifest.artifact_version == "1.2.3"
        assert manifest.metadata["framework"] == "pytorch"
        assert manifest.metadata["accuracy"] == 0.95
        assert manifest.metadata["model_type"] == "machine_learning"

    def test_verify_model_with_manifest(self, tmp_path):
        """Test model verification with manifest."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"model data")

        # Create manifest
        manifest = ModelIntegrityChecker.create_model_manifest(
            model_path=model_file,
            model_name="test_model",
            model_version="1.0.0",
            framework="sklearn",
        )

        # Save manifest
        manifest_file = tmp_path / "manifest.json"
        IntegrityVerifier.save_manifest(manifest, manifest_file)

        # Verify
        assert ModelIntegrityChecker.verify_model_file(model_file, manifest_file)

    def test_verify_model_with_checksum(self, tmp_path):
        """Test model verification with direct checksum."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"model data")

        expected_checksum = IntegrityVerifier.compute_file_checksum(model_file)

        assert ModelIntegrityChecker.verify_model_file(
            model_file, expected_checksum=expected_checksum
        )

    def test_verify_model_failure(self, tmp_path):
        """Test model verification failure."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"original model")

        # Create manifest
        manifest = ModelIntegrityChecker.create_model_manifest(
            model_path=model_file,
            model_name="test_model",
            model_version="1.0.0",
            framework="pytorch",
        )

        manifest_file = tmp_path / "manifest.json"
        IntegrityVerifier.save_manifest(manifest, manifest_file)

        # Modify model file (simulate tampering)
        model_file.write_bytes(b"tampered model")

        # Verification should fail
        with pytest.raises(IntegrityError):
            ModelIntegrityChecker.verify_model_file(model_file, manifest_file)

    def test_verify_model_no_source(self, tmp_path):
        """Test model verification without manifest or checksum."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"model data")

        with pytest.raises(
            ValueError, match="Either manifest_path or expected_checksum"
        ):
            ModelIntegrityChecker.verify_model_file(model_file)
