from panel.infrastructure.crypto import FieldEncryptor


def test_field_encryptor_roundtrip() -> None:
    encryptor = FieldEncryptor("encryption-key-with-32-chars-min")
    plaintext = "private-key-material"
    ciphertext = encryptor.encrypt(plaintext)
    assert ciphertext != plaintext
    assert encryptor.decrypt(ciphertext) == plaintext
