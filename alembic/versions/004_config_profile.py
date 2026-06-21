"""Revision ID: 004_config_profile
Revises: 003_share_tokens
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_config_profile"
down_revision: Union[str, None] = "003_share_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_configs",
        sa.Column("profile", sa.Text(), nullable=False, server_default="xray-reality"),
    )
    op.alter_column("vpn_configs", "profile", server_default=None)


def downgrade() -> None:
    op.drop_column("vpn_configs", "profile")
