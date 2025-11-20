from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from core.security import create_server_ssl_context, parse_tls_version


def _write_certificate_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    base = tmp_path / "tls"
    base.mkdir()
    one_day = timedelta(days=1)
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
        .not_valid_before(now - one_day)
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_key, hashes.SHA256())
    )

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    server_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TradePulse Test Service"),
            x509.NameAttribute(NameOID.COMMON_NAME, "tradepulse.test"),
        ]
    )
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_subject)
        .issuer_name(root_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - one_day)
        .not_valid_after(now + timedelta(days=180))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("tradepulse.test"), x509.DNSName("localhost")]
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
    server_cert_path = base / "server.pem"
    server_cert_path.write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    server_key_path = base / "server.key"
    server_key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return root_path, server_cert_path, server_key_path


def test_create_server_ssl_context_enforces_client_ca(tmp_path: Path) -> None:
    _, cert, key = _write_certificate_bundle(tmp_path)

    with pytest.raises(ValueError, match="without a CA bundle"):
        create_server_ssl_context(
            certificate_chain=cert,
            private_key=key,
            require_client_certificate=True,
        )


def test_create_server_ssl_context_supports_optional_client_auth(
    tmp_path: Path,
) -> None:
    ca, cert, key = _write_certificate_bundle(tmp_path)

    context = create_server_ssl_context(
        certificate_chain=cert,
        private_key=key,
        trusted_client_ca=ca,
        require_client_certificate=False,
        minimum_version=parse_tls_version("TLSv1.2"),
    )

    assert context.verify_mode == ssl.CERT_OPTIONAL
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


def test_parse_tls_version_rejects_unknown_version() -> None:
    with pytest.raises(ValueError):
        parse_tls_version("TLSv1.1")
