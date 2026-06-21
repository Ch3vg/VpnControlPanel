from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceMetricResponse(BaseModel):
    percent: float = Field(ge=0, le=100)
    used_bytes: int | None = None
    total_bytes: int | None = None


class SystemResourcesResponse(BaseModel):
    cpu: ResourceMetricResponse
    memory: ResourceMetricResponse
    swap: ResourceMetricResponse
    disk: ResourceMetricResponse
    disk_path: str
