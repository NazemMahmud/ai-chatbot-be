"""
Enable PostgreSQL extensions

Revision ID: a3f9c1d7b2e4 ( 1st revision )
Revises: -
Create Date: 2026-02-17

Enables required PostgreSQL extensions before any table uses them.
pgvector: provides the VECTOR column type for embedding storage.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c1d7b2e4"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
