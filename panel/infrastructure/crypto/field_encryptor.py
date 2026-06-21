from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
import base64
import hashlib


class FieldEncryptor:
    def __init__(self, encryption_key: str) -> None:
        digest = hashlib.sha256(encryption_key.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(fernet_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt field") from exc
