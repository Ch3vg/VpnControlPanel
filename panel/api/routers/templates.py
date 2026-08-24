from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from panel.api.deps import CurrentUserDep, SettingsDep, get_db_session, make_audit_service
from panel.api.schemas.templates import (
    TemplateContentResponse,
    TemplateListItemResponse,
    TemplateListResponse,
    UpdateTemplateRequest,
)
from panel.application.templates import (
    GetTemplateUseCase,
    ListTemplatesUseCase,
    TemplateAccessDenied,
    TemplateNotFound,
    UpdateTemplateUseCase,
)
from panel.application.update_config_data import InvalidConfigData

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    _user: CurrentUserDep,
    settings: SettingsDep,
) -> TemplateListResponse:
    items = await ListTemplatesUseCase(settings).execute()
    return TemplateListResponse(
        items=[
            TemplateListItemResponse(
                profile=item.profile,
                template_file=item.template_file,
                path=item.path,
                format=item.format,
                exists=item.exists,
            )
            for item in items
        ],
    )


@router.get("/{profile}", response_model=TemplateContentResponse)
async def get_template(
    profile: str,
    _user: CurrentUserDep,
    settings: SettingsDep,
) -> TemplateContentResponse:
    try:
        result = await GetTemplateUseCase(settings).execute(profile)
    except TemplateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except TemplateAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except InvalidConfigData as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    return TemplateContentResponse(
        profile=result.profile,
        template_file=result.template_file,
        path=result.path,
        format=result.format,
        content=result.content,
    )


@router.put("/{profile}", response_model=TemplateContentResponse)
async def update_template(
    profile: str,
    body: UpdateTemplateRequest,
    user: CurrentUserDep,
    settings: SettingsDep,
    session: AsyncSession = Depends(get_db_session),
) -> TemplateContentResponse:
    use_case = UpdateTemplateUseCase(settings, make_audit_service(settings, session))
    try:
        result = await use_case.execute(profile, user, body.content)
    except TemplateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    except TemplateAccessDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except InvalidConfigData as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    await session.commit()
    return TemplateContentResponse(
        profile=result.profile,
        template_file=result.template_file,
        path=result.path,
        format=result.format,
        content=result.content,
    )
