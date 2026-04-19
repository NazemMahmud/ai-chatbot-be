from enum import Enum


class OrgRole(str, Enum):
    """Role of a user within an organization."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class TransferAction(str, Enum):
    """Actions a target member can take on an ownership transfer request."""

    ACCEPT = "accept"
    DECLINE = "decline"

    @property
    def success_message(self) -> str:
        messages = {
            TransferAction.ACCEPT: "Ownership transfer accepted. You are now the organization owner.",
            TransferAction.DECLINE: "Ownership transfer declined.",
        }
        return messages[self]
