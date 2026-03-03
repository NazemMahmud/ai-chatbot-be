import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base
from app.enums import DocumentSourceType, DocumentStatus, DocumentParserType


class Document(Base):
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
    entities = relationship(
        "DocumentEntity",
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


class DocumentChunk(Base):
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

    # Sequential position within the document (0-based).
    # Used for neighbor-chunk expansion during retrieval.
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Full-text search vector for BM25 / keyword hybrid search.
    # Auto-generated from content column.
    search_vector = mapped_column(
        TSVECTOR,
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
        # HNSW vector index for cosine similarity search
        Index(
            "idx_chunks_embedding_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN index for full-text keyword search
        Index(
            "idx_chunks_search_vector",
            search_vector,
            postgresql_using="gin",
        ),
        # B-tree index for neighbor expansion queries
        Index(
            "idx_chunks_doc_index",
            "document_id",
            "chunk_index",
        ),
    )


class DocumentEntity(Base):
    """
    Entities extracted at index time via NER.

    Stores named entities (people, organizations, locations, etc.)
    found in each chunk. Enables deterministic answers for exhaustive
    queries like "list ALL characters" without relying on the LLM.
    """

    __tablename__ = "document_entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # person, org, location, date, money, term, ...
    entity_value: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # "Kian", "Ko Pha Ngan", ...
    count: Mapped[int] = mapped_column(
        Integer, default=1
    )  # occurrences in this chunk
    snippet: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # surrounding context for citation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    document = relationship("Document", back_populates="entities")

    __table_args__ = (
        Index("idx_entities_doc", "document_id"),
        Index("idx_entities_type_value", "entity_type", "entity_value"),
    )
