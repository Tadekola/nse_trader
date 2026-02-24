"""Alembic environment configuration."""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from alembic import context
import sys
import os

# Allow JSONB columns to work on SQLite (rendered as JSON)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"

# Add backend to path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.models import Base
from app.core.config import get_settings

config = context.config

# Allow override via ALEMBIC_DATABASE_URL env var (useful for testing with SQLite)
_override_url = os.environ.get("ALEMBIC_DATABASE_URL")
if _override_url:
    config.set_main_option("sqlalchemy.url", _override_url)
else:
    try:
        settings = get_settings()
        config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)
    except Exception:
        pass

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
