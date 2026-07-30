"""
Create bot_channels and ownership_transfers tables

Revision ID: f5a3b8c2d1e7 ( 8th revision )
Revises: e4b2d7a9c1f3 ( 7th revision )
Create Date: 2026-03-24

bot_channels: Maps a bot to a messaging channel (WhatsApp, Telegram, Widget).
ownership_transfers: Tracks ownership transfer requests between org members.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f5a3b8c2d1e7"
down_revision: Union[str, None] = "e4b2d7a9c1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- bot_channels ---
    op.create_table(
        "bot_channels",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "bot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(50), nullable=False),
        sa.Column(
            "channel_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_bot_channels_bot_id", "bot_channels", ["bot_id"])
    op.create_index("idx_bot_channels_type", "bot_channels", ["channel_type"])

    # --- ownership_transfers ---
    op.create_table(
        "ownership_transfers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_ownership_transfers_org_id",
        "ownership_transfers",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_table("ownership_transfers")
    op.drop_table("bot_channels")
