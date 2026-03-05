from enum import Enum


class WidgetPosition(str, Enum):
    """Position of the chat widget on the page."""

    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"


class WidgetTheme(str, Enum):
    """Visual theme of the chat widget."""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class WidgetBubbleIcon(str, Enum):
    """Icon displayed on the widget bubble button."""

    CHAT = "chat"
