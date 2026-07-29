from __future__ import annotations

from cryptography import x509

from panel.infrastructure.vpn.crypto_utils import generate_self_signed_cert


def test_generate_self_signed_cert_includes_san() -> None:
    _key, cert_pem, fingerprint = generate_self_signed_cert()
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "vpn-panel" in san.get_values_for_type(x509.DNSName)
    assert len(fingerprint) == 64


def test_generate_self_signed_cert_extra_dns_names() -> None:
    _key, cert_pem, _fp = generate_self_signed_cert(dns_names=["vpn.example.com"])
    cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(
        x509.DNSName,
    )
    assert names[0] == "vpn-panel"
    assert "vpn.example.com" in names
