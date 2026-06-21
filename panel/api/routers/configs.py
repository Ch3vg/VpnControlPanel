from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import CurrentUserDep, SettingsDep, get_db_session, make_audit_service
from panel.api.schemas.configs import (
    ConfigDetailResponse,
    ConfigListResponse,
    ConfigStatusResponse,
    CreateConfigRequest,
    CreateConfigResponse,
    RegenerateConfigResponse,
    config_to_detail,
    config_to_list_item,
)
from panel.api.schemas.share import CreateShareLinkRequest, CreateShareLinkResponse
from panel.application.configs import (
    ConfigNotFound,
    DeleteConfigUseCase,
    GetConfigUseCase,
    ListConfigsQuery,
    ListConfigsUseCase,
)
from panel.application.create_config import CreateConfigUseCase
from panel.application.create_share_link import (
    ConfigNotShareable,
    CreateShareLinkUseCase,
)
from panel.application.share_expiration import InvalidShareRequest
from panel.application.get_config_status import GetConfigStatusUseCase
from panel.application.regenerate_config import ConfigNotRegeneratable, RegenerateConfigUseCase
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.broker import HttpBrokerClient
from panel.infrastructure.persistence.repositories.share_token import ShareTokenRepository
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository

router = APIRouter(prefix="/api/v1/configs", tags=["configs"])


@router.get("", response_model=ConfigListResponse)
async def list_configs(
    _user: CurrentUserDep,
    session: AsyncSession = Depends(get_db_session),
    protocol: VpnProtocolType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ConfigListResponse:
    use_case = ListConfigsUseCase(VpnConfigRepository(session))
    result = await use_case.execute(
        ListConfigsQuery(protocol=protocol, limit=limit, offset=offset),
    )
    return ConfigListResponse(
        items=[config_to_list_item(item) for item in result.items],
        total=result.total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=CreateConfigResponse)
async def create_config(
    body: CreateConfigRequest,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> CreateConfigResponse:
    broker = HttpBrokerClient(settings.broker)
    try:
        use_case = CreateConfigUseCase(
            settings,
            session,
            VpnConfigRepository(session),
            broker,
            make_audit_service(settings, session),
        )
        result = await use_case.execute(body.name, body.protocol, body.profile, user)
    finally:
        await broker.close()
    return CreateConfigResponse(task_id=result.task_id, config_id=str(result.config_id))


@router.post(
    "/{config_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegenerateConfigResponse,
)
async def regenerate_config(
    config_id: uuid.UUID,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> RegenerateConfigResponse:
    broker = HttpBrokerClient(settings.broker)
    try:
        use_case = RegenerateConfigUseCase(
            settings,
            session,
            VpnConfigRepository(session),
            broker,
            make_audit_service(settings, session),
        )
        try:
            result = await use_case.execute(config_id, user)
        except ConfigNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
        except ConfigNotRegeneratable as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    finally:
        await broker.close()
    return RegenerateConfigResponse(task_id=result.task_id, config_id=str(result.config_id))


@router.post(
    "/{config_id}/share",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateShareLinkResponse,
)
async def create_share_link(
    config_id: uuid.UUID,
    body: CreateShareLinkRequest,
    request: Request,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> CreateShareLinkResponse:
    use_case = CreateShareLinkUseCase(
        VpnConfigRepository(session),
        ShareTokenRepository(session),
        make_audit_service(settings, session),
    )
    try:
        result = await use_case.execute(
            config_id,
            user,
            secure=body.secure,
            is_permanent=body.is_permanent,
            expires_at=body.expires_at,
            ttl_seconds=body.ttl_seconds,
            public_base_url=str(request.base_url).rstrip("/"),
        )
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    except ConfigNotShareable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except InvalidShareRequest as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    await session.commit()
    return CreateShareLinkResponse(
        token=result.token,
        url=result.url,
        secure=result.secure,
        all_configs=False,
        is_permanent=result.is_permanent,
        expires_at=result.expires_at,
    )


@router.get("/{config_id}/status", response_model=ConfigStatusResponse)
async def get_config_status(
    config_id: uuid.UUID,
    _user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigStatusResponse:
    broker = HttpBrokerClient(settings.broker)
    try:
        use_case = GetConfigStatusUseCase(VpnConfigRepository(session), broker)
        try:
            result = await use_case.execute(config_id)
        except ConfigNotFound:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    finally:
        await broker.close()
    return ConfigStatusResponse(
        config_id=str(result.config_id),
        status=result.status,
        task_id=result.task_id,
        task_status=result.task_status,
        retries=result.retries,
        max_retries=result.max_retries,
        error_message=result.error_message,
    )


@router.get("/{config_id}", response_model=ConfigDetailResponse)
async def get_config(
    config_id: uuid.UUID,
    _user: CurrentUserDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigDetailResponse:
    use_case = GetConfigUseCase(VpnConfigRepository(session))
    try:
        config = await use_case.execute(config_id)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    return config_to_detail(config)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    config_id: uuid.UUID,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> None:
    use_case = DeleteConfigUseCase(
        VpnConfigRepository(session),
        make_audit_service(settings, session),
        settings,
    )
    try:
        await use_case.execute(config_id, user)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    await session.commit()
