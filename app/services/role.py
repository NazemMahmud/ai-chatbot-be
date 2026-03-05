"""
RoleService - Manage dynamic roles and permissions per organization.
"""
import uuid
import logging

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select, delete, insert, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Permission, Role, RolePermission, OrgMember
from app.models.organization import Organization
from app.services.permissions import ALL_PERMISSIONS, DEFAULT_ROLES

logger = logging.getLogger(__name__)


class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Seed system permissions (run once or idempotent)
    # ------------------------------------------------------------------

    async def seed_permissions(self) -> dict[str, uuid.UUID]:
        """
        Ensure all system permissions exist. Returns a map of
        'resource.action' → permission_id.
        """
        result = await self.db.execute(select(Permission))
        existing = {p.code: p for p in result.scalars().all()}
        missing  = [
            dict(id=uuid.uuid4(), resource=r.value, action=a.value, description=d)
            for r, a, d in ALL_PERMISSIONS
            if f"{r.value}.{a.value}" not in existing
        ]

        if missing:
            await self.db.execute(insert(Permission).values(missing))
            await self.db.flush()

            result = await self.db.execute(select(Permission))
            existing = {p.code: p for p in result.scalars().all()}

        return {code: p.id for code, p in existing.items()}


    async def create_default_roles(
        self, organization_id: uuid.UUID
    ) -> dict[str, Role]:
        """
        Create default roles (owner, admin, member) for a new org.
        Returns map of role_name → Role object.

        3 DB calls: 1 seed_permissions, 1 bulk insert roles, 1 bulk insert role_permissions.
        """
        perm_map = await self.seed_permissions()
        all_perm_ids = list(perm_map.values())

        # 1. Build all Role objects in memory
        roles: dict[str, Role] = {}
        for role_name, (description, is_system, _) in DEFAULT_ROLES.items():
            role = Role(
                organization_id=organization_id,
                name=role_name,
                description=description,
                is_system=is_system,
            )
            self.db.add(role)
            roles[role_name] = role

        # Single flush → all roles get IDs
        await self.db.flush()

        # 2. Build all RolePermission rows in memory
        rp_rows: list[dict] = []
        for role_name, (_, __, perm_codes) in DEFAULT_ROLES.items():
            role_id = roles[role_name].id
            target_ids = (
                all_perm_ids
                if "*" in perm_codes
                else [perm_map[c] for c in perm_codes if c in perm_map]
            )
            rp_rows.extend(
                dict(role_id=role_id, permission_id=pid) for pid in target_ids
            )

        # Single bulk insert for all role-permission mappings
        if rp_rows:
            await self.db.execute(insert(RolePermission).values(rp_rows))
            await self.db.flush()

        return roles

    # ------------------------------------------------------------------
    # List roles for an organization
    # ------------------------------------------------------------------

    async def list_roles(self, organization_id: uuid.UUID) -> list[Role]:
        result = await self.db.execute(
            select(Role)
            .where(
                Role.organization_id == organization_id,
                Role.deleted_at.is_(None),
            )
            .order_by(Role.is_system.desc(), Role.name)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Get single role
    # ------------------------------------------------------------------

    async def get_role(
        self, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Role:
        result = await self.db.execute(
            select(Role).where(
                Role.id == role_id,
                Role.organization_id == organization_id,
                Role.deleted_at.is_(None),
            )
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
            )
        return role


    async def create_role(
        self,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        permission_ids: list[uuid.UUID],
    ) -> Role:
        name_lower = name.lower()

        # Check if role with same name exists (active or soft-deleted)
        existing = await self._get_role_by_name(organization_id, name_lower)

        if existing and existing.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A role named '{name}' already exists",
            )

        if existing and existing.deleted_at is not None:
            # Undelete: reuse the soft-deleted row
            existing.description = description
            existing.deleted_at = None
            await self._replace_permissions(existing.id, permission_ids)
            await self.db.flush()
            return await self.get_role(existing.id, organization_id)

        role = Role(
            organization_id=organization_id,
            name=name_lower,
            description=description,
            is_system=False,
        )
        self.db.add(role)
        await self.db.flush()

        await self._assign_permissions(role.id, permission_ids)
        return await self.get_role(role.id, organization_id)

    # ------------------------------------------------------------------
    # Update role
    # ------------------------------------------------------------------

    async def update_role(
        self,
        role_id: uuid.UUID,
        organization_id: uuid.UUID,
        name: str | None,
        description: str | None,
        permission_ids: list[uuid.UUID] | None,
    ) -> Role:
        role = await self.get_role(role_id, organization_id)

        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System roles cannot be modified",
            )

        if name is not None:
            name_lower = name.lower()
            if name_lower != role.name:
                await self._check_name_or_undelete(
                    organization_id, name_lower, exclude_role_id=role_id
                )
                role.name = name_lower

        if description is not None:
            role.description = description

        if permission_ids is not None:
            await self._replace_permissions(role_id, permission_ids)

        await self.db.flush()
        return await self.get_role(role_id, organization_id)

    # ------------------------------------------------------------------
    # Delete role
    # ------------------------------------------------------------------

    async def delete_role(
        self, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        role = await self.get_role(role_id, organization_id)

        if role.is_system:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="System roles cannot be deleted",
            )

        # Reassign any members on this role to "member" (least-access default)
        await self._reassign_members_to_default(role_id, organization_id)

        # Soft delete — keep role_permissions intact for audit
        role.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def _reassign_members_to_default(
        self, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Reassign all members of a given role to the 'member' role (least access)."""
        member_role = await self._get_default_member_role(organization_id)

        await self.db.execute(
            update(OrgMember)
            .where(
                OrgMember.organization_id == organization_id,
                OrgMember.role_id == role_id,
                OrgMember.deleted_at.is_(None),
            )
            .values(role_id=member_role.id)
        )
        await self.db.flush()

    async def _get_default_member_role(
        self, organization_id: uuid.UUID
    ) -> Role:
        """Get the 'member' role — the least-access default role for an org."""
        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.name == "member",
                Role.deleted_at.is_(None),
            )
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Default 'member' role not found for organization",
            )
        return role

    # ------------------------------------------------------------------
    # Permission check — core of the RBAC system
    # ------------------------------------------------------------------

    async def user_has_permission(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        resource: str,
        action: str,
    ) -> bool:
        """Check if a user has a specific permission in their org."""
        # Get user's role in org
        # todo: later shift this to organization membber or related service to get organization member info, get could be dynamic
        member_result = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == organization_id,
                OrgMember.user_id == user_id,
                OrgMember.deleted_at.is_(None),
            )
        )
        member = member_result.scalar_one_or_none()

        if not member:
            # Legacy fallback: user registered before RBAC was implemented.
            # Check if user is the org owner and auto-provision their membership.
            org_result = await self.db.execute(
                select(Organization).where(
                    Organization.id == organization_id,
                    Organization.owner_id == user_id,
                    Organization.deleted_at.is_(None),
                )
            )
            org = org_result.scalar_one_or_none()
            if not org:
                return False

            # create default roles if missing, then add owner as OrgMember
            await self._auto_provision_owner(organization_id, user_id)
            return True

        # Get role with permissions (exclude soft-deleted)
        role_result = await self.db.execute(
            select(Role).where(
                Role.id == member.role_id,
                Role.deleted_at.is_(None),
            )
        )
        role = role_result.scalar_one_or_none()
        if not role:
            return False

        # System owner role has all permissions
        if role.is_system and role.name == "owner":
            return True

        # Check if the permission exists in role's permissions
        for perm in role.permissions:
            if perm.resource == resource and perm.action == action:
                return True

        return False

    # ------------------------------------------------------------------
    # List all system permissions
    # ------------------------------------------------------------------

    async def list_permissions(self) -> list[Permission]:
        result = await self.db.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return list(result.scalars().all())

    async def list_permissions_grouped(self) -> dict[str, list[Permission]]:
        """Return permissions grouped by resource for picker UI."""
        permissions = await self.list_permissions()
        grouped: dict[str, list[Permission]] = {}
        for p in permissions:
            grouped.setdefault(p.resource, []).append(p)
        return grouped

    # ------------------------------------------------------------------
    # Get owner role for an org
    # ------------------------------------------------------------------

    async def get_owner_role(self, organization_id: uuid.UUID) -> Role:
        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.is_system.is_(True),
                Role.name == "owner",
                Role.deleted_at.is_(None),
            )
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Owner role not found for organization",
            )
        return role

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _auto_provision_owner(
        self, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """
        One-time self-healing for pre-RBAC users.
        Creates default roles (if missing) and adds the org owner as OrgMember.
        """
        # Check if roles already exist for this org
        existing_roles = await self.db.execute(
            select(exists().where(
                Role.organization_id == organization_id,
                Role.deleted_at.is_(None),
            ))
        )
        if not existing_roles.scalar():
            logger.info(f"Auto-provisioning default roles for org {organization_id}")
            await self.create_default_roles(organization_id)

        owner_role = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.is_system.is_(True),
                Role.name == "owner",
                Role.deleted_at.is_(None),
            )
        )
        role = owner_role.scalar_one_or_none()
        if not role:
            logger.error(f"Owner role not found after provisioning for org {organization_id}")
            return

        existing_m = await self.db.execute(
            select(OrgMember).where(
                OrgMember.organization_id == organization_id,
                OrgMember.user_id == user_id,
            )
        )
        existing_row = existing_m.scalar_one_or_none()
        if existing_row:
            if existing_row.deleted_at is not None:
                existing_row.deleted_at = None
                existing_row.role_id = role.id
                await self.db.flush()
            return

        self.db.add(OrgMember(
            organization_id=organization_id,
            user_id=user_id,
            role_id=role.id,
        ))
        await self.db.flush()

    async def _get_role_by_name(
        self, organization_id: uuid.UUID, name: str
    ) -> Role | None:
        """Fetch role by org + name (case-insensitive), including soft-deleted."""
        result = await self.db.execute(
            select(Role).where(
                Role.organization_id == organization_id,
                func.lower(Role.name) == name.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def _check_name_or_undelete(
        self,
        organization_id: uuid.UUID,
        name: str,
        exclude_role_id: uuid.UUID | None = None,
    ) -> None:
        """
        For update: if target name is taken by an active role → 409.
        If taken by a soft-deleted role → hard-delete that row so the name is freed.
        """
        existing = await self._get_role_by_name(organization_id, name)
        if not existing:
            return
        if exclude_role_id and existing.id == exclude_role_id:
            return

        if existing.deleted_at is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A role named '{name}' already exists",
            )

        # Name held by a soft-deleted role → hard-delete to free the unique constraint
        await self.db.execute(
            delete(RolePermission).where(RolePermission.role_id == existing.id)
        )
        await self.db.delete(existing)
        await self.db.flush()

    async def _replace_permissions(
        self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]
    ) -> None:
        """Delete all existing role_permissions, then assign new ones."""
        await self.db.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )
        await self._assign_permissions(role_id, permission_ids)

    async def _assign_permissions(
        self, role_id: uuid.UUID, permission_ids: list[uuid.UUID]
    ) -> None:
        """Validate permission IDs exist and bulk-insert them for a role."""
        if not permission_ids:
            return

        # Select only id column to validate existence
        result = await self.db.execute(
            select(Permission.id).where(Permission.id.in_(permission_ids))
        )
        valid_ids = {row[0] for row in result.all()}

        invalid = set(permission_ids) - valid_ids
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid permission IDs: {[str(i) for i in invalid]}",
            )

        rows = [dict(role_id=role_id, permission_id=pid) for pid in permission_ids]
        await self.db.execute(insert(RolePermission).values(rows))
        await self.db.flush()
