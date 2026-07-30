"""
Predefined permissions and default role templates.

Permissions are system-defined (resource.action pairs).
Default roles are templates seeded when an organization is created.

Usage in route dependencies:
    @router.post("", dependencies=[Depends(PermissionService.Bots.CREATE)])
"""
from app.enums import Resource, Action
from app.core.permission_checker import PermissionChecker


# Format: (resource, action, description)
ALL_PERMISSIONS: list[tuple[str, str, str]] = [
    # Bots
    (Resource.BOTS, Action.CREATE, "Create new bots"),
    (Resource.BOTS, Action.READ, "View bots"),
    (Resource.BOTS, Action.UPDATE, "Edit bot settings"),
    (Resource.BOTS, Action.DELETE, "Delete bots"),
    # Documents
    (Resource.DOCUMENTS, Action.UPLOAD, "Upload documents"),
    (Resource.DOCUMENTS, Action.READ, "View documents"),
    (Resource.DOCUMENTS, Action.UPDATE, "Update document associations"),
    (Resource.DOCUMENTS, Action.DELETE, "Delete documents"),
    # Chat
    (Resource.CHAT, Action.SEND, "Send chat messages"),
    (Resource.CHAT, Action.READ, "View conversations and messages"),
    # Members
    (Resource.MEMBERS, Action.INVITE, "Invite new members"),
    (Resource.MEMBERS, Action.READ, "View organization members"),
    (Resource.MEMBERS, Action.UPDATE, "Change member roles"),
    (Resource.MEMBERS, Action.REMOVE, "Remove members"),
    # Roles
    (Resource.ROLES, Action.CREATE, "Create custom roles"),
    (Resource.ROLES, Action.READ, "View roles and permissions"),
    (Resource.ROLES, Action.UPDATE, "Edit roles and assign permissions"),
    (Resource.ROLES, Action.DELETE, "Delete custom roles"),
    # Integrations
    (Resource.INTEGRATIONS, Action.CREATE, "Set up integrations (WhatsApp, Telegram)"),
    (Resource.INTEGRATIONS, Action.READ, "View integration status"),
    (Resource.INTEGRATIONS, Action.UPDATE, "Update integration credentials"),
    (Resource.INTEGRATIONS, Action.DELETE, "Remove integrations"),
    # Organization
    (Resource.ORGANIZATION, Action.UPDATE, "Update organization settings"),
    (Resource.ORGANIZATION, Action.DELETE, "Delete the organization"),
]


# ---------------------------------------------------------------------------
# Default role templates — created when a new organization is registered.
# Maps role name → (description, is_system, list of "resource.action" codes)
# ---------------------------------------------------------------------------

DEFAULT_ROLES: dict[str, tuple[str, bool, list[str]]] = {
    "owner": (
        "Full access. Cannot be deleted or renamed.",
        True,
        ["*"],
    ),
    "admin": (
        "Can manage bots, documents, members, and integrations.",
        False,
        [
            f"{Resource.BOTS}.{Action.CREATE}",
            f"{Resource.BOTS}.{Action.READ}",
            f"{Resource.BOTS}.{Action.UPDATE}",
            f"{Resource.BOTS}.{Action.DELETE}",
            f"{Resource.DOCUMENTS}.{Action.UPLOAD}",
            f"{Resource.DOCUMENTS}.{Action.READ}",
            f"{Resource.DOCUMENTS}.{Action.UPDATE}",
            f"{Resource.DOCUMENTS}.{Action.DELETE}",
            f"{Resource.CHAT}.{Action.SEND}",
            f"{Resource.CHAT}.{Action.READ}",
            f"{Resource.MEMBERS}.{Action.INVITE}",
            f"{Resource.MEMBERS}.{Action.READ}",
            f"{Resource.MEMBERS}.{Action.UPDATE}",
            f"{Resource.MEMBERS}.{Action.REMOVE}",
            f"{Resource.ROLES}.{Action.READ}",
            f"{Resource.INTEGRATIONS}.{Action.CREATE}",
            f"{Resource.INTEGRATIONS}.{Action.READ}",
            f"{Resource.INTEGRATIONS}.{Action.UPDATE}",
            f"{Resource.INTEGRATIONS}.{Action.DELETE}",
        ],
    ),
    "member": (
        "Can view bots and documents, and use chat.",
        False,
        [
            f"{Resource.BOTS}.{Action.READ}",
            f"{Resource.DOCUMENTS}.{Action.READ}",
            f"{Resource.CHAT}.{Action.SEND}",
            f"{Resource.CHAT}.{Action.READ}",
            f"{Resource.MEMBERS}.{Action.READ}",
            f"{Resource.ROLES}.{Action.READ}",
        ],
    ),
}


# ---------------------------------------------------------------------------
# PermissionService — pre-built PermissionChecker instances grouped by resource.
#
# Usage:
#   @router.post("", dependencies=[Depends(PermissionService.Bots.CREATE)])
#
# Changing a permission string? Change the enum above — all routes update.
# Adding a new permission? Add to enum + ALL_PERMISSIONS + PermissionService group.
# ---------------------------------------------------------------------------

# Lazy import to avoid circular dependency (deps imports permissions indirectly)
# PermissionChecker is imported at module level after deps.py is loaded.
# We use a factory to defer the import.

def _checker(resource: Resource, action: Action):
    """Create a PermissionChecker instance. Import is deferred to avoid circular deps."""
    return PermissionChecker(resource.value, action.value)


class _BotsPerms:
    @property
    def CREATE(self): return _checker(Resource.BOTS, Action.CREATE)
    @property
    def READ(self): return _checker(Resource.BOTS, Action.READ)
    @property
    def UPDATE(self): return _checker(Resource.BOTS, Action.UPDATE)
    @property
    def DELETE(self): return _checker(Resource.BOTS, Action.DELETE)


class _DocumentsPerms:
    @property
    def UPLOAD(self): return _checker(Resource.DOCUMENTS, Action.UPLOAD)
    @property
    def READ(self): return _checker(Resource.DOCUMENTS, Action.READ)
    @property
    def UPDATE(self): return _checker(Resource.DOCUMENTS, Action.UPDATE)
    @property
    def DELETE(self): return _checker(Resource.DOCUMENTS, Action.DELETE)


class _ChatPerms:
    @property
    def SEND(self): return _checker(Resource.CHAT, Action.SEND)
    @property
    def READ(self): return _checker(Resource.CHAT, Action.READ)


class _MembersPerms:
    @property
    def INVITE(self): return _checker(Resource.MEMBERS, Action.INVITE)
    @property
    def READ(self): return _checker(Resource.MEMBERS, Action.READ)
    @property
    def UPDATE(self): return _checker(Resource.MEMBERS, Action.UPDATE)
    @property
    def REMOVE(self): return _checker(Resource.MEMBERS, Action.REMOVE)


class _RolesPerms:
    @property
    def CREATE(self): return _checker(Resource.ROLES, Action.CREATE)
    @property
    def READ(self): return _checker(Resource.ROLES, Action.READ)
    @property
    def UPDATE(self): return _checker(Resource.ROLES, Action.UPDATE)
    @property
    def DELETE(self): return _checker(Resource.ROLES, Action.DELETE)


class _IntegrationsPerms:
    @property
    def CREATE(self): return _checker(Resource.INTEGRATIONS, Action.CREATE)
    @property
    def READ(self): return _checker(Resource.INTEGRATIONS, Action.READ)
    @property
    def UPDATE(self): return _checker(Resource.INTEGRATIONS, Action.UPDATE)
    @property
    def DELETE(self): return _checker(Resource.INTEGRATIONS, Action.DELETE)


class _OrganizationPerms:
    @property
    def UPDATE(self): return _checker(Resource.ORGANIZATION, Action.UPDATE)
    @property
    def DELETE(self): return _checker(Resource.ORGANIZATION, Action.DELETE)


class PermissionService:
    """
    Centralized permission registry. All route dependencies reference this.

    Example:
        @router.post("", dependencies=[Depends(PermissionService.Bots.CREATE)])
        @router.get("", dependencies=[Depends(PermissionService.Documents.READ)])
    """
    Bots = _BotsPerms()
    Documents = _DocumentsPerms()
    Chat = _ChatPerms()
    Members = _MembersPerms()
    Roles = _RolesPerms()
    Integrations = _IntegrationsPerms()
    Organization = _OrganizationPerms()
