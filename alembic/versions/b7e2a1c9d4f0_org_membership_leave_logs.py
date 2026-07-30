"""org_membership_leave_logs audit table

Revision ID: b7e2a1c9d4f0 ( 9th revision )
Revises: f5a3b8c2d1e7 ( 8th revision )
Create Date: 2026-04-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e2a1c9d4f0"
down_revision: Union[str, None] = "f5a3b8c2d1e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_membership_leave_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("role_id", sa.UUID(), nullable=True),
        sa.Column("voluntary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_org_membership_leave_logs_user_id",
        "org_membership_leave_logs",
        ["user_id"],
    )
    op.create_index(
        "ix_org_membership_leave_logs_organization_id",
        "org_membership_leave_logs",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_membership_leave_logs_organization_id",
        table_name="org_membership_leave_logs",
    )
    op.drop_index(
        "ix_org_membership_leave_logs_user_id",
        table_name="org_membership_leave_logs",
    )
    op.drop_table("org_membership_leave_logs")
