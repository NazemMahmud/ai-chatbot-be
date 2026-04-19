import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.config import settings
from app.database import Base
from app.enums import DocumentSourceType, DocumentStatus, DocumentParserType
from app.models.mixins import SoftDeleteMixin


class Document(SoftDeleteMixin, Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[DocumentSourceType] = mapped_column(
        String(50), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    file_size: Mapped[int | None] = mapped_column(Integer)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[DocumentStatus] = mapped_column(
        String(50), default=DocumentStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    parser_type: Mapped[DocumentParserType | None] = mapped_column(
        String(20)
    )  # 'simple' or 'docling', null = use env default
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

    # Relationships — many-to-many with bots via document_bots join table
    bots = relationship(
        "Bot",
        secondary="document_bots",
        back_populates="documents",
        lazy="selectin",
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_documents_status", "status"),
        Index("idx_documents_created", "created_at"),
    )

    @property
    def bot_ids(self) -> list[uuid.UUID]:
        """Convenience property: list of associated bot UUIDs."""
        return [bot.id for bot in self.bots] if self.bots else []


"""
    TODO: later documentation
    cache_ok = True
    SQLAlchemy caches compiled SQL statements for performance. 
    When a custom type is used, SQLAlchemy asks: "is it safe to cache queries that use this type?" 
    Setting True means "yes, this type always behaves the same way, cache it." 
    If you don't set this, SQLAlchemy prints a warning.

    get_col_spec()
    This is the one method SQLAlchemy calls when it needs to write the column type in a SQL statement — 
    for example in CREATE TABLE. It returns the raw PostgreSQL type name as a string. 
    That's all it does. When Alembic generates a migration or SQLAlchemy creates the table, it calls this and gets "TSVECTOR", 
    so the SQL becomes:

    search_vector TSVECTOR ...

"""
class TSVector(UserDefinedType):
    """Custom SQLAlchemy type for PostgreSQL tsvector."""

    cache_ok = True

    def get_col_spec(self):
        return "TSVECTOR"


class DocumentChunk(SoftDeleteMixin, Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
    embedding = mapped_column(Vector(settings.EMBED_DIMENSIONS))
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # todo: later documentation
    """
        1. TSVector
            - The column's data type. Tells SQLAlchemy: "this column is of type TSVECTOR in PostgreSQL." Same role as Integer, Text, String in other columns.

        2. Computed("to_tsvector('simple', content)", persisted=True)
            - key part. It tells SQLAlchemy that this column is a PostgreSQL generated column 
            — meaning: You never set it manually from Python.
            PostgreSQL automatically runs to_tsvector('simple', content) and fills it in
            Every time a row is inserted or content is updated, PostgreSQL recomputes the value
            - persisted=True means the value is stored on disk (the alternative is computed on-the-fly at read time — stored is faster for searching)
            -  In raw SQL this produces: 
            search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED

        3. nullable=True
            - The column can be NULL. In practice it's never null because PostgreSQL always computes it — but this is needed because SQLAlchemy doesn't know that a generated column is always populated.
    """
    search_vector = mapped_column(
        TSVector,
        Computed("to_tsvector('english', content)", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index(
            "idx_chunks_embedding_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "idx_chunks_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "idx_chunks_doc_chunk_idx",
            "document_id",
            "chunk_index",
        ),
        Index(
            "idx_chunks_metadata_gin",
            "metadata",
            postgresql_using="gin",
        ),
    )
