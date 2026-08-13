"""base: register the pgvector extension.

Revision ID: 0001
Revises: (none)
Create Date: 2026-08-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """pgvector must exist before any vector(1536) column is created."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Drop the extension; safe only after tables have been removed."""
    op.execute("DROP EXTENSION IF EXISTS vector")
