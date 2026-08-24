"""vpn_configs.share_public_host

Revision ID: 007_share_public_host
Revises: 006_regenerate_policy
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_share_public_host"
down_revision: Union[str, None] = "006_regenerate_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_configs",
        sa.Column("share_public_host", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vpn_configs", "share_public_host")
