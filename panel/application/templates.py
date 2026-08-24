from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from panel.application.audit_service import AuditService
from panel.application.update_config_data import (
    ConfigFormat,
    InvalidConfigData,
    parse_config_content,
)
from panel.config import PanelSettings
from panel.domain.entities.user import User
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.filesystem.writer import atomic_write


class TemplateNotFound(Exception):
    pass


class TemplateAccessDenied(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TemplateInfo:
    profile: str
    template_file: str
    path: str
    format: ConfigFormat
    exists: bool


@dataclass(frozen=True, slots=True)
class TemplateContent:
    profile: str
    template_file: str
    path: str
    format: ConfigFormat
    content: str


def _format_for_path(profile_key: str, path: Path) -> ConfigFormat:
    if profile_key == ConfigProfile.HYSTERIA2.value:
        return "yaml"
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return "json"


def resolve_profile_template_path(settings: PanelSettings, profile_key: str) -> Path:
    if profile_key not in settings.vpn.profiles:
        raise TemplateNotFound(f"Unknown profile: {profile_key}")
    template_file = settings.vpn.profiles[profile_key].template_file
    path = Path(template_file)
    if path.is_file():
        resolved = path.resolve()
    else:
        resolved = (settings.paths.templates / template_file).resolve()
    templates_root = settings.paths.templates.resolve()
    try:
        resolved.relative_to(templates_root)
    except ValueError as exc:
        # Allow absolute template_file only when it resolves to an existing configured file
        # that was explicitly set (still must exist as a file under a known profile).
        if not path.is_absolute() or not resolved.is_file():
            raise TemplateAccessDenied(
                f"Template path escapes templates root: {resolved}",
            ) from exc
    return resolved


def list_templates(settings: PanelSettings) -> list[TemplateInfo]:
    items: list[TemplateInfo] = []
    for profile_key in sorted(settings.vpn.profiles):
        profile = settings.vpn.profiles[profile_key]
        try:
            path = resolve_profile_template_path(settings, profile_key)
        except (TemplateNotFound, TemplateAccessDenied):
            path = (settings.paths.templates / profile.template_file).resolve()
            items.append(
                TemplateInfo(
                    profile=profile_key,
                    template_file=profile.template_file,
                    path=str(path),
                    format=_format_for_path(profile_key, path),
                    exists=False,
                ),
            )
            continue
        items.append(
            TemplateInfo(
                profile=profile_key,
                template_file=profile.template_file,
                path=str(path),
                format=_format_for_path(profile_key, path),
                exists=path.is_file(),
            ),
        )
    return items


class ListTemplatesUseCase:
    def __init__(self, settings: PanelSettings) -> None:
        self._settings = settings

    async def execute(self) -> list[TemplateInfo]:
        return list_templates(self._settings)


class GetTemplateUseCase:
    def __init__(self, settings: PanelSettings) -> None:
        self._settings = settings

    async def execute(self, profile_key: str) -> TemplateContent:
        path = resolve_profile_template_path(self._settings, profile_key)
        if not path.is_file():
            raise TemplateNotFound(f"Template file not found: {path}")
        content = path.read_text(encoding="utf-8")
        fmt = _format_for_path(profile_key, path)
        return TemplateContent(
            profile=profile_key,
            template_file=self._settings.vpn.profiles[profile_key].template_file,
            path=str(path),
            format=fmt,
            content=content,
        )


class UpdateTemplateUseCase:
    def __init__(self, settings: PanelSettings, audit: AuditService) -> None:
        self._settings = settings
        self._audit = audit

    async def execute(self, profile_key: str, user: User, content: str) -> TemplateContent:
        path = resolve_profile_template_path(self._settings, profile_key)
        fmt = _format_for_path(profile_key, path)
        parse_config_content(content, fmt)
        text = content if content.endswith("\n") else content + "\n"
        atomic_write(path, text, mode=0o640)
        await self._audit.log(
            "template.updated",
            {
                "profile": profile_key,
                "path": str(path),
                "format": fmt,
            },
            user_id=user.id,
        )
        return TemplateContent(
            profile=profile_key,
            template_file=self._settings.vpn.profiles[profile_key].template_file,
            path=str(path),
            format=fmt,
            content=text,
        )
