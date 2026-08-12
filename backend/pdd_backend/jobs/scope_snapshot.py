from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Engine, text

from ..config import Settings
from ..db import load_sql
from ..scope_rules import scope_exclusion_policy_json


@dataclass(frozen=True)
class ScopeSnapshotResult:
    scope_version_uuid: UUID
    source_as_of_ts: datetime
    article_count: int
    routed_article_count: int
    pair_count: int
    destination_count: int
    article_checksum: str
    pair_checksum: str
    scope_checksum: str

    def serializable(self) -> dict:
        result = asdict(self)
        result["scope_version_uuid"] = str(self.scope_version_uuid)
        result["source_as_of_ts"] = self.source_as_of_ts.isoformat()
        return result


def capture_scope_snapshot(
    engine: Engine,
    settings: Settings,
    scope_version_uuid: UUID,
    version_no: int,
    business_date: date,
    captured_by: str,
    supersedes_scope_version_uuid: UUID | None = None,
    scope_code: str = "CD41_DISTRIBUTABLE_ASSORTMENT",
) -> ScopeSnapshotResult:
    if version_no <= 0:
        raise ValueError("version_no debe ser positivo")
    if not captured_by.strip():
        raise ValueError("captured_by es obligatorio")
    exclusion_policy_json = scope_exclusion_policy_json()

    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        with connection.begin():
            connection.execute(
                text("SET LOCAL statement_timeout = :timeout"),
                {"timeout": f"{settings.statement_timeout_ms}ms"},
            )
            connection.execute(
                text("SET LOCAL lock_timeout = :timeout"),
                {"timeout": f"{settings.lock_timeout_ms}ms"},
            )
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
                {"lock_name": "pdd.job.scope_snapshot"},
            )
            connection.execute(
                text(load_sql("scope/prepare_scope_snapshot.sql")),
                {
                    "origin_cd": settings.origin_cd,
                    "exclusion_policy_json": exclusion_policy_json,
                },
            )
            row = connection.execute(
                text(load_sql("scope/insert_scope_version.sql")),
                {
                    "scope_version_uuid": scope_version_uuid,
                    "scope_code": scope_code,
                    "version_no": version_no,
                    "supersedes_scope_version_uuid": supersedes_scope_version_uuid,
                    "origin_cd": settings.origin_cd,
                    "business_date": business_date,
                    "captured_by": captured_by.strip(),
                    "exclusion_policy_json": exclusion_policy_json,
                },
            ).mappings().one()
            article_rows = connection.execute(
                text(load_sql("scope/insert_scope_articles.sql")),
                {"scope_version_uuid": scope_version_uuid},
            ).rowcount
            pair_rows = connection.execute(
                text(load_sql("scope/insert_scope_pairs.sql")),
                {"scope_version_uuid": scope_version_uuid},
            ).rowcount

            if article_rows != row["article_count"] or pair_rows != row["pair_count"]:
                raise RuntimeError(
                    "El conteo insertado no coincide con la cabecera sellada: "
                    f"articles={article_rows}/{row['article_count']}, "
                    f"pairs={pair_rows}/{row['pair_count']}"
                )

    return ScopeSnapshotResult(**dict(row))
