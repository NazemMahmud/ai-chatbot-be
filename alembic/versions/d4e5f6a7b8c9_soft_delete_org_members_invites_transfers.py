"""Add deleted_at for soft-delete on org_members, org_invitations, ownership_transfers

Revision ID: d4e5f6a7b8c9 ( 10th revision )
Revises: b7e2a1c9d4f0 ( 9th revision )
Create Date: 2026-04-08

Preserves membership / invitation / transfer rows for SaaS analytics and recovery.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b7e2a1c9d4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_members",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_org_members_deleted_at", "org_members", ["deleted_at"])

    op.add_column(
        "org_invitations",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_org_invitations_deleted_at", "org_invitations", ["deleted_at"])

    op.add_column(
        "ownership_transfers",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ownership_transfers_deleted_at",
        "ownership_transfers",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ownership_transfers_deleted_at", table_name="ownership_transfers")
    op.drop_column("ownership_transfers", "deleted_at")

    op.drop_index("ix_org_invitations_deleted_at", table_name="org_invitations")
    op.drop_column("org_invitations", "deleted_at")

    op.drop_index("ix_org_members_deleted_at", table_name="org_members")
    op.drop_column("org_members", "deleted_at")
