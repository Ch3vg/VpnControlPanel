from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateListItemResponse(BaseModel):
    profile: str
    template_file: str
    path: str
    format: str
    exists: bool


class TemplateListResponse(BaseModel):
    items: list[TemplateListItemResponse]


class TemplateContentResponse(BaseModel):
    profile: str
    template_file: str
    path: str
    format: str
    content: str


class UpdateTemplateRequest(BaseModel):
    content: str = Field(min_length=1)
