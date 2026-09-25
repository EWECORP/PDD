from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass(frozen=True)
class JobResult:
    job_name: str
    start_date: date
    end_date: date
    affected_rows: int
    partitions: tuple[str, ...] = ()


def validate_date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("end_date no puede ser anterior a start_date")


def require_frozen_scope(
    connection: Connection,
    scope_version_uuid: UUID,
    origin_cd: int,
) -> None:
    row = connection.execute(
        text(
            """
            SELECT
                v.status,
                v.article_count,
                v.pair_count,
                (SELECT count(*)
                   FROM datamart.dm_pdd_scope_article AS a
                  WHERE a.scope_version_uuid = v.scope_version_uuid) AS stored_articles,
                (SELECT count(*)
                   FROM datamart.dm_pdd_scope_pair AS p
                  WHERE p.scope_version_uuid = v.scope_version_uuid) AS stored_pairs
            FROM datamart.dm_pdd_scope_version AS v
            WHERE v.scope_version_uuid = :scope_version_uuid
              AND v.origin_cd = :origin_cd
            """
        ),
        {"scope_version_uuid": scope_version_uuid, "origin_cd": origin_cd},
    ).mappings().one_or_none()
    if row is None:
        raise RuntimeError(f"Scope congelado inexistente: {scope_version_uuid}")
    if row["status"] == "REJECTED":
        raise RuntimeError(
            f"Scope {scope_version_uuid} no utilizable; estado={row['status']}"
        )
    if (
        row["article_count"] != row["stored_articles"]
        or row["pair_count"] != row["stored_pairs"]
    ):
        raise RuntimeError(
            f"Scope {scope_version_uuid} incompleto: "
            f"articles={row['stored_articles']}/{row['article_count']}, "
            f"pairs={row['stored_pairs']}/{row['pair_count']}"
        )
