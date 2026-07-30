import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import SoftDeleteMixin


# Allowed widget_config keys — single source of truth for the key-subtraction constraint.
# If a new field is added to WidgetConfig (Pydantic), add it here too.
_WIDGET_CONFIG_FIELDS = ["position", "theme", "primary_color", "bubble_icon", "show_branding"]
_KEY_SUBTRACT = " ".join(f"- '{k}'" for k in _WIDGET_CONFIG_FIELDS)


class Bot(SoftDeleteMixin, Base):
    __tablename__ = "bots"

    __table_args__ = (
        # Must be a JSON object (not array, string, etc.)
        CheckConstraint(
            "widget_config IS NULL OR jsonb_typeof(widget_config) = 'object'",
            name="ck_widget_config_is_object",
        ),
        # Only allowed keys — removing all known keys must leave an empty object
        CheckConstraint(
            f"widget_config IS NULL OR (widget_config {_KEY_SUBTRACT}) = '{{}}'::jsonb",
            name="ck_widget_config_allowed_keys",
        ),
        # position must be 'bottom-right' or 'bottom-left'
        CheckConstraint(
            "widget_config IS NULL OR NOT (widget_config ? 'position') OR "
            "(widget_config->>'position') IN ('bottom-right','bottom-left')",
            name="ck_widget_config_position",
        ),
        # theme must be 'light', 'dark', or 'auto'
        CheckConstraint(
            "widget_config IS NULL OR NOT (widget_config ? 'theme') OR "
            "(widget_config->>'theme') IN ('light','dark','auto')",
            name="ck_widget_config_theme",
        ),
        # bubble_icon must be 'chat'
        CheckConstraint(
            "widget_config IS NULL OR NOT (widget_config ? 'bubble_icon') OR "
            "(widget_config->>'bubble_icon') IN ('chat')",
            name="ck_widget_config_bubble_icon",
        ),
        # show_branding must be a boolean
        CheckConstraint(
            "widget_config IS NULL OR NOT (widget_config ? 'show_branding') OR "
            "jsonb_typeof(widget_config->'show_branding') = 'boolean'",
            name="ck_widget_config_show_branding_type",
        ),
        # primary_color must be a string
        CheckConstraint(
            "widget_config IS NULL OR NOT (widget_config ? 'primary_color') OR "
            "jsonb_typeof(widget_config->'primary_color') = 'string'",
            name="ck_widget_config_primary_color_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My Chatbot")
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(
        Text, default="You are a helpful assistant."
    )
    welcome_message: Mapped[str | None] = mapped_column(
        Text, default="Hi! How can I help you?"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    widget_config: Mapped[dict | None] = mapped_column(
        JSONB,
        server_default=text(
            "jsonb_build_object("
            "'position','bottom-right',"
            "'theme','light',"
            "'primary_color','#6366f1',"
            "'bubble_icon','chat',"
            "'show_branding',true"
            ")"
        ),
    )
    allowed_domains: Mapped[list | None] = mapped_column(
        ARRAY(String(255)),
        server_default=text("'{}'::varchar[]"),
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships — many-to-many with documents via document_bots join table
    documents = relationship(
        "Document",
        secondary="document_bots",
        back_populates="bots",
        lazy="selectin",
    )
