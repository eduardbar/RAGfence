"""base: register the pgvector extension.

Revision ID: 0001
Revises: (none)
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """pgvector must exist before any vector(1536) column is created."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Drop the extension; safe only after tables have been removed."""
    op.execute("DROP EXTENSION IF EXISTS vector")
