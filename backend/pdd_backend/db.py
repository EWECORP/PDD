from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Iterator, Mapping

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from .config import OperationalSettings, Settings


SQL_ROOT = Path(__file__).resolve().parent / "sql"
DAILY_MASTER_LOCK_NAME = "pdd.daily.master.shared.source"


def build_engine(settings: Settings) -> Engine:
    return _build_engine(settings, f"pdd_{settings.runtime_environment.lower()}_source")


def build_operational_engine(settings: OperationalSettings) -> Engine:
    return _build_engine(settings, f"pdd_{settings.target_environment.lower()}_target")


def _build_engine(
    settings: Settings | OperationalSettings,
    application_name: str,
) -> Engine:
    return create_engine(
        settings.sqlalchemy_url(),
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        future=True,
        connect_args={
            "application_name": application_name,
            "connect_timeout": settings.connect_timeout_seconds,
            "options": (
                f"-c statement_timeout={settings.statement_timeout_ms} "
                f"-c lock_timeout={settings.lock_timeout_ms} "
                "-c idle_in_transaction_session_timeout="
                f"{settings.idle_in_transaction_timeout_ms}"
            ),
            "keepalives": 1,
            "keepalives_idle": settings.keepalives_idle_seconds,
            "keepalives_interval": settings.keepalives_interval_seconds,
            "keepalives_count": settings.keepalives_count,
        },
    )


@contextmanager
def transactional_connection(
    engine: Engine,
    settings: Settings | OperationalSettings,
) -> Iterator[Connection]:
    with engine.begin() as connection:
        connection.execute(
            text("SET LOCAL statement_timeout = :timeout"),
            {"timeout": f"{settings.statement_timeout_ms}ms"},
        )
        connection.execute(
            text("SET LOCAL lock_timeout = :timeout"),
            {"timeout": f"{settings.lock_timeout_ms}ms"},
        )
        yield connection


@contextmanager
def daily_master_execution_lock(
    settings: Settings,
    *,
    wait_seconds: int = 900,
    poll_seconds: int = 15,
) -> Iterator[None]:
    """Serializa los masters TEST/PROD en diarco_data sin abrir una transaccion."""
    if wait_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("Los plazos del lock diario deben ser positivos")
    engine = build_engine(settings)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            deadline = monotonic() + wait_seconds
            while not connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtext(:name))"),
                {"name": DAILY_MASTER_LOCK_NAME},
            ):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        "SOURCE_DAILY_MASTER_BUSY: otra corrida diaria PDD sigue "
                        "usando diarco_data; reintentar al terminar"
                    )
                sleep(min(poll_seconds, remaining))
            try:
                yield
            finally:
                try:
                    released = connection.scalar(
                        text("SELECT pg_advisory_unlock(hashtext(:name))"),
                        {"name": DAILY_MASTER_LOCK_NAME},
                    )
                    if not released:
                        raise RuntimeError("Se perdio el lock del master diario")
                except Exception:
                    connection.invalidate()
                    raise
    finally:
        engine.dispose()


def load_sql(relative_path: str) -> str:
    path = (SQL_ROOT / relative_path).resolve()
    if SQL_ROOT.resolve() not in path.parents:
        raise ValueError(f"Ruta SQL fuera del paquete: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def execute_sql(
    connection: Connection,
    relative_path: str,
    parameters: Mapping[str, Any],
) -> int:
    result = connection.execute(text(load_sql(relative_path)), dict(parameters))
    return max(result.rowcount or 0, 0)
