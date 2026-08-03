from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import execute_sql, transactional_connection
from ..partitioning import ensure_monthly_partitions
from ..windows import build_pdvb_windows
from .common import JobResult


def calculate_pdvb(
    engine: Engine,
    settings: Settings,
    business_date: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    calculation_run_uuid: UUID | None = None,
    recent_days: int = 28,
    previous_days: int = 28,
    seasonal_days: int = 28,
    recent_weight: Decimal = Decimal("0.60"),
    previous_weight: Decimal = Decimal("0.25"),
    seasonal_weight: Decimal = Decimal("0.15"),
    minimum_recent_eligible_days: int = 7,
    minimum_total_eligible_days: int = 14,
    warning_coverage: Decimal = Decimal("0.70"),
) -> tuple[JobResult, UUID]:
    windows = build_pdvb_windows(
        business_date,
        recent_days=recent_days,
        previous_days=previous_days,
        seasonal_days=seasonal_days,
    )
    if sum((recent_weight, previous_weight, seasonal_weight), Decimal("0")) <= 0:
        raise ValueError("La suma de pesos base debe ser positiva")
    run_uuid = calculation_run_uuid or uuid4()

    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": "pdd.job.pdvb"},
        )
        partitions = ensure_monthly_partitions(
            connection,
            "dm_pdd_pdvb_estimate_detail",
            business_date,
            business_date,
        )
        affected = execute_sql(
            connection,
            "pdvb/insert_pdvb_detail.sql",
            {
                "business_date": business_date,
                "cutoff_date": windows.cutoff_date,
                "recent_start": windows.recent_start,
                "recent_end": windows.recent_end,
                "previous_start": windows.previous_start,
                "previous_end": windows.previous_end,
                "seasonal_start": windows.seasonal_start,
                "seasonal_end": windows.seasonal_end,
                "origin_cd": settings.origin_cd,
                "scope_version_uuid": scope_version_uuid,
                "model_version_uuid": model_version_uuid,
                "calculation_run_uuid": run_uuid,
                "recent_base_weight": recent_weight,
                "previous_base_weight": previous_weight,
                "seasonal_base_weight": seasonal_weight,
                "minimum_recent_eligible_days": minimum_recent_eligible_days,
                "minimum_total_eligible_days": minimum_total_eligible_days,
                "warning_coverage": warning_coverage,
            },
        )
    return (
        JobResult(
            job_name="pdvb",
            start_date=business_date,
            end_date=business_date,
            affected_rows=affected,
            partitions=tuple(partitions),
        ),
        run_uuid,
    )

