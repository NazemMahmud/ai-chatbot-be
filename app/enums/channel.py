from enum import Enum


class ChannelType(str, Enum):
    """Type of messaging channel a bot can connect to."""
    WIDGET = "widget"


class WebHookChannelType(str, Enum):
    """Type of messaging channel a bot can connect to."""
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"