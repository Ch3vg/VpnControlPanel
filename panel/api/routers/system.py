from __future__ import annotations

from fastapi import APIRouter

from panel.api.deps import CurrentUserDep, SettingsDep
from panel.api.schemas.system import ResourceMetricResponse, SystemResourcesResponse
from panel.infrastructure.system.resources import ResourceSnapshot, get_system_resources

router = APIRouter(prefix="/api/v1/system", tags=["system"])


def _metric(snapshot: ResourceSnapshot) -> ResourceMetricResponse:
    return ResourceMetricResponse(
        percent=snapshot.percent,
        used_bytes=snapshot.used_bytes,
        total_bytes=snapshot.total_bytes,
    )


@router.get("/resources", response_model=SystemResourcesResponse)
async def system_resources(
    _user: CurrentUserDep,
    settings: SettingsDep,
) -> SystemResourcesResponse:
    snapshot = await get_system_resources(settings.paths.configs)
    return SystemResourcesResponse(
        cpu=ResourceMetricResponse(percent=snapshot.cpu_percent),
        memory=_metric(snapshot.memory),
        swap=_metric(snapshot.swap),
        disk=_metric(snapshot.disk),
        disk_path=snapshot.disk_path,
    )
