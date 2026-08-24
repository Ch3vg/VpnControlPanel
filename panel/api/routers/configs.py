from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import CurrentUserDep, SettingsDep, get_db_session, make_audit_service
from panel.api.schemas.configs import (
    ConfigDataResponse,
    ConfigDetailResponse,
    ConfigListResponse,
    ConfigRuntimeListResponse,
    ConfigRuntimeItemResponse,
    ConfigStatusResponse,
    CreateConfigRequest,
    CreateConfigResponse,
    RegenerateAllResponse,
    RegenerateConfigResponse,
    UpdateConfigDataRequest,
    UpdateRegeneratePolicyRequest,
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
    UpdateRegeneratePolicyUseCase,
)
from panel.application.create_config import CreateConfigUseCase
from panel.application.update_config_data import (
    ConfigDataUnavailable,
    GetConfigDataUseCase,
    InvalidConfigData,
    UpdateConfigDataUseCase,
)
from panel.domain.value_objects.regenerate_policy import RegeneratePolicy
from panel.infrastructure.crypto import FieldEncryptor
from panel.application.create_share_link import (
    ConfigNotShareable,
    CreateShareLinkUseCase,
)
from panel.application.share_expiration import InvalidShareRequest
from panel.application.get_config_runtime import GetConfigsRuntimeUseCase
from panel.application.get_config_status import GetConfigStatusUseCase
from panel.application.regenerate_config import ConfigNotRegeneratable, RegenerateConfigUseCase
from panel.application.regenerate_all_configs import RegenerateAllConfigsUseCase
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


@router.get("/runtime", response_model=ConfigRuntimeListResponse)
async def list_configs_runtime(
    _user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
    protocol: VpnProtocolType | None = Query(default=None),
) -> ConfigRuntimeListResponse:
    use_case = GetConfigsRuntimeUseCase(VpnConfigRepository(session), settings)
    items = await use_case.execute(protocol=protocol)
    return ConfigRuntimeListResponse(
        items=[
            ConfigRuntimeItemResponse(
                config_id=str(item.config_id),
                online=item.online,
                systemd_active=item.systemd_active,
                port_listening=item.port_listening,
                detail=item.detail,
            )
            for item in items
        ],
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
        policy_overrides = body.regenerate_policy
        result = await use_case.execute(
            body.name,
            body.protocol,
            body.profile,  # type: ignore[arg-type]
            user,
            regenerate_policy=policy_overrides,
        )
    finally:
        await broker.close()
    return CreateConfigResponse(task_id=result.task_id, config_id=str(result.config_id))


@router.post(
    "/regenerate-all",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RegenerateAllResponse,
)
async def regenerate_all_configs(
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> RegenerateAllResponse:
    broker = HttpBrokerClient(settings.broker)
    try:
        use_case = RegenerateAllConfigsUseCase(
            settings,
            session,
            VpnConfigRepository(session),
            broker,
            make_audit_service(settings, session),
        )
        result = await use_case.execute(user)
    finally:
        await broker.close()
    return RegenerateAllResponse(
        queued=[
            {"config_id": str(item.config_id), "task_id": item.task_id}
            for item in result.queued
        ],
        skipped=[
            {"config_id": str(item.config_id), "reason": item.reason}
            for item in result.skipped
        ],
    )


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
        use_case = GetConfigStatusUseCase(VpnConfigRepository(session), broker, settings)
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
        runtime_online=result.runtime_online,
        runtime_systemd_active=result.runtime_systemd_active,
        runtime_port_listening=result.runtime_port_listening,
        runtime_detail=result.runtime_detail,
    )


@router.get("/{config_id}/config-data", response_model=ConfigDataResponse)
async def get_config_data(
    config_id: uuid.UUID,
    _user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigDataResponse:
    use_case = GetConfigDataUseCase(
        settings,
        VpnConfigRepository(session),
        FieldEncryptor(settings.security.encryption_key),
    )
    try:
        result = await use_case.execute(config_id)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    except ConfigDataUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return ConfigDataResponse(
        config_id=str(result.config_id),
        version=result.version,
        profile=result.profile,
        config_data=result.config_data,
    )


@router.put("/{config_id}/config-data", response_model=ConfigDataResponse)
async def update_config_data(
    config_id: uuid.UUID,
    body: UpdateConfigDataRequest,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigDataResponse:
    use_case = UpdateConfigDataUseCase(
        settings,
        VpnConfigRepository(session),
        FieldEncryptor(settings.security.encryption_key),
        make_audit_service(settings, session),
    )
    try:
        result = await use_case.execute(config_id, user, body.config_data)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    except ConfigDataUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except InvalidConfigData as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    await session.commit()
    return ConfigDataResponse(
        config_id=str(result.config_id),
        version=result.version,
        profile=result.profile,
        config_data=result.config_data,
    )


@router.get("/{config_id}", response_model=ConfigDetailResponse)
async def get_config(
    config_id: uuid.UUID,
    _user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigDetailResponse:
    use_case = GetConfigUseCase(VpnConfigRepository(session))
    try:
        config = await use_case.execute(config_id)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    detail = config_to_detail(config)
    if detail.regenerate_policy is None:
        profile_settings = settings.vpn.profiles.get(config.profile.value)
        detail.regenerate_policy = RegeneratePolicy.for_profile(
            config.profile,
            profile_settings,
        ).to_stored()
    return detail


@router.patch("/{config_id}/regenerate-policy", response_model=ConfigDetailResponse)
async def update_regenerate_policy(
    config_id: uuid.UUID,
    body: UpdateRegeneratePolicyRequest,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> ConfigDetailResponse:
    use_case = UpdateRegeneratePolicyUseCase(
        settings,
        VpnConfigRepository(session),
        make_audit_service(settings, session),
    )
    try:
        config = await use_case.execute(config_id, user, body.regenerate_policy)
    except ConfigNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found") from None
    await session.commit()
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
