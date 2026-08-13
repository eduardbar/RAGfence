"""SQLAlchemy declarative base for the RAGFence storage schema.

DDL ownership is Alembic-only: ``create_all`` is forbidden. Migrations in
``alembic/versions/`` create the enum types (0002), tables (0003), and indexes
(0004); this metadata is the source of truth for that DDL and for autogenerate.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in ``ragfence.db.models``."""
