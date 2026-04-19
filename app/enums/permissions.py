from enum import Enum

class Resource(str, Enum):
    BOTS = "bots"
    DOCUMENTS = "documents"
    CHAT = "chat"
    MEMBERS = "members"
    ROLES = "roles"
    INTEGRATIONS = "integrations"
    ORGANIZATION = "organization"


class Action(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    UPLOAD = "upload"
    SEND = "send"
    INVITE = "invite"
    REMOVE = "remove"