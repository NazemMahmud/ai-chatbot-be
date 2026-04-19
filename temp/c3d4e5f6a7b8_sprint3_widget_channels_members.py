"""Sprint 3: widget config, bot channels, org members, org invitations

Add widget_config and allowed_domains to bots table.
Create bot_channels, org_members, and org_invitations tables.

Revision ID: c3d4e5f6a7b8
Revises: b1a2c3d4e5f6
Create Date: 2026-03-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY


# revision identifiers
revision = "c3d4e5f6a7b8"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add widget_config and allowed_domains to bots
    op.add_column(
        "bots",
        sa.Column(
            "widget_config",
            JSONB,
            server_default=sa.text(
                """'{"position":"bottom-right","theme":"light","primary_color":"#6366f1","bubble_icon":"chat","show_branding":true}'::jsonb"""
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "bots",
        sa.Column(
            "allowed_domains",
            ARRAY(sa.String(255)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=True,
        ),
    )

    # 2. Create bot_channels table
    op.create_table(
        "bot_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("bot_id", UUID(as_uuid=True), sa.ForeignKey("bots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_type", sa.String(50), nullable=False),
        sa.Column("channel_config", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_bot_channels_bot_id", "bot_channels", ["bot_id"])
    op.create_index("idx_bot_channels_type", "bot_channels", ["channel_type"])

    # 3. Create org_members table
    op.create_table(
        "org_members",
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'member'")),
        sa.Column("invited_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_org_members_user", "org_members", ["user_id"])
    op.create_index("idx_org_members_role", "org_members", ["organization_id", "role"])

    # 4. Create org_invitations table
    op.create_table(
        "org_invitations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default=sa.text("'member'")),
        sa.Column("token", sa.Text(), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_org_invitations_token", "org_invitations", ["token"])
    op.create_index("idx_org_invitations_org", "org_invitations", ["organization_id"])

    # 5. Backfill: create OrgMember rows for existing org owners
    op.execute("""
        INSERT INTO org_members (organization_id, user_id, role)
        SELECT o.id, o.owner_id, 'owner'
        FROM organizations o
        WHERE NOT EXISTS (
            SELECT 1 FROM org_members om
            WHERE om.organization_id = o.id AND om.user_id = o.owner_id
        )
    """)


def downgrade() -> None:
    op.drop_table("org_invitations")
    op.drop_table("org_members")
    op.drop_table("bot_channels")
    op.drop_column("bots", "allowed_domains")
    op.drop_column("bots", "widget_config")
