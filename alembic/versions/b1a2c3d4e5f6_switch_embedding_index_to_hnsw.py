"""
Switch embedding index from IVFFlat to HNSW

IVFFlat indexes become stale after bulk delete+insert operations,
causing cosine distance queries to return 0 results.
HNSW indexes don't have this problem and provide better recall.

Revision ID: b1a2c3d4e5f6
Revises: 82d63cb31320
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1a2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '82d63cb31320'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old IVFFlat index
    op.drop_index(
        'idx_chunks_embedding',
        table_name='document_chunks',
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    # Create new HNSW index (no stale index issues, better recall)
    op.create_index(
        'idx_chunks_embedding_hnsw',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    # Drop HNSW index
    op.drop_index(
        'idx_chunks_embedding_hnsw',
        table_name='document_chunks',
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    # Recreate IVFFlat index
    op.create_index(
        'idx_chunks_embedding',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='ivfflat',
        postgresql_with={'lists': 100},
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
