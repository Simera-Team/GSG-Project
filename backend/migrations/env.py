
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Project Configuration
from app.core.config import settings

# SQLAlchemy Base
from app.infrastructure.persistence.db.base import Base

# Import all database models
from app.infrastructure.persistence.models.user_model import UserModel
from app.infrastructure.persistence.models.profile_model import ProfileModel
from app.infrastructure.persistence.models.country_model import CountryModel


# Alembic Config
config = context.config

# Logging Configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Connect Alembic to PostgreSQL
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("%", "%%")
)

# Register SQLAlchemy Models
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without connecting to the database."""

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
    """Run migrations with a database connection."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
