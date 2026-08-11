from __future__ import annotations

import pytest
from cryptography import x509

from panel.infrastructure.vpn.crypto_utils import generate_self_signed_cert


def test_generate_self_signed_cert_requires_dns_names() -> None:
    with pytest.raises(ValueError, match="dns_names"):
        generate_self_signed_cert()


def test_generate_self_signed_cert_includes_san() -> None:
    _key, cert_pem, fingerprint = generate_self_signed_cert(dns_names=["vpn.example.com"])
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "vpn.example.com" in san.get_values_for_type(x509.DNSName)
    assert len(fingerprint) == 64


def test_generate_self_signed_cert_extra_dns_names() -> None:
    _key, cert_pem, _fp = generate_self_signed_cert(dns_names=["vpn.example.com", "alt.example.com"])
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(
        x509.DNSName,
    )
    assert names[0] == "vpn.example.com"
    assert "alt.example.com" in names


def test_cert_has_dns_san_rejects_cn_only() -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    from panel.infrastructure.vpn.crypto_utils import cert_has_dns_san

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "legacy-cn")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    assert cert_has_dns_san(pem) is False
    _k, good_pem, _fp = generate_self_signed_cert(dns_names=["vpn.example.com"])
    assert cert_has_dns_san(good_pem) is True
    assert cert_has_dns_san(good_pem, required_name="vpn.example.com") is True
    assert cert_has_dns_san(good_pem, required_name="other.example") is False
