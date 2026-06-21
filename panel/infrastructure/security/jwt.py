from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from panel.config import SecuritySettings


class JwtError(Exception):
    pass


class JwtService:
    def __init__(self, settings: SecuritySettings) -> None:
        self._settings = settings

    def create_access_token(self, user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.jwt_expire_minutes),
        }
        return jwt.encode(
            payload,
            self._settings.secret_key,
            algorithm=self._settings.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(
                token,
                self._settings.secret_key,
                algorithms=[self._settings.jwt_algorithm],
            )
        except jwt.PyJWTError as exc:
            raise JwtError("Invalid token") from exc
        sub = payload.get("sub")
        if not sub:
            raise JwtError("Invalid token")
        return uuid.UUID(str(sub))
