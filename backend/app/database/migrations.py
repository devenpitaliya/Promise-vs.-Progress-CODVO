from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR, settings


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def upgrade_to_head() -> None:
    """Blocking; call from a worker thread (migrations/env.py runs its own event loop)."""
    command.upgrade(alembic_config(), "head")


def head_revision() -> str | None:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()
