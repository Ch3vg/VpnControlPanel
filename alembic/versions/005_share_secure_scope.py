"""share secure flag and all-configs scope

Revision ID: 005_share_secure_scope
Revises: 004_config_profile
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_share_secure_scope"
down_revision: Union[str, None] = "004_config_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "share_tokens",
        sa.Column("secure", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("share_tokens", "config_id", existing_type=sa.UUID(), nullable=True)
    op.alter_column("share_tokens", "config_version", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_share_tokens_scope",
        "share_tokens",
        "(config_id IS NULL AND config_version IS NULL) "
        "OR (config_id IS NOT NULL AND config_version IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_share_tokens_scope", "share_tokens", type_="check")
    op.alter_column("share_tokens", "config_version", existing_type=sa.Integer(), nullable=False)
    op.alter_column("share_tokens", "config_id", existing_type=sa.UUID(), nullable=False)
    op.drop_column("share_tokens", "secure")
