"""Alembic environment for RAGFence.

DDL is Alembic-only (``create_all`` is forbidden): the ORM metadata in
``ragfence.db.models`` is the source of truth for migration DDL. The URL
resolution order is ``RAGFENCE_TEST_DATABASE_DSN``, then
``RAGFENCE_DATABASE_DSN``, then ``sqlalchemy.url`` from ``alembic.ini``.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from ragfence.db.base import Base
from ragfence.db import models  # noqa: F401  (register every table on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    env_url = os.environ.get("RAGFENCE_TEST_DATABASE_DSN") or os.environ.get(
        "RAGFENCE_DATABASE_DSN"
    )
    if env_url is not None:
        return env_url
    configured = config.get_main_option("sqlalchemy.url")
    if configured is not None:
        return configured
    raise RuntimeError("no database URL configured; set RAGFENCE_DATABASE_DSN or sqlalchemy.url")


def run_migrations_offline() -> None:
    """Render DDL to stdout (``alembic upgrade head --sql``) without a connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations to a live database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=_resolve_url(),
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
