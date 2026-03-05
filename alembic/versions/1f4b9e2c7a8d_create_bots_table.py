"""
Create bots table

Revision ID: 1f4b9e2c7a8d ( 4th revision )
Revises: c8e1a4b7d2f9 ( 3rd revision )
Create Date: 2026-02-13

Complete bots table with all columns:
  name, description, system_prompt, welcome_message, is_active,
  widget_config (JSONB with check constraints), allowed_domains,
  organization_id FK.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1f4b9e2c7a8d"
down_revision: Union[str, Sequence[str], None] = "c8e1a4b7d2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column(
            "widget_config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                "jsonb_build_object("
                "'position','bottom-right',"
                "'theme','light',"
                "'primary_color','#6366f1',"
                "'bubble_icon','chat',"
                "'show_branding',true"
                ")"
            ),
            nullable=True,
        ),
        sa.Column(
            "allowed_domains",
            postgresql.ARRAY(sa.String(length=255)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=True,
        ),
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
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_bots_is_active"), "bots", ["is_active"], unique=False
    )
    op.create_index("idx_bots_deleted_at", "bots", ["deleted_at"])

    # --- widget_config JSONB check constraints ---
    op.create_check_constraint(
        "ck_widget_config_is_object",
        "bots",
        "widget_config IS NULL OR jsonb_typeof(widget_config) = 'object'",
    )
    op.create_check_constraint(
        "ck_widget_config_allowed_keys",
        "bots",
        "widget_config IS NULL OR "
        "(widget_config - 'position' - 'theme' - 'primary_color' "
        "- 'bubble_icon' - 'show_branding') = '{}'::jsonb",
    )
    op.create_check_constraint(
        "ck_widget_config_position",
        "bots",
        "widget_config IS NULL OR NOT (widget_config ? 'position') OR "
        "(widget_config->>'position') IN ('bottom-right','bottom-left')",
    )
    op.create_check_constraint(
        "ck_widget_config_theme",
        "bots",
        "widget_config IS NULL OR NOT (widget_config ? 'theme') OR "
        "(widget_config->>'theme') IN ('light','dark','auto')",
    )
    op.create_check_constraint(
        "ck_widget_config_bubble_icon",
        "bots",
        "widget_config IS NULL OR NOT (widget_config ? 'bubble_icon') OR "
        "(widget_config->>'bubble_icon') IN ('chat')",
    )
    op.create_check_constraint(
        "ck_widget_config_show_branding_type",
        "bots",
        "widget_config IS NULL OR NOT (widget_config ? 'show_branding') OR "
        "jsonb_typeof(widget_config->'show_branding') = 'boolean'",
    )
    op.create_check_constraint(
        "ck_widget_config_primary_color_type",
        "bots",
        "widget_config IS NULL OR NOT (widget_config ? 'primary_color') OR "
        "jsonb_typeof(widget_config->'primary_color') = 'string'",
    )


def downgrade() -> None:
    op.drop_index("idx_bots_deleted_at", table_name="bots")
    op.drop_constraint("ck_widget_config_primary_color_type", "bots")
    op.drop_constraint("ck_widget_config_show_branding_type", "bots")
    op.drop_constraint("ck_widget_config_bubble_icon", "bots")
    op.drop_constraint("ck_widget_config_theme", "bots")
    op.drop_constraint("ck_widget_config_position", "bots")
    op.drop_constraint("ck_widget_config_allowed_keys", "bots")
    op.drop_constraint("ck_widget_config_is_object", "bots")
    op.drop_index(op.f("ix_bots_is_active"), table_name="bots")
    op.drop_table("bots")
