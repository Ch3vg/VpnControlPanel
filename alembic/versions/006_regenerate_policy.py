"""vpn_configs.regenerate_policy

Revision ID: 006_regenerate_policy
Revises: 005_share_secure_scope
Create Date: 2026-08-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_regenerate_policy"
down_revision: Union[str, None] = "005_share_secure_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vpn_configs",
        sa.Column(
            "regenerate_policy",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("vpn_configs", "regenerate_policy")
