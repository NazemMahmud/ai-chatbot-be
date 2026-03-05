"""
Create users and user_tokens tables

Revision ID: c8e1a4b7d2f9 ( 3rd revision )
Revises: 7b2d8f4a1c9e ( 2nd revision )
Create Date: 2026-02-21

Also adds the deferred FK from organizations.owner_id → users.id
(couldn't be added in 7b2d8f4a1c9e because users table didn't exist yet).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c8e1a4b7d2f9"
down_revision: Union[str, Sequence[str], None] = "7b2d8f4a1c9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])

    # --- user_tokens ---
    op.create_table(
        "user_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_tokens_jti"), "user_tokens", ["jti"], unique=True
    )

    # --- deferred FK: organizations.owner_id → users.id ---
    op.create_foreign_key(
        "fk_organizations_owner_id",
        "organizations",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organizations_owner_id", "organizations", type_="foreignkey"
    )
    op.drop_index(op.f("ix_user_tokens_jti"), table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_table("users")
