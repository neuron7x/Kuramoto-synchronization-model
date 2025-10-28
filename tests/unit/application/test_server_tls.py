from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pydantic import ValidationError

from application.security.tls import build_api_server_ssl_context
from application.settings import ApiServerSettings, ApiServerTLSSettings


def _generate_server_material(tmp_path: Path) -> tuple[Path, Path, Path]:
    base = tmp_path / "api-tls"
    base.mkdir()
    now = datetime.now(timezone.utc)

    root_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TradePulse Test CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, "TradePulse Root CA"),
        ]
    )
    root_cert = (
        x509.CertificateBuilder()
        .subject_name(root_subject)
        .issuer_name(root_subject)
        .public_key(root_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TradePulse API"),
            x509.NameAttribute(NameOID.COMMON_NAME, "tradepulse.dev"),
        ]
    )
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_subject)
        .issuer_name(root_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("tradepulse.dev"), x509.DNSName("localhost")]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    root_path = base / "root-ca.pem"
    root_path.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    cert_path = base / "server.pem"
    cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    key_path = base / "server.key"
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return root_path, cert_path, key_path


def test_api_server_settings_require_tls_by_default(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ApiServerSettings.model_validate({})

    ca, cert, key = _generate_server_material(tmp_path)
    settings = ApiServerSettings.model_validate(
        {
            "tls": {
                "cert_file": str(cert),
                "key_file": str(key),
                "client_ca_file": str(ca),
                "require_client_certificate": False,
            }
        }
    )
    assert settings.tls is not None


def test_api_server_tls_settings_normalises_sequences(tmp_path: Path) -> None:
    ca, cert, key = _generate_server_material(tmp_path)

    tls = ApiServerTLSSettings(
        cert_file=cert,
        key_file=key,
        client_ca_file=ca,
        cipher_suites="ECDHE-RSA-AES256-GCM-SHA384,  ECDHE-RSA-AES256-GCM-SHA384, ECDHE-RSA-AES128-GCM-SHA256",
        alpn_protocols=["h2", "http/1.1", "h2"],
        require_client_certificate=False,
    )

    assert tls.cipher_suites == (
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES128-GCM-SHA256",
    )
    assert tls.alpn_protocols == ("h2", "http/1.1")


def test_build_api_server_ssl_context(tmp_path: Path) -> None:
    ca, cert, key = _generate_server_material(tmp_path)
    tls = ApiServerTLSSettings(
        cert_file=cert,
        key_file=key,
        client_ca_file=ca,
        require_client_certificate=False,
    )

    context = build_api_server_ssl_context(tls)

    assert context.minimum_version is ssl.TLSVersion.TLSv1_2
    assert context.verify_mode == ssl.CERT_OPTIONAL
