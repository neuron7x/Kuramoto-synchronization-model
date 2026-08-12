# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_mfa_module():
    module_path = Path(__file__).resolve().parents[3] / "src/geosync/core/auth/mfa.py"
    spec = importlib.util.spec_from_file_location("_isolated_mfa_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load MFA module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mfa_module = _load_mfa_module()


class _FakeQRImage:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def save(self, buf, format: str) -> None:  # noqa: A002
        assert format == "PNG"
        buf.write(f"QR:{self.payload}".encode("utf-8"))


class _FakePyOTP:
    @staticmethod
    def random_base32() -> str:
        return "TESTBASECODEABCDE"

    class TOTP:
        def __init__(self, secret: str) -> None:
            self.seed = secret

        def provisioning_uri(self, email: str, issuer_name: str) -> str:
            return f"otpauth://totp/{issuer_name}:{email}?k={self.seed}"

        def verify(self, token: str, valid_window: int) -> bool:
            return self.seed == "TESTBASECODEABCDE" and token == "123456" and valid_window == 1


class _BadSecretPyOTP(_FakePyOTP):
    @staticmethod
    def random_base32() -> str:
        return "not-base32"


class _BadUriPyOTP(_FakePyOTP):
    class TOTP(_FakePyOTP.TOTP):
        def provisioning_uri(self, email: str, issuer_name: str) -> str:
            return "invalid-uri"


class _FakeQRCode:
    @staticmethod
    def make(payload: str) -> _FakeQRImage:
        return _FakeQRImage(payload)


class _EmptyQRCode:
    @staticmethod
    def make(payload: str):
        class _EmptyImage:
            @staticmethod
            def save(buf, format: str) -> None:  # noqa: A002
                assert format == "PNG"

        return _EmptyImage()


def test_setup_generates_secret_and_qr_png_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)
    monkeypatch.setattr(mfa_module, "qrcode", _FakeQRCode)

    secret, png_bytes = mfa_module.MFA.setup("analyst@geosync.ai")

    assert secret == "TESTBASECODEABCDE"  # pragma: allowlist secret
    assert png_bytes.startswith(b"QR:otpauth://totp/GeoSync:analyst@geosync.ai")


@pytest.mark.parametrize(
    "bad_email", ["", " analyst@geosync.ai", "analyst@geosync", "analyst geosync.ai"]
)
def test_setup_rejects_malformed_email(monkeypatch: pytest.MonkeyPatch, bad_email: str) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)
    monkeypatch.setattr(mfa_module, "qrcode", _FakeQRCode)

    with pytest.raises(ValueError):
        mfa_module.MFA.setup(bad_email)


def test_setup_requires_optional_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", None)
    monkeypatch.setattr(mfa_module, "qrcode", None)

    with pytest.raises(ImportError, match="pyotp and qrcode"):
        mfa_module.MFA.setup("analyst@geosync.ai")


@pytest.mark.parametrize(
    ("fake_pyotp", "expected_message"),
    [
        (_BadSecretPyOTP, "generated TOTP secret is invalid"),
        (_BadUriPyOTP, "generated provisioning URI is invalid"),
    ],
)
def test_setup_fails_closed_on_invalid_dependency_outputs(
    monkeypatch: pytest.MonkeyPatch,
    fake_pyotp: type,
    expected_message: str,
) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", fake_pyotp)
    monkeypatch.setattr(mfa_module, "qrcode", _FakeQRCode)

    with pytest.raises(RuntimeError, match=expected_message):
        mfa_module.MFA.setup("analyst@geosync.ai")


def test_setup_rejects_empty_qr_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)
    monkeypatch.setattr(mfa_module, "qrcode", _EmptyQRCode)

    with pytest.raises(RuntimeError, match="generated QR payload is empty"):
        mfa_module.MFA.setup("analyst@geosync.ai")


def test_verify_uses_totp_with_drift_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)

    assert mfa_module.MFA.verify("TESTBASECODEABCDE", "123456") is True
    assert mfa_module.MFA.verify("TESTBASECODEABCDE", "000000") is False


@pytest.mark.parametrize(
    ("secret", "token"),
    [
        ("", "123456"),
        ("TESTBASECODEABCDE", ""),
        ("jbswy3dpehpk3pxp", "123456"),
        ("TESTBASECODEABCDE", "12345a"),
        ("TESTBASECODEABCDE", "1234567"),
        (" TESTBASECODEABCDE", "123456"),
    ],
)
def test_verify_rejects_malformed_inputs(
    monkeypatch: pytest.MonkeyPatch,
    secret: str,
    token: str,
) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)

    with pytest.raises(ValueError):
        mfa_module.MFA.verify(secret, token)


def test_verify_rejects_non_string_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", _FakePyOTP)

    with pytest.raises(TypeError):
        mfa_module.MFA.verify(123, "123456")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        mfa_module.MFA.verify("TESTBASECODEABCDE", 123456)  # type: ignore[arg-type]


def test_verify_requires_pyotp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mfa_module, "pyotp", None)

    with pytest.raises(ImportError, match="pyotp"):
        mfa_module.MFA.verify("TESTBASECODEABCDE", "123456")
