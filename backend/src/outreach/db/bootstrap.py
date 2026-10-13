"""
Get the database ready at startup: create it if missing, then migrate it.

The point is that a second person can clone the repository, install
PostgreSQL, and run one command. No "did you remember to run alembic",
no schema drift between two laptops, no silent failures three screens
later because a column is missing.

Never do this in production. Two instances starting at once would migrate
at the same time, and a bad migration would take the service down instead
of failing a deploy. `AUTO_MIGRATE=false` turns it off.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from outreach.config import settings

log = structlog.get_logger(__name__)


class DatabaseUnavailable(RuntimeError):
    """PostgreSQL is not reachable. The message is written for a person."""


def _backend_root() -> Path:
    """Walk up from this file until alembic.ini appears."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "alembic.ini").is_file():
            return parent
    raise RuntimeError("Cannot find alembic.ini. Is the project laid out as expected?")


async def _ensure_database_exists() -> bool:
    """
    Create the database if it is not there yet. True when it was created.

    Connects to the built-in `postgres` database, because you cannot connect
    to a database in order to create it.
    """
    url = make_url(settings.database_url)
    target = url.database
    if not target:
        raise RuntimeError("DATABASE_URL has no database name.")

    try:
        conn = await asyncpg.connect(
            user=url.username,
            password=url.password,
            host=url.host or "localhost",
            port=url.port or 5432,
            database="postgres",
        )
    except OSError as exc:
        raise DatabaseUnavailable(
            f"Cannot reach PostgreSQL at {url.host or 'localhost'}:{url.port or 5432}. "
            "Is the PostgreSQL service running?"
        ) from exc
    except asyncpg.InvalidPasswordError as exc:
        raise DatabaseUnavailable(
            f"PostgreSQL rejected the password for user '{url.username}'. "
            "Check DATABASE_URL in backend/.env."
        ) from exc

    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", target)
        if exists:
            return False

        # CREATE DATABASE cannot run inside a transaction, which is why this
        # uses asyncpg directly rather than a SQLAlchemy session.
        await conn.execute(f'CREATE DATABASE "{target}"')
        log.info("db.created", database=target)
        return True

    except asyncpg.InsufficientPrivilegeError as exc:
        raise DatabaseUnavailable(
            f"The database '{target}' does not exist and user '{url.username}' is not "
            f"allowed to create it. Either run this once as the postgres superuser:\n"
            f'    CREATE DATABASE "{target}" OWNER {url.username};\n'
            f"or grant the permission:\n"
            f"    ALTER ROLE {url.username} CREATEDB;"
        ) from exc
    finally:
        await conn.close()


def _upgrade_to_head() -> None:
    """
    Apply every migration that has not run yet.

    Blocking, and called from a worker thread. Alembic's env.py starts its
    own event loop, which it cannot do from inside a running one.
    """
    root = _backend_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    command.upgrade(config, "head")


async def prepare_database() -> None:
    """
    Called once at startup. Creates the database if needed, then migrates.

    Raises DatabaseUnavailable with a readable message when PostgreSQL is
    not there, so the log says what to do instead of printing a traceback.
    """
    created = await _ensure_database_exists()
    await asyncio.to_thread(_upgrade_to_head)
    log.info(
        "db.ready",
        database=make_url(settings.database_url).database,
        created=created,
    )
