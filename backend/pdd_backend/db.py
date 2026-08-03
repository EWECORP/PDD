from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

from .config import Settings


SQL_ROOT = Path(__file__).resolve().parent / "sql"


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.sqlalchemy_url(),
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        future=True,
        connect_args={"application_name": "pdd_backend"},
    )


@contextmanager
def transactional_connection(
    engine: Engine,
    settings: Settings,
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

