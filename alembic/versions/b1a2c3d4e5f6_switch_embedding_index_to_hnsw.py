"""
RAG pipeline upgrade: HNSW index, chunk_index, search_vector, document_entities

Changes:
1. Switch embedding index from IVFFlat to HNSW (no stale index issues)
2. Add chunk_index column for neighbor expansion
3. Add search_vector (tsvector) column for BM25 hybrid search
4. Create document_entities table for index-time NER extraction

Revision ID: b1a2c3d4e5f6
Revises: 82d63cb31320
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '82d63cb31320'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------------------
    # 1. Switch embedding index: IVFFlat → HNSW
    # -----------------------------------------------------------------
    op.drop_index(
        'idx_chunks_embedding',
        table_name='document_chunks',
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_index(
        'idx_chunks_embedding_hnsw',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )

    # -----------------------------------------------------------------
    # 2. Add chunk_index column for neighbor expansion
    # -----------------------------------------------------------------
    op.add_column(
        'document_chunks',
        sa.Column('chunk_index', sa.Integer(), nullable=True),
    )
    op.create_index(
        'idx_chunks_doc_index',
        'document_chunks',
        ['document_id', 'chunk_index'],
    )

    # -----------------------------------------------------------------
    # 3. Add search_vector column for BM25 full-text search
    # -----------------------------------------------------------------
    op.add_column(
        'document_chunks',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('english', content)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        'idx_chunks_search_vector',
        'document_chunks',
        ['search_vector'],
        postgresql_using='gin',
    )

    # -----------------------------------------------------------------
    # 4. Create document_entities table
    # -----------------------------------------------------------------
    op.create_table(
        'document_entities',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('chunk_id', sa.UUID(), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_value', sa.Text(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['document_id'], ['documents.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['chunk_id'], ['document_chunks.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_entities_doc', 'document_entities', ['document_id'])
    op.create_index(
        'idx_entities_type_value',
        'document_entities',
        ['entity_type', 'entity_value'],
    )


def downgrade() -> None:
    # Drop document_entities
    op.drop_index('idx_entities_type_value', table_name='document_entities')
    op.drop_index('idx_entities_doc', table_name='document_entities')
    op.drop_table('document_entities')

    # Drop search_vector
    op.drop_index(
        'idx_chunks_search_vector',
        table_name='document_chunks',
        postgresql_using='gin',
    )
    op.drop_column('document_chunks', 'search_vector')

    # Drop chunk_index
    op.drop_index('idx_chunks_doc_index', table_name='document_chunks')
    op.drop_column('document_chunks', 'chunk_index')

    # Switch back to IVFFlat
    op.drop_index(
        'idx_chunks_embedding_hnsw',
        table_name='document_chunks',
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_index(
        'idx_chunks_embedding',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
