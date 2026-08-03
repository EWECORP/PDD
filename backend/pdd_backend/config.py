from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from sqlalchemy import URL


def _candidate_env_files() -> list[Path]:
    candidates: list[Path] = []
    for variable in ("PDD_ENV_PATH", "FORECAST_ENV_PATH"):
        value = os.getenv(variable)
        if value:
            candidates.append(Path(value))

    # Desarrollo Windows: E:/ETL/PDD/backend -> E:/ETL/FORECAST/.env
    workspace = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            workspace / "FORECAST" / ".env",
            Path("/srv/FORECAST/forecast_core/.env"),
            Path("/srv/FORECAST/.env"),
        ]
    )
    return candidates


def load_environment() -> Path | None:
    for candidate in _candidate_env_files():
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return candidate
    load_dotenv(override=False)
    return None


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Variable requerida no configurada: {name}")
    return value.strip()


def _optional_uuid(name: str) -> UUID | None:
    value = os.getenv(name)
    return UUID(value) if value and value.strip() else None


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    origin_cd: int = 41
    statement_timeout_ms: int = 0
    lock_timeout_ms: int = 30_000
    scope_version_uuid: UUID | None = None
    model_version_uuid: UUID | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        load_environment()
        settings = cls(
            pg_host=_required("PG_HOST"),
            pg_port=int(os.getenv("PG_PORT", "5432")),
            pg_database=_required("PG_DB"),
            pg_user=_required("PG_USER"),
            pg_password=_required("PG_PASSWORD"),
            origin_cd=int(os.getenv("PDD_ORIGIN_CD", "41")),
            statement_timeout_ms=int(os.getenv("PDD_DB_STATEMENT_TIMEOUT_MS", "0")),
            lock_timeout_ms=int(os.getenv("PDD_DB_LOCK_TIMEOUT_MS", "30000")),
            scope_version_uuid=_optional_uuid("PDD_SCOPE_VERSION_UUID"),
            model_version_uuid=_optional_uuid("PDD_MODEL_VERSION_UUID"),
        )
        if settings.pg_database != "diarco_data":
            raise RuntimeError(
                f"PDD analitico requiere PG_DB=diarco_data; recibido {settings.pg_database!r}"
            )
        if settings.origin_cd != 41:
            raise RuntimeError("La Fase 1 solo admite PDD_ORIGIN_CD=41")
        return settings

    def sqlalchemy_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.pg_user,
            password=self.pg_password,
            host=self.pg_host,
            port=self.pg_port,
            database=self.pg_database,
        )

    def require_scope_uuid(self, override: UUID | None = None) -> UUID:
        value = override or self.scope_version_uuid
        if value is None:
            raise RuntimeError(
                "Debe informar scope_version_uuid o configurar PDD_SCOPE_VERSION_UUID"
            )
        return value

    def require_model_uuid(self, override: UUID | None = None) -> UUID:
        value = override or self.model_version_uuid
        if value is None:
            raise RuntimeError(
                "Debe informar model_version_uuid o configurar PDD_MODEL_VERSION_UUID"
            )
        return value

