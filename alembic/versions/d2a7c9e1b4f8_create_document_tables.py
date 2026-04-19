"""
Create document-related tables

Revision ID: d2a7c9e1b4f8 ( 5th revision )
Revises: 1f4b9e2c7a8d ( 4th revision )
Create Date: 2026-02-18

Tables: documents, document_bots, document_chunks.

document_chunks uses:
  - Vector(768) for nomic-embed-text embeddings
  - HNSW index for fast cosine similarity search
  - search_vector (tsvector GENERATED column, 'english' config) + GIN index for keyword search
  - (document_id, chunk_index) B-tree index for neighbor expansion
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2a7c9e1b4f8"
down_revision: Union[str, Sequence[str], None] = "1f4b9e2c7a8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("parser_type", sa.String(length=20), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_created", "documents", ["created_at"])
    op.create_index("idx_documents_status", "documents", ["status"])
    op.create_index("idx_documents_deleted_at", "documents", ["deleted_at"])

    # --- document_bots (join table) ---
    op.create_table(
        "document_bots",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("bot_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"], ["bots.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("document_id", "bot_id"),
    )

    # --- document_chunks ---
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("embedding", Vector(dim=768), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # search_vector: GENERATED ALWAYS AS tsvector for hybrid keyword search
    # 'english' config enables stemming (mother/mothers, run/running match)
    op.execute(
        """
        ALTER TABLE document_chunks
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
        """
    )

    # HNSW index — fast cosine similarity, no stale-index issues
    op.create_index(
        "idx_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # GIN index on search_vector for fast keyword search
    op.create_index(
        "idx_chunks_search_vector",
        "document_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )

    # B-tree index on (document_id, chunk_index) for neighbor expansion lookups
    op.create_index(
        "idx_chunks_doc_chunk_idx",
        "document_chunks",
        ["document_id", "chunk_index"],
    )

    # GIN index on metadata JSONB for metadata-aware search (@>, ?| operators)
    op.create_index(
        "idx_chunks_metadata_gin",
        "document_chunks",
        ["metadata"],
        postgresql_using="gin",
    )

    # Soft-delete index for document_chunks
    op.create_index("idx_chunks_deleted_at", "document_chunks", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_chunks_deleted_at", table_name="document_chunks")
    op.drop_index(
        "idx_chunks_metadata_gin",
        table_name="document_chunks",
        postgresql_using="gin",
    )
    op.drop_index("idx_chunks_doc_chunk_idx", table_name="document_chunks")
    op.drop_index(
        "idx_chunks_search_vector",
        table_name="document_chunks",
        postgresql_using="gin",
    )
    op.drop_index(
        "idx_chunks_embedding_hnsw",
        table_name="document_chunks",
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_table("document_chunks")
    op.drop_table("document_bots")
    op.drop_index("idx_documents_deleted_at", table_name="documents")
    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_index("idx_documents_created", table_name="documents")
    op.drop_table("documents")
