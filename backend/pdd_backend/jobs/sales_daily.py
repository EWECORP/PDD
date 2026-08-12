from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import execute_sql, transactional_connection
from ..partitioning import ensure_monthly_partitions
from .common import JobResult, require_frozen_scope, validate_date_range


def load_sales_daily(
    engine: Engine,
    settings: Settings,
    start_date: date,
    end_date: date,
    scope_version_uuid: UUID,
    feature_run_uuid: UUID | None = None,
) -> JobResult:
    """Construye el panel diario incluyendo ceros servibles y stock desconocido."""
    validate_date_range(start_date, end_date)
    run_uuid = feature_run_uuid or uuid4()
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": "pdd.job.sales_daily"},
        )
        require_frozen_scope(connection, scope_version_uuid, settings.origin_cd)
        partitions = ensure_monthly_partitions(
            connection,
            "dm_pdd_venta_diaria",
            start_date,
            end_date,
        )
        affected = execute_sql(
            connection,
            "sales/upsert_sales_daily.sql",
            {
                "start_date": start_date,
                "end_date": end_date,
                "origin_cd": settings.origin_cd,
                "scope_version_uuid": scope_version_uuid,
                "feature_run_uuid": run_uuid,
            },
        )
    return JobResult(
        job_name="sales_daily",
        start_date=start_date,
        end_date=end_date,
        affected_rows=affected,
        partitions=tuple(partitions),
    )
