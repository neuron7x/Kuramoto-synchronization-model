from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from core.security import create_server_ssl_context, create_client_ssl_context, parse_tls_version


def _write_certificate_bundle(tmp_path: Path) -> tuple[Path, Path, Path, rsa.RSAPrivateKey]:
    """Generate CA, server cert/key for testing. Returns root CA path, server cert, server key, and root key."""
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
    return root_path, server_cert_path, server_key_path, root_key


def _write_client_certificate(tmp_path: Path, root_cert_path: Path, root_key: rsa.RSAPrivateKey) -> tuple[Path, Path]:
    """Generate client certificate for mutual TLS testing."""
    base = tmp_path / "tls"
    one_day = timedelta(days=1)
    now = datetime.now(timezone.utc)

    # Load root CA for signing
    root_cert_bytes = root_cert_path.read_bytes()
    root_cert = x509.load_pem_x509_certificate(root_cert_bytes)

    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TradePulse Test Client"),
            x509.NameAttribute(NameOID.COMMON_NAME, "client.tradepulse.test"),
        ]
    )
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(client_subject)
        .issuer_name(root_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - one_day)
        .not_valid_after(now + timedelta(days=180))
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )

    client_cert_path = base / "client.pem"
    client_cert_path.write_bytes(client_cert.public_bytes(serialization.Encoding.PEM))
    client_key_path = base / "client.key"
    client_key_path.write_bytes(
        client_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return client_cert_path, client_key_path


def test_create_server_ssl_context_enforces_client_ca(tmp_path: Path) -> None:
    _, cert, key, _ = _write_certificate_bundle(tmp_path)

    with pytest.raises(ValueError, match="without a CA bundle"):
        create_server_ssl_context(
            certificate_chain=cert,
            private_key=key,
            require_client_certificate=True,
        )


def test_create_server_ssl_context_supports_optional_client_auth(tmp_path: Path) -> None:
    ca, cert, key, _ = _write_certificate_bundle(tmp_path)

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


def test_create_client_ssl_context_basic(tmp_path: Path) -> None:
    """Test creating a basic client SSL context without mutual TLS."""
    ca, _, _, _ = _write_certificate_bundle(tmp_path)

    context = create_client_ssl_context(
        trusted_server_ca=ca,
        minimum_version=parse_tls_version("TLSv1.2"),
    )

    assert context.check_hostname is True
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2
    assert context.maximum_version is ssl.TLSVersion.TLSv1_3


def test_create_client_ssl_context_with_mutual_tls(tmp_path: Path) -> None:
    """Test creating a client SSL context with mutual TLS (client certificate)."""
    ca, _, _, root_key = _write_certificate_bundle(tmp_path)
    client_cert, client_key = _write_client_certificate(tmp_path, ca, root_key)

    context = create_client_ssl_context(
        trusted_server_ca=ca,
        client_certificate=client_cert,
        client_private_key=client_key,
        minimum_version=parse_tls_version("TLSv1.2"),
    )

    assert context.check_hostname is True
    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


def test_create_client_ssl_context_requires_both_cert_and_key(tmp_path: Path) -> None:
    """Test that client certificate requires both cert and key."""
    ca, _, _, root_key = _write_certificate_bundle(tmp_path)
    client_cert, _ = _write_client_certificate(tmp_path, ca, root_key)

    with pytest.raises(ValueError, match="Both client certificate and private key"):
        create_client_ssl_context(
            trusted_server_ca=ca,
            client_certificate=client_cert,
        )


def test_create_client_ssl_context_with_cipher_suites(tmp_path: Path) -> None:
    """Test client SSL context with custom cipher suites."""
    ca, _, _, _ = _write_certificate_bundle(tmp_path)

    context = create_client_ssl_context(
        trusted_server_ca=ca,
        cipher_suites=["ECDHE-RSA-AES256-GCM-SHA384", "ECDHE-RSA-AES128-GCM-SHA256"],
        minimum_version=parse_tls_version("TLSv1.2"),
    )

    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


def test_create_server_ssl_context_with_cipher_suites(tmp_path: Path) -> None:
    """Test server SSL context with custom cipher suites."""
    _, cert, key, _ = _write_certificate_bundle(tmp_path)

    context = create_server_ssl_context(
        certificate_chain=cert,
        private_key=key,
        cipher_suites="ECDHE-RSA-AES256-GCM-SHA384,ECDHE-RSA-AES128-GCM-SHA256",
        minimum_version=parse_tls_version("TLSv1.3"),
    )

    assert context.minimum_version is ssl.TLSVersion.TLSv1_3
    assert context.maximum_version is ssl.TLSVersion.TLSv1_3
