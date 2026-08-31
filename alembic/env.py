from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# ── EDIT 1: import your app's pieces ──────────────────────────────
# Base holds the registry of all your tables; settings has your DB URL;
# importing app.models forces both model files to load so they register
# themselves on Base.metadata (otherwise Alembic won't "see" them).
from app.db.base import Base
from app.core.config import settings
import app.models  # noqa: F401
# ──────────────────────────────────────────────────────────────────

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# ── EDIT 2: feed the DB URL from .env at runtime ──────────────────
# This overrides the (blank) sqlalchemy.url in alembic.ini, so your
# database password lives ONLY in .env and never in the committed .ini.
config.set_main_option("sqlalchemy.url", settings.database_url)
# ──────────────────────────────────────────────────────────────────

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── EDIT 3: point Alembic at your tables ──────────────────────────
# This is what autogenerate compares against the live database to
# decide what to CREATE/ALTER. Was `None`; now it's your metadata.
target_metadata = Base.metadata
# ──────────────────────────────────────────────────────────────────


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
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()