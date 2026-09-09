from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.auth import models as auth_models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base
from app.data_health import models as data_health_models  # noqa: F401
from app.development import models as development_models  # noqa: F401
from app.documents import models as document_models  # noqa: F401
from app.ingestion import models as ingestion_models  # noqa: F401
from app.organisations import models as org_models  # noqa: F401
from app.platform import audit as platform_audit  # noqa: F401
from app.platform import billing as platform_billing  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
