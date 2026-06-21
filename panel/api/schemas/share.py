from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateShareLinkRequest(BaseModel):
    is_permanent: bool = True
    expires_at: datetime | None = None


class CreateShareLinkResponse(BaseModel):
    token: str
    url: str
