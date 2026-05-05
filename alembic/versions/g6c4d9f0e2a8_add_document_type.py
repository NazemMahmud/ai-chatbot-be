"""
Add document_type column to documents table

Revision ID: g6c4d9f0e2a8 ( 11th revision )
Revises: d4e5f6a7b8c9 ( 10th revision )
Create Date: 2026-04-19

Adds document_type column with default value 'general' for all existing documents.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "g6c4d9f0e2a8"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add document_type column with default value 'general'
    op.add_column(
        "documents",
        sa.Column(
            "document_type",
            sa.String(50),
            nullable=False,
            server_default="general"
        )
    )
    # Create index on document_type for filtering
    op.create_index(
        "idx_documents_document_type",
        "documents",
        ["document_type"]
    )


def downgrade() -> None:
    # Remove index and column
    op.drop_index("idx_documents_document_type", table_name="documents")
    op.drop_column("documents", "document_type")
