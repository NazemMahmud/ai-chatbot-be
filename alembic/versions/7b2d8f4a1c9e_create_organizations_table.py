"""
Create organizations table

Revision ID: 7b2d8f4a1c9e ( 2nd revision )
Revises: a3f9c1d7b2e4 ( 1st revision )
Create Date: 2026-02-21

Note: owner_id FK to users is added in 0003 (after users table exists).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7b2d8f4a1c9e"
down_revision: Union[str, Sequence[str], None] = "a3f9c1d7b2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("idx_organizations_deleted_at", "organizations", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_organizations_deleted_at", table_name="organizations")
    op.drop_table("organizations")
