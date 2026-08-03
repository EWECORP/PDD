from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import execute_sql, transactional_connection
from ..partitioning import ensure_monthly_partitions
from .common import JobResult, validate_date_range


def generate_backtest_detail(
    engine: Engine,
    settings: Settings,
    evaluation_from: date,
    evaluation_to: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    calculation_run_uuid: UUID | None = None,
    forecast_horizon_days: int = 1,
) -> tuple[JobResult, UUID]:
    validate_date_range(evaluation_from, evaluation_to)
    if forecast_horizon_days <= 0:
        raise ValueError("forecast_horizon_days debe ser positivo")
    run_uuid = calculation_run_uuid or uuid4()

    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": "pdd.job.backtest"},
        )
        partitions = ensure_monthly_partitions(
            connection,
            "dm_pdd_pdvb_backtest_detail",
            evaluation_from,
            evaluation_to,
        )
        affected = execute_sql(
            connection,
            "backtest/insert_backtest_detail.sql",
            {
                "evaluation_from": evaluation_from,
                "evaluation_to": evaluation_to,
                "forecast_horizon_days": forecast_horizon_days,
                "scope_version_uuid": scope_version_uuid,
                "model_version_uuid": model_version_uuid,
                "calculation_run_uuid": run_uuid,
                "origin_cd": settings.origin_cd,
            },
        )
    return (
        JobResult(
            job_name="backtest",
            start_date=evaluation_from,
            end_date=evaluation_to,
            affected_rows=affected,
            partitions=tuple(partitions),
        ),
        run_uuid,
    )

