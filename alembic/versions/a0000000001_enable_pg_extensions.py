"""
Enable PostgreSQL extensions

Revision ID: a0000000001
Revises: f3327c5011d1
Create Date: 2026-02-17

Enables required PostgreSQL extensions before any table uses them.
pgvector: provides the VECTOR column type for embedding storage.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a0000000001"
down_revision: Union[str, Sequence[str], None] = "f3327c5011d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
