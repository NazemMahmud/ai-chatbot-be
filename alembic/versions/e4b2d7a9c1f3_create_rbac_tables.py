"""
Create RBAC tables: permissions, roles, role_permissions, org_members, org_invitations

Revision ID: e4b2d7a9c1f3 ( 7th revision )
Revises: 9c1e7a4d2b8f ( 6th revision )
Create Date: 2026-03-19

Tables: permissions, roles, role_permissions, org_members, org_invitations

Owner registers → creates org → seeds 24 permissions + 3 default roles (owner/admin/member)
                                                    ↓
Owner can rename "admin" to "project-admin", create "content-editor", etc.
                                                    ↓
Owner assigns any combination of permissions to each custom role
                                                    ↓
Every API endpoint checks: user → org_member → role → role_permissions → allow/deny

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e4b2d7a9c1f3"
down_revision: Union[str, None] = "9c1e7a4d2b8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- permissions (system-wide, shared across all orgs) ---
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("resource", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.UniqueConstraint("resource", "action", name="uq_permission_resource_action"),
    )

    # --- roles (per organization) ---
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("organization_id", "name", name="uq_role_org_name"),
    )
    op.create_index("ix_roles_organization_id", "roles", ["organization_id"])

    # --- role_permissions (join table) ---
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    # --- org_members ---
    op.create_table(
        "org_members",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_org_members_role_id", "org_members", ["role_id"])

    # --- org_invitations ---
    op.create_table(
        "org_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column(
            "invited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("org_invitations")
    op.drop_table("org_members")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
