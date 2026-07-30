import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from pgvector.sqlalchemy import Vector

from app.config import settings
from app.database import Base

# Import all models so Alembic can detect them
from app.models import (  # noqa: F401
    User,
    UserToken,
    Organization,
    Bot,
    BotChannel,
    Document,
    DocumentBot,
    DocumentChunk,
    Conversation,
    Message,
    Permission,
    Role,
    RolePermission,
    OrgMember,
    OrgInvitation,
    OwnershipTransfer,
)


# ---------------------------------------------------------------------------
# Third-party type renderer for autogenerate
# ---------------------------------------------------------------------------
# Alembic only auto-imports sqlalchemy + dialect types. Third-party column
# types (pgvector, geoalchemy2, etc.) get serialized via repr() without
# adding the import → NameError at runtime. This hook fixes that.
# See: docs/alembic-third-party-types.md
# ---------------------------------------------------------------------------
def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")
        return f"Vector(dim={obj.dim})"
    return False  # default rendering for everything else


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use DATABASE_URL from settings (overrides alembic.ini)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.



def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    Generates SQL scripts without actually connecting to the database.
    alembic upgrade head --sql > migration.sql
    This outputs raw SQL that you can review or run manually. Useful for:
    - DBA review before production deployment
    - Environments where you can't connect directly
    - Debugging migrations before running them
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        render_item=render_item,
        literal_binds=True, # literal_binds=True: Embeds values directly in SQL instead of using parameters. Makes the SQL file runnable standalone.
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool, # Migrations run once and exit. No need to keep connections pooled. NullPool means "create a connection, use it, close it immediately."
    )
    async with connectable.connect() as connection:
        """
            Alembic's core migration logic is synchronous. But our database driver (asyncpg) is async. 
            run_sync() bridges this gap — it runs sync code inside an async connection.
        """
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""
    Checks if you ran:

alembic upgrade head → online mode (connects to DB)
alembic upgrade head --sql → offline mode (generates SQL file)

"""