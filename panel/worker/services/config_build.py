from __future__ import annotations

import uuid
from typing import Any

import structlog

from panel.domain.value_objects.config_profile import ConfigProfile
from panel.infrastructure.crypto.config_data import decrypt_config_data_fields, encrypt_config_data_fields
from panel.infrastructure.persistence.repositories.vpn_config import VpnConfigRepository
from panel.infrastructure.vpn.config_builder import ProfileConfigBuilder, previous_for_regenerate
from panel.worker.context import WorkerContext, cert_fingerprint_for_keys

logger = structlog.get_logger(__name__)


async def build_and_persist_version(
    *,
    repo: VpnConfigRepository,
    config_id: uuid.UUID,
    profile: ConfigProfile,
    target_version: int,
    name: str,
    ctx: WorkerContext,
) -> None:
    builder = ProfileConfigBuilder(ctx.settings)
    previous = None
    if target_version > 1:
        snapshot = await repo.get_version_snapshot(config_id, target_version - 1)
        if snapshot is not None:
            encrypted_private = await repo.get_version_private_key(config_id, target_version - 1)
            private_plain = ""
            if encrypted_private and snapshot.profile is ConfigProfile.XRAY_REALITY:
                private_plain = ctx.encryptor.decrypt(encrypted_private)
            config_plain = decrypt_config_data_fields(
                snapshot.config_data,
                builder.sensitive_fields(snapshot.profile),
                ctx.encryptor,
            )
            previous = previous_for_regenerate(
                snapshot.profile,
                config_plain,
                private_key_plain=private_plain,
                public_key=snapshot.public_key,
            )

    result = builder.build(profile, name=name, previous=previous)
    builder.write_files(profile, config_id, result)

    config_data_stored = encrypt_config_data_fields(
        result.config_data,
        builder.sensitive_fields(profile),
        ctx.encryptor,
    )
    private_key_encrypted = ctx.encryptor.encrypt(result.private_key) if result.private_key else ""
    fingerprint = cert_fingerprint_for_keys(
        result.private_key,
        result.public_key,
        result.cert_fingerprint,
    )

    await repo.insert_version(
        config_id=config_id,
        version=target_version,
        port=result.port,
        private_key_encrypted=private_key_encrypted,
        public_key=result.public_key,
        cert_fingerprint=fingerprint,
        config_data=config_data_stored,
    )
