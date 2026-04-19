"""
Role - Dynamic roles created per organization.
Permission - Predefined system permissions (resource.action).
RolePermission - Join table linking roles to permissions.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Permission(Base):
    """
    System-defined permissions. Seeded once, shared across all orgs.
    Example: resource='bots', action='create' → 'bots.create'
    """

    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resource: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_permission_resource_action"),
    )

    @property
    def code(self) -> str:
        return f"{self.resource}.{self.action}"


class Role(Base):
    """
    Organization-scoped roles. Each org can create custom roles.
    is_system (bool) ← "owner" is system role, can't delete
    """

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # Relationships
    organization = relationship("Organization", lazy="selectin")
    permissions = relationship(
        "Permission",
        secondary="role_permissions",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "name", name="uq_role_org_name"
        ),
    )


class RolePermission(Base):
    """Join table: which permissions are assigned to which role."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
