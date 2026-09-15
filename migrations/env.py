import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import config
from app.core.db import Base
from app.domains.devices import models as _devices_models
from app.domains.geozones import models as _geozone_models

_ = (
    _geozone_models,
    _devices_models,
)

current_path = os.path.dirname(os.path.abspath(__file__))
app_path = os.path.dirname(current_path)
sys.path.insert(0, app_path)

alembic_config = context.config

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

alembic_config.set_main_option("sqlalchemy.url", config.database.get_url("psycopg"))
target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
