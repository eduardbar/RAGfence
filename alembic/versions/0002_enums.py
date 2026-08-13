"""enums: create the five native Postgres enum types.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import CreateEnumType, DropEnumType

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

classification = postgresql.ENUM(
    "public", "internal", "confidential", "restricted", name="classification"
)
document_status = postgresql.ENUM("pending", "ready", "failed", name="document_status")
finding_severity = postgresql.ENUM("low", "medium", "high", "critical", name="finding_severity")
run_status = postgresql.ENUM("running", "passed", "failed", "crashed", name="run_status")
scenario_outcome = postgresql.ENUM("pass", "warning", "fail", "critical", name="scenario_outcome")


def upgrade() -> None:
    op.execute(CreateEnumType(classification))
    op.execute(CreateEnumType(document_status))
    op.execute(CreateEnumType(finding_severity))
    op.execute(CreateEnumType(run_status))
    op.execute(CreateEnumType(scenario_outcome))


def downgrade() -> None:
    op.execute(DropEnumType(scenario_outcome))
    op.execute(DropEnumType(run_status))
    op.execute(DropEnumType(finding_severity))
    op.execute(DropEnumType(document_status))
    op.execute(DropEnumType(classification))
