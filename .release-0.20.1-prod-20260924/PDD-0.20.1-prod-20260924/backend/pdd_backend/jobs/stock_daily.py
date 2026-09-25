from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import execute_sql, transactional_connection
from ..partitioning import ensure_monthly_partitions
from .common import JobResult, require_frozen_scope, validate_date_range


def load_stock_daily(
    engine: Engine,
    settings: Settings,
    start_date: date,
    end_date: date,
    scope_version_uuid: UUID,
) -> JobResult:
    """Normaliza t710 al scope CD41 y hace upsert por fecha-articulo-sucursal."""
    validate_date_range(start_date, end_date)
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": "pdd.job.stock_daily"},
        )
        require_frozen_scope(connection, scope_version_uuid, settings.origin_cd)
        partitions = ensure_monthly_partitions(
            connection,
            "dm_pdd_stock_diario",
            start_date,
            end_date,
        )
        affected = execute_sql(
            connection,
            "stock/upsert_stock_daily.sql",
            {
                "start_date": start_date,
                "end_date": end_date,
                "origin_cd": settings.origin_cd,
                "scope_version_uuid": scope_version_uuid,
            },
        )
    return JobResult(
        job_name="stock_daily",
        start_date=start_date,
        end_date=end_date,
        affected_rows=affected,
        partitions=tuple(partitions),
    )
