from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from panel.domain.entities.vpn_config import VpnConfig, VpnConfigVersion
from panel.domain.value_objects.config_profile import ConfigProfile
from panel.domain.value_objects.config_status import ConfigStatus
from panel.domain.value_objects.protocol import VpnProtocolType
from panel.infrastructure.persistence.models import VpnConfigModel, VpnConfigVersionModel


@dataclass(frozen=True, slots=True)
class ConfigListResult:
    items: list[VpnConfig]
    total: int


def _version_to_entity(model: VpnConfigVersionModel) -> VpnConfigVersion:
    return VpnConfigVersion(
        id=model.id,
        config_id=model.config_id,
        version=model.version,
        port=model.port,
        public_key=model.public_key,
        cert_fingerprint=model.cert_fingerprint,
        created_at=model.created_at,
    )


def _config_to_entity(
    model: VpnConfigModel,
    *,
    version_model: VpnConfigVersionModel | None = None,
) -> VpnConfig:
    version_detail = _version_to_entity(version_model) if version_model else None
    return VpnConfig(
        id=model.id,
        name=model.name,
        protocol=VpnProtocolType(model.protocol),
        profile=ConfigProfile(model.profile),
        status=ConfigStatus(model.status),
        current_version=model.current_version,
        last_task_id=model.last_task_id,
        error_message=model.error_message,
        is_active=model.is_active,
        created_by=model.created_by,
        updated_by=model.updated_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
        current_version_detail=version_detail,
    )


@dataclass(frozen=True, slots=True)
class ConfigVersionSnapshot:
    config_id: uuid.UUID
    protocol: VpnProtocolType
    profile: ConfigProfile
    name: str
    version: int
    port: int
    public_key: str
    cert_fingerprint: str
    config_data: dict


class VpnConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(
        self,
        *,
        protocol: VpnProtocolType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ConfigListResult:
        filters = [VpnConfigModel.is_active.is_(True)]
        if protocol is not None:
            filters.append(VpnConfigModel.protocol == protocol.value)

        total_result = await self._session.execute(
            select(func.count()).select_from(VpnConfigModel).where(*filters),
        )
        total = int(total_result.scalar_one())

        result = await self._session.execute(
            select(VpnConfigModel)
            .where(*filters)
            .order_by(VpnConfigModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        items = [_config_to_entity(model) for model in result.scalars().all()]
        return ConfigListResult(items=items, total=total)

    async def get_by_id(self, config_id: uuid.UUID, *, active_only: bool = True) -> VpnConfig | None:
        filters = [VpnConfigModel.id == config_id]
        if active_only:
            filters.append(VpnConfigModel.is_active.is_(True))

        result = await self._session.execute(select(VpnConfigModel).where(*filters))
        model = result.scalar_one_or_none()
        if model is None:
            return None

        version_model = await self._load_current_version(model)
        return _config_to_entity(model, version_model=version_model)

    async def soft_delete(self, config_id: uuid.UUID, updated_by: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(VpnConfigModel).where(
                VpnConfigModel.id == config_id,
                VpnConfigModel.is_active.is_(True),
            ),
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.is_active = False
        model.updated_by = updated_by
        model.updated_at = datetime.now(UTC)
        return True

    async def create_pending(
        self,
        *,
        name: str,
        protocol: VpnProtocolType,
        profile: ConfigProfile,
        created_by: uuid.UUID,
    ) -> VpnConfig:
        model = VpnConfigModel(
            name=name,
            protocol=protocol.value,
            profile=profile.value,
            status=ConfigStatus.PENDING.value,
            current_version=None,
            is_active=True,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(model)
        await self._session.flush()
        return _config_to_entity(model)

    async def set_last_task_id(self, config_id: uuid.UUID, task_id: str) -> None:
        model = await self._get_model(config_id)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        model.last_task_id = task_id
        model.updated_at = datetime.now(UTC)

    async def mark_processing(self, config_id: uuid.UUID) -> None:
        model = await self._get_model(config_id, active_only=False)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        model.status = ConfigStatus.PROCESSING.value
        model.error_message = None
        model.updated_at = datetime.now(UTC)

    async def mark_active(self, config_id: uuid.UUID, version: int) -> None:
        model = await self._get_model(config_id, active_only=False)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        model.status = ConfigStatus.ACTIVE.value
        model.current_version = version
        model.error_message = None
        model.updated_at = datetime.now(UTC)

    async def mark_failed(self, config_id: uuid.UUID, error_message: str) -> None:
        model = await self._get_model(config_id, active_only=False)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        model.status = ConfigStatus.FAILED.value
        model.error_message = error_message[:2000]
        model.updated_at = datetime.now(UTC)

    async def has_version(self, config_id: uuid.UUID, version: int) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(VpnConfigVersionModel)
            .where(
                VpnConfigVersionModel.config_id == config_id,
                VpnConfigVersionModel.version == version,
            ),
        )
        return int(result.scalar_one()) > 0

    async def list_used_ports(self, *, exclude_config_id: uuid.UUID | None = None) -> set[int]:
        stmt = select(VpnConfigVersionModel.port).distinct()
        if exclude_config_id is not None:
            stmt = stmt.where(VpnConfigVersionModel.config_id != exclude_config_id)
        result = await self._session.execute(stmt)
        return {int(row[0]) for row in result.all()}

    async def insert_version(
        self,
        *,
        config_id: uuid.UUID,
        version: int,
        port: int,
        private_key_encrypted: str,
        public_key: str,
        cert_fingerprint: str,
        config_data: dict,
    ) -> None:
        self._session.add(
            VpnConfigVersionModel(
                config_id=config_id,
                version=version,
                port=port,
                private_key=private_key_encrypted,
                public_key=public_key,
                cert_fingerprint=cert_fingerprint,
                config_data=config_data,
            ),
        )
        await self._session.flush()

    async def _get_model(
        self,
        config_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> VpnConfigModel | None:
        filters = [VpnConfigModel.id == config_id]
        if active_only:
            filters.append(VpnConfigModel.is_active.is_(True))
        result = await self._session.execute(select(VpnConfigModel).where(*filters))
        return result.scalar_one_or_none()

    async def _load_current_version(self, model: VpnConfigModel) -> VpnConfigVersionModel | None:
        if model.current_version is None:
            return None
        result = await self._session.execute(
            select(VpnConfigVersionModel).where(
                VpnConfigVersionModel.config_id == model.id,
                VpnConfigVersionModel.version == model.current_version,
            ),
        )
        return result.scalar_one_or_none()

    async def prepare_regenerate(self, config_id: uuid.UUID, updated_by: uuid.UUID) -> VpnConfig:
        model = await self._get_model(config_id)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        if model.current_version is None:
            raise ValueError("Config has no version to regenerate from")
        if model.status in (ConfigStatus.PENDING.value, ConfigStatus.PROCESSING.value):
            raise ValueError("Config is not ready for regenerate")
        model.status = ConfigStatus.PENDING.value
        model.error_message = None
        model.updated_by = updated_by
        model.updated_at = datetime.now(UTC)
        return _config_to_entity(model)

    async def get_regenerate_context(
        self,
        config_id: uuid.UUID,
    ) -> tuple[VpnProtocolType, ConfigProfile, str, int]:
        model = await self._get_model(config_id)
        if model is None:
            raise ValueError(f"Config not found: {config_id}")
        if model.current_version is None:
            raise ValueError("Config has no version to regenerate from")
        return (
            VpnProtocolType(model.protocol),
            ConfigProfile(model.profile),
            model.name,
            model.current_version + 1,
        )

    async def get_version_snapshot(
        self,
        config_id: uuid.UUID,
        version: int,
    ) -> ConfigVersionSnapshot | None:
        config_model = await self._get_model(config_id, active_only=False)
        if config_model is None:
            return None
        result = await self._session.execute(
            select(VpnConfigVersionModel).where(
                VpnConfigVersionModel.config_id == config_id,
                VpnConfigVersionModel.version == version,
            ),
        )
        version_model = result.scalar_one_or_none()
        if version_model is None:
            return None
        return ConfigVersionSnapshot(
            config_id=config_id,
            protocol=VpnProtocolType(config_model.protocol),
            profile=ConfigProfile(config_model.profile),
            name=config_model.name,
            version=version_model.version,
            port=version_model.port,
            public_key=version_model.public_key,
            cert_fingerprint=version_model.cert_fingerprint,
            config_data=dict(version_model.config_data),
        )

    async def list_current_version_snapshots(self) -> list[ConfigVersionSnapshot]:
        result = await self._session.execute(
            select(VpnConfigModel).where(
                VpnConfigModel.is_active.is_(True),
                VpnConfigModel.status == ConfigStatus.ACTIVE.value,
                VpnConfigModel.current_version.is_not(None),
            ).order_by(VpnConfigModel.created_at.asc()),
        )
        snapshots: list[ConfigVersionSnapshot] = []
        for model in result.scalars():
            snapshot = await self.get_version_snapshot(model.id, model.current_version)
            if snapshot is not None:
                snapshots.append(snapshot)
        return snapshots

    async def get_version_private_key(self, config_id: uuid.UUID, version: int) -> str | None:
        result = await self._session.execute(
            select(VpnConfigVersionModel.private_key).where(
                VpnConfigVersionModel.config_id == config_id,
                VpnConfigVersionModel.version == version,
            ),
        )
        return result.scalar_one_or_none()

    async def create_with_version(
        self,
        *,
        name: str,
        protocol: VpnProtocolType,
        status: ConfigStatus,
        created_by: uuid.UUID,
        version: VpnConfigVersionModel,
    ) -> VpnConfig:
        """Тестовый/внутренний helper; публичный POST /configs — этап 3."""
        config_model = VpnConfigModel(
            name=name,
            protocol=protocol.value,
            profile=ConfigProfile.default_for_protocol(protocol.value).value,
            status=status.value,
            current_version=version.version,
            is_active=True,
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(config_model)
        await self._session.flush()
        version.config_id = config_model.id
        self._session.add(version)
        await self._session.flush()
        return _config_to_entity(config_model, version_model=version)
