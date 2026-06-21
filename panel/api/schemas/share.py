from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateShareLinkRequest(BaseModel):
    is_permanent: bool = True
    expires_at: datetime | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)
    secure: bool = True


class CreateAllShareLinkRequest(BaseModel):
    is_permanent: bool = True
    expires_at: datetime | None = None
    ttl_seconds: int | None = Field(default=None, gt=0)
    secure: bool = True


class CreateShareLinkResponse(BaseModel):
    token: str
    url: str
    secure: bool
    all_configs: bool = False
    config_count: int | None = None
    is_permanent: bool = True
    expires_at: datetime | None = None


class ShareLinkListItem(BaseModel):
    id: uuid.UUID
    all_configs: bool
    config_id: uuid.UUID | None
    config_name: str | None
    secure: bool
    is_permanent: bool
    created_by: str
    created_at: datetime
    expires_at: datetime | None
    access_count: int
    last_accessed_at: datetime | None


class ShareLinkListResponse(BaseModel):
    items: list[ShareLinkListItem]
    total: int
