# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.security modules."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

try:
    from core.security.integrity import (
        IntegrityError,
        IntegrityVerifier,
    )
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

try:
    from core.security.validation import (
        CommandValidator,
        NumericRangeValidator,
        PathValidator,
        TradingSymbolValidator,
        ValidationError,
    )
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)

try:
    from core.security.random import SecureRandom
except ImportError:
    pytest.skip("module dependencies not available", allow_module_level=True)


class TestIntegrityVerifier:
    pytestmark = pytest.mark.skipif(IntegrityVerifier is None, reason="integrity not importable")

    def test_compute_file_checksum(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        checksum = IntegrityVerifier.compute_file_checksum(f)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert checksum == expected

    def test_verify_file_checksum(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"data")
        expected = hashlib.sha256(b"data").hexdigest()
        assert IntegrityVerifier.verify_file_checksum(f, expected) is True

    def test_verify_wrong_checksum(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"data")
        assert IntegrityVerifier.verify_file_checksum(f, "0" * 64) is False

    def test_unsupported_algorithm(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"x")
        with pytest.raises(ValueError, match="Unsupported"):
            IntegrityVerifier.compute_file_checksum(f, algorithm="md5")

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            IntegrityVerifier.compute_file_checksum(Path("/nonexistent/file.bin"))

    def test_create_manifest(self, tmp_path):
        f = tmp_path / "model.bin"
        f.write_bytes(b"model data")
        manifest = IntegrityVerifier.create_manifest(f, artifact_version="2.0")
        assert manifest.artifact_version == "2.0"
        assert len(manifest.checksum) == 64

    def test_verify_manifest(self, tmp_path):
        f = tmp_path / "model.bin"
        f.write_bytes(b"model data")
        manifest = IntegrityVerifier.create_manifest(f)
        assert IntegrityVerifier.verify_manifest(f, manifest) is True

    def test_sha512(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"x")
        cs = IntegrityVerifier.compute_file_checksum(f, algorithm="sha512")
        assert len(cs) == 128

    def test_directory_raises(self, tmp_path):
        with pytest.raises(IntegrityError):
            IntegrityVerifier.compute_file_checksum(tmp_path)

    @pytest.mark.parametrize("algo", ["sha256", "sha384", "sha512", "sha3_256"])
    def test_supported_algorithms(self, tmp_path, algo):
        f = tmp_path / "t.bin"
        f.write_bytes(b"test")
        cs = IntegrityVerifier.compute_file_checksum(f, algorithm=algo)
        assert len(cs) > 0


class TestTradingSymbolValidator:
    pytestmark = pytest.mark.skipif(
        TradingSymbolValidator is None, reason="validation not importable"
    )

    def test_valid_symbol(self):
        v = TradingSymbolValidator(symbol="AAPL")
        assert v.symbol == "AAPL"

    def test_normalizes_to_upper(self):
        v = TradingSymbolValidator(symbol="btc-usd")
        assert v.symbol == "BTC-USD"

    def test_rejects_special_chars(self):
        with pytest.raises(Exception):
            TradingSymbolValidator(symbol="AA;PL")

    def test_rejects_sql_injection(self):
        with pytest.raises(Exception):
            TradingSymbolValidator(symbol="AAPL--")

    def test_rejects_empty(self):
        with pytest.raises(Exception):
            TradingSymbolValidator(symbol="")


class TestNumericRangeValidator:
    pytestmark = pytest.mark.skipif(
        TradingSymbolValidator is None, reason="validation not importable"
    )

    def test_valid_price(self):
        result = NumericRangeValidator.validate_price(100.50)
        assert result == Decimal("100.50")

    def test_price_too_low(self):
        with pytest.raises(ValidationError):
            NumericRangeValidator.validate_price(0.00001)

    def test_price_too_high(self):
        with pytest.raises(ValidationError):
            NumericRangeValidator.validate_price(2_000_000_000)

    def test_price_excessive_precision(self):
        with pytest.raises(ValidationError, match="excessive"):
            NumericRangeValidator.validate_price(1.1234567890)

    def test_valid_quantity(self):
        result = NumericRangeValidator.validate_quantity(100.0)
        assert result > 0

    def test_quantity_too_small(self):
        with pytest.raises(ValidationError):
            NumericRangeValidator.validate_quantity(0.0)

    def test_valid_percentage(self):
        assert NumericRangeValidator.validate_percentage(50.0) == 50.0

    def test_percentage_nan(self):
        with pytest.raises(ValidationError):
            NumericRangeValidator.validate_percentage(float("inf"))


class TestPathValidator:
    pytestmark = pytest.mark.skipif(
        TradingSymbolValidator is None, reason="validation not importable"
    )

    def test_safe_path(self):
        result = PathValidator.validate_safe_path("/data/models/model.bin")
        assert result == "/data/models/model.bin"

    def test_traversal_rejected(self):
        with pytest.raises(ValidationError):
            PathValidator.validate_safe_path("/data/../etc/passwd")

    def test_tilde_rejected(self):
        with pytest.raises(ValidationError):
            PathValidator.validate_safe_path("~/secret")


class TestCommandValidator:
    pytestmark = pytest.mark.skipif(
        TradingSymbolValidator is None, reason="validation not importable"
    )

    def test_valid_command(self):
        result = CommandValidator.validate_command("git status")
        assert result == ["git", "status"]

    def test_not_in_whitelist(self):
        with pytest.raises(ValidationError, match="whitelist"):
            CommandValidator.validate_command("rm -rf /")

    def test_shell_injection(self):
        with pytest.raises(ValidationError):
            CommandValidator.validate_command("git status; rm -rf /")

    def test_empty_command(self):
        with pytest.raises(ValidationError):
            CommandValidator.validate_command("")


class TestSecureRandom:
    pytestmark = pytest.mark.skipif(SecureRandom is None, reason="random not importable")

    def test_randint_range(self):
        for _ in range(50):
            v = SecureRandom.randint(1, 10)
            assert 1 <= v <= 10

    def test_randint_invalid(self):
        with pytest.raises(ValueError):
            SecureRandom.randint(10, 1)

    def test_random_range(self):
        for _ in range(50):
            v = SecureRandom.random()
            assert 0.0 <= v < 1.0

    def test_uniform(self):
        v = SecureRandom.uniform(5.0, 10.0)
        assert 5.0 <= v < 10.0

    def test_uniform_invalid(self):
        with pytest.raises(ValueError):
            SecureRandom.uniform(10.0, 5.0)

    def test_choice(self):
        items = ["a", "b", "c"]
        assert SecureRandom.choice(items) in items

    def test_choice_empty(self):
        with pytest.raises(IndexError):
            SecureRandom.choice([])

    def test_sample(self):
        result = SecureRandom.sample([1, 2, 3, 4, 5], 3)
        assert len(result) == 3
        assert len(set(result)) == 3

    def test_sample_too_large(self):
        with pytest.raises(ValueError):
            SecureRandom.sample([1, 2], 5)

    def test_shuffle(self):
        items = list(range(20))
        original = items.copy()
        SecureRandom.shuffle(items)
        assert sorted(items) == sorted(original)

    def test_token_bytes(self):
        assert len(SecureRandom.token_bytes(32)) == 32
