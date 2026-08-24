from __future__ import annotations

import base64
import datetime
import hashlib
import secrets

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def cert_fingerprint_sha256(cert_pem: str) -> str:
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def generate_self_signed_cert(*, dns_names: list[str] | None = None) -> tuple[str, str, str]:
    """Return private_key_pem, cert_pem, sha256 fingerprint hex.

    Always includes a DNS SAN. Modern Go (Hysteria, recent Xray) rejects
    CN-only certificates with "legacy Common Name field".
    """
    names = [n.strip() for n in (dns_names or []) if n and str(n).strip()]
    if not names:
        raise ValueError("dns_names must contain at least one name for the certificate SAN")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    san = x509.SubjectAlternativeName([x509.DNSName(name) for name in names])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .add_extension(san, critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    fingerprint = cert_fingerprint_sha256(cert_pem)
    return private_pem, cert_pem, fingerprint


def generate_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def to_base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def cert_has_dns_san(cert_pem: str, *, required_name: str | None = None) -> bool:
    """Return True if cert has DNS SANs (optionally requiring a specific name)."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (ValueError, x509.ExtensionNotFound):
        return False
    names = san.get_values_for_type(x509.DNSName)
    if not names:
        return False
    if required_name is None:
        return True
    return required_name in names


def cert_matches_private_key(cert_pem: str, private_key_pem: str) -> bool:
    """Return True if the certificate public key matches the private key."""
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    except (ValueError, TypeError):
        return False
    cert_pub = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return cert_pub == key_pub
