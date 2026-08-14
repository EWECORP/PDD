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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Variable booleana invalida {name}={value!r}")


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    origin_cd: int = 41
    statement_timeout_ms: int = 1_800_000
    lock_timeout_ms: int = 30_000
    keepalives_idle_seconds: int = 60
    keepalives_interval_seconds: int = 30
    keepalives_count: int = 5
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
            statement_timeout_ms=int(
                os.getenv("PDD_DB_STATEMENT_TIMEOUT_MS", "1800000")
            ),
            lock_timeout_ms=int(os.getenv("PDD_DB_LOCK_TIMEOUT_MS", "30000")),
            keepalives_idle_seconds=int(
                os.getenv("PDD_DB_KEEPALIVES_IDLE_SECONDS", "60")
            ),
            keepalives_interval_seconds=int(
                os.getenv("PDD_DB_KEEPALIVES_INTERVAL_SECONDS", "30")
            ),
            keepalives_count=int(os.getenv("PDD_DB_KEEPALIVES_COUNT", "5")),
            scope_version_uuid=_optional_uuid("PDD_SCOPE_VERSION_UUID"),
            model_version_uuid=_optional_uuid("PDD_MODEL_VERSION_UUID"),
        )
        if settings.pg_database != "diarco_data":
            raise RuntimeError(
                f"PDD analitico requiere PG_DB=diarco_data; recibido {settings.pg_database!r}"
            )
        if settings.origin_cd != 41:
            raise RuntimeError("La Fase 1 solo admite PDD_ORIGIN_CD=41")
        if settings.statement_timeout_ms <= 0:
            raise RuntimeError("PDD_DB_STATEMENT_TIMEOUT_MS debe ser positivo")
        if min(
            settings.keepalives_idle_seconds,
            settings.keepalives_interval_seconds,
            settings.keepalives_count,
        ) <= 0:
            raise RuntimeError("Los parametros keepalive deben ser positivos")
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


@dataclass(frozen=True)
class OperationalSettings:
    pg_host: str
    pg_port: int
    pg_database: str
    pg_user: str
    pg_password: str
    statement_timeout_ms: int = 1_800_000
    lock_timeout_ms: int = 30_000
    keepalives_idle_seconds: int = 60
    keepalives_interval_seconds: int = 30
    keepalives_count: int = 5

    @classmethod
    def from_env(cls) -> "OperationalSettings":
        load_environment()
        settings = cls(
            pg_host=_required("PDD_OPERATIONAL_PG_HOST"),
            pg_port=int(os.getenv("PDD_OPERATIONAL_PG_PORT", "5432")),
            pg_database=_required("PDD_OPERATIONAL_PG_DB"),
            pg_user=_required("PDD_OPERATIONAL_PG_USER"),
            pg_password=_required("PDD_OPERATIONAL_PG_PASSWORD"),
            statement_timeout_ms=int(
                os.getenv("PDD_OPERATIONAL_DB_STATEMENT_TIMEOUT_MS", "1800000")
            ),
            lock_timeout_ms=int(
                os.getenv("PDD_OPERATIONAL_DB_LOCK_TIMEOUT_MS", "30000")
            ),
            keepalives_idle_seconds=int(
                os.getenv("PDD_OPERATIONAL_DB_KEEPALIVES_IDLE_SECONDS", "60")
            ),
            keepalives_interval_seconds=int(
                os.getenv("PDD_OPERATIONAL_DB_KEEPALIVES_INTERVAL_SECONDS", "30")
            ),
            keepalives_count=int(
                os.getenv("PDD_OPERATIONAL_DB_KEEPALIVES_COUNT", "5")
            ),
        )
        allowed = {"connexa_platform_test"}
        if _env_bool("PDD_OPERATIONAL_ALLOW_PRODUCTION"):
            allowed.add("connexa_platform_ms")
        if settings.pg_database not in allowed:
            raise RuntimeError(
                "La publicacion PDD solo admite connexa_platform_test; "
                "para produccion configure explicitamente "
                "PDD_OPERATIONAL_ALLOW_PRODUCTION=true"
            )
        if settings.statement_timeout_ms <= 0:
            raise RuntimeError(
                "PDD_OPERATIONAL_DB_STATEMENT_TIMEOUT_MS debe ser positivo"
            )
        if min(
            settings.keepalives_idle_seconds,
            settings.keepalives_interval_seconds,
            settings.keepalives_count,
        ) <= 0:
            raise RuntimeError("Los parametros keepalive operativos deben ser positivos")
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
