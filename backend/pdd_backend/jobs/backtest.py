from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
import json
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import execute_sql, transactional_connection
from ..partitioning import ensure_monthly_partitions
from .common import JobResult, validate_date_range
from .pdvb import calculate_pdvb


BACKTEST_ESTIMATORS = (
    "PDVB_CANDIDATE",
    "MEAN_28",
    "ALGO_01_GROWTH",
    "ALGO_01_NORMALIZED",
    "OCCURRENCE_SIZE",
    "CROSTON_SBA",
    "HYBRID_EXPERIMENTAL",
)

EVALUATION_MODES = ("POINT_DAILY", "CUMULATIVE")


@dataclass(frozen=True)
class RollingBacktestResult:
    calculation_run_uuid: UUID
    origin_from: date
    origin_to: date
    evaluation_from: date
    evaluation_to: date
    forecast_horizon_days: int
    evaluation_mode: str
    origin_count: int
    estimate_rows: int
    detail_rows: int
    metric_rows: int

    def serializable(self) -> dict[str, object]:
        return {
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "origin_from": self.origin_from,
            "origin_to": self.origin_to,
            "evaluation_from": self.evaluation_from,
            "evaluation_to": self.evaluation_to,
            "forecast_horizon_days": self.forecast_horizon_days,
            "evaluation_mode": self.evaluation_mode,
            "origin_count": self.origin_count,
            "estimate_rows": self.estimate_rows,
            "detail_rows": self.detail_rows,
            "metric_rows": self.metric_rows,
            "estimators": list(BACKTEST_ESTIMATORS),
        }


def iter_dates(start_date: date, end_date: date):
    validate_date_range(start_date, end_date)
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _validate_weights(
    recent_weight: Decimal,
    previous_weight: Decimal,
    seasonal_weight: Decimal,
) -> None:
    if min(recent_weight, previous_weight, seasonal_weight) < 0:
        raise ValueError("Los pesos ALGO_01 no pueden ser negativos")
    if recent_weight + previous_weight + seasonal_weight <= 0:
        raise ValueError("La suma de pesos ALGO_01 debe ser positiva")


def _validate_backtest_parameters(
    evaluation_mode: str,
    actual_min_coverage: Decimal,
    croston_alpha: Decimal,
    adi_threshold: Decimal,
    cv2_threshold: Decimal,
) -> None:
    if evaluation_mode not in EVALUATION_MODES:
        raise ValueError(
            f"evaluation_mode invalido: {evaluation_mode}; permitidos={EVALUATION_MODES}"
        )
    if not Decimal("0") < actual_min_coverage <= Decimal("1"):
        raise ValueError("actual_min_coverage debe estar en (0, 1]")
    if not Decimal("0") < croston_alpha <= Decimal("1"):
        raise ValueError("croston_alpha debe estar en (0, 1]")
    if adi_threshold <= 0 or cv2_threshold < 0:
        raise ValueError("Los umbrales ADI/CV2 no pueden ser negativos")


def generate_backtest_detail(
    engine: Engine,
    settings: Settings,
    evaluation_from: date,
    evaluation_to: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    calculation_run_uuid: UUID | None = None,
    forecast_horizon_days: int = 1,
    forecast_origin_date: date | None = None,
    forecast_calculation_run_uuid: UUID | None = None,
    algo01_recent_weight: Decimal = Decimal("0.80"),
    algo01_previous_weight: Decimal = Decimal("0.10"),
    algo01_seasonal_weight: Decimal = Decimal("0.20"),
    evaluation_mode: str = "POINT_DAILY",
    actual_min_coverage: Decimal = Decimal("0.70"),
    croston_alpha: Decimal = Decimal("0.10"),
    adi_threshold: Decimal = Decimal("1.32"),
    cv2_threshold: Decimal = Decimal("0.49"),
) -> tuple[JobResult, UUID]:
    validate_date_range(evaluation_from, evaluation_to)
    if forecast_horizon_days <= 0:
        raise ValueError("forecast_horizon_days debe ser positivo")
    _validate_weights(
        algo01_recent_weight,
        algo01_previous_weight,
        algo01_seasonal_weight,
    )
    _validate_backtest_parameters(
        evaluation_mode,
        actual_min_coverage,
        croston_alpha,
        adi_threshold,
        cv2_threshold,
    )
    origin_date = forecast_origin_date
    if origin_date is not None:
        expected_evaluation = origin_date + timedelta(days=forecast_horizon_days)
        if evaluation_from != evaluation_to or evaluation_from != expected_evaluation:
            raise ValueError(
                "El detalle debe generarse para una fecha de origen y una fecha "
                "de evaluacion coherentes con el horizonte"
            )
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
                "forecast_origin_date": origin_date,
                "forecast_horizon_days": forecast_horizon_days,
                "scope_version_uuid": scope_version_uuid,
                "model_version_uuid": model_version_uuid,
                "calculation_run_uuid": run_uuid,
                "forecast_calculation_run_uuid": forecast_calculation_run_uuid,
                "origin_cd": settings.origin_cd,
                "algo01_recent_weight": algo01_recent_weight,
                "algo01_previous_weight": algo01_previous_weight,
                "algo01_seasonal_weight": algo01_seasonal_weight,
                "occurrence_recent_weight": Decimal("0.60"),
                "occurrence_previous_weight": Decimal("0.25"),
                "occurrence_seasonal_weight": Decimal("0.15"),
                "evaluation_mode": evaluation_mode,
                "actual_min_coverage": actual_min_coverage,
                "croston_alpha": croston_alpha,
                "adi_threshold": adi_threshold,
                "cv2_threshold": cv2_threshold,
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


def _register_run(
    engine: Engine,
    settings: Settings,
    run_uuid: UUID,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    origin_from: date,
    origin_to: date,
    horizon: int,
    origin_count: int,
    max_origins: int,
    evaluation_mode: str,
    actual_min_coverage: Decimal,
    croston_alpha: Decimal,
    adi_threshold: Decimal,
    cv2_threshold: Decimal,
) -> None:
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text(
                """
                INSERT INTO datamart.dm_pdd_pdvb_backtest_run (
                    calculation_run_uuid, model_version_uuid, scope_version_uuid,
                    origin_cd, origin_from, origin_to, evaluation_from,
                    evaluation_to, forecast_horizon_days, origin_count,
                    evaluation_mode, actual_min_coverage,
                    estimator_codes, parameters, status
                ) VALUES (
                    :run_uuid, :model_uuid, :scope_uuid, :origin_cd,
                    :origin_from, :origin_to, :evaluation_from, :evaluation_to,
                    :horizon, :origin_count, :evaluation_mode,
                    :actual_min_coverage, :estimator_codes,
                    CAST(:parameters AS jsonb), 'RUNNING'
                )
                """
            ),
            {
                "run_uuid": run_uuid,
                "model_uuid": model_version_uuid,
                "scope_uuid": scope_version_uuid,
                "origin_cd": settings.origin_cd,
                "origin_from": origin_from,
                "origin_to": origin_to,
                "evaluation_from": origin_from + timedelta(days=horizon),
                "evaluation_to": origin_to + timedelta(days=horizon),
                "horizon": horizon,
                "origin_count": origin_count,
                "evaluation_mode": evaluation_mode,
                "actual_min_coverage": actual_min_coverage,
                "estimator_codes": list(BACKTEST_ESTIMATORS),
                "parameters": json.dumps(
                    {
                        "algo01_weights": {
                            "recent": 0.8,
                            "previous": 0.1,
                            "seasonal": 0.2,
                        },
                        "occurrence_size_weights": {
                            "recent": 0.6,
                            "previous": 0.25,
                            "seasonal": 0.15,
                        },
                        "croston_alpha": str(croston_alpha),
                        "adi_threshold": str(adi_threshold),
                        "cv2_threshold": str(cv2_threshold),
                        "max_origins": max_origins,
                    },
                    sort_keys=True,
                ),
            },
        )


def _finish_run(
    engine: Engine,
    settings: Settings,
    run_uuid: UUID,
    status: str,
    completed_origins: int,
    estimate_rows: int,
    detail_rows: int,
    metric_rows: int,
    error_message: str | None = None,
) -> None:
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text(
                """
                UPDATE datamart.dm_pdd_pdvb_backtest_run
                SET status = :status,
                    completed_origin_count = :completed_origins,
                    estimate_row_count = :estimate_rows,
                    detail_row_count = :detail_rows,
                    metric_row_count = :metric_rows,
                    error_message = :error_message,
                    completed_at = clock_timestamp()
                WHERE calculation_run_uuid = :run_uuid
                """
            ),
            {
                "status": status,
                "completed_origins": completed_origins,
                "estimate_rows": estimate_rows,
                "detail_rows": detail_rows,
                "metric_rows": metric_rows,
                "error_message": error_message,
                "run_uuid": run_uuid,
            },
        )


def _update_run_progress(
    engine: Engine,
    settings: Settings,
    run_uuid: UUID,
    completed_origins: int,
    estimate_rows: int,
    detail_rows: int,
) -> None:
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text(
                """
                UPDATE datamart.dm_pdd_pdvb_backtest_run
                SET completed_origin_count = :completed_origins,
                    estimate_row_count = :estimate_rows,
                    detail_row_count = :detail_rows
                WHERE calculation_run_uuid = :run_uuid
                  AND status = 'RUNNING'
                """
            ),
            {
                "completed_origins": completed_origins,
                "estimate_rows": estimate_rows,
                "detail_rows": detail_rows,
                "run_uuid": run_uuid,
            },
        )


def aggregate_backtest_metrics(
    engine: Engine,
    settings: Settings,
    calculation_run_uuid: UUID,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    evaluation_from: date,
    evaluation_to: date,
    forecast_horizon_days: int,
    evaluation_mode: str,
) -> int:
    with transactional_connection(engine, settings) as connection:
        return execute_sql(
            connection,
            "backtest/insert_backtest_metrics.sql",
            {
                "calculation_run_uuid": calculation_run_uuid,
                "scope_version_uuid": scope_version_uuid,
                "model_version_uuid": model_version_uuid,
                "evaluation_from": evaluation_from,
                "evaluation_to": evaluation_to,
                "forecast_horizon_days": forecast_horizon_days,
                "estimator_count": len(BACKTEST_ESTIMATORS),
                "evaluation_mode": evaluation_mode,
            },
        )


def run_rolling_backtest(
    engine: Engine,
    settings: Settings,
    origin_from: date,
    origin_to: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    forecast_horizon_days: int = 1,
    max_origins: int = 120,
    evaluation_mode: str = "POINT_DAILY",
    actual_min_coverage: Decimal = Decimal("0.70"),
    croston_alpha: Decimal = Decimal("0.10"),
    adi_threshold: Decimal = Decimal("1.32"),
    cv2_threshold: Decimal = Decimal("0.49"),
    progress_callback: Callable[[int, int, date, int], None] | None = None,
) -> RollingBacktestResult:
    validate_date_range(origin_from, origin_to)
    if forecast_horizon_days <= 0:
        raise ValueError("forecast_horizon_days debe ser positivo")
    if max_origins <= 0:
        raise ValueError("max_origins debe ser positivo")
    _validate_backtest_parameters(
        evaluation_mode,
        actual_min_coverage,
        croston_alpha,
        adi_threshold,
        cv2_threshold,
    )
    origins = list(iter_dates(origin_from, origin_to))
    if len(origins) > max_origins:
        raise ValueError(
            f"El rango contiene {len(origins)} origenes; max_origins={max_origins}"
        )

    run_uuid = uuid4()
    evaluation_from = origin_from + timedelta(days=forecast_horizon_days)
    evaluation_to = origin_to + timedelta(days=forecast_horizon_days)
    _register_run(
        engine,
        settings,
        run_uuid,
        scope_version_uuid,
        model_version_uuid,
        origin_from,
        origin_to,
        forecast_horizon_days,
        len(origins),
        max_origins,
        evaluation_mode,
        actual_min_coverage,
        croston_alpha,
        adi_threshold,
        cv2_threshold,
    )

    completed_origins = 0
    estimate_rows = 0
    detail_rows = 0
    metric_rows = 0
    try:
        for origin_date in origins:
            estimate_result, forecast_run_uuid = calculate_pdvb(
                engine,
                settings,
                origin_date,
                scope_version_uuid,
                model_version_uuid,
            )
            evaluation_date = origin_date + timedelta(days=forecast_horizon_days)
            detail_result, _ = generate_backtest_detail(
                engine,
                settings,
                evaluation_date,
                evaluation_date,
                scope_version_uuid,
                model_version_uuid,
                calculation_run_uuid=run_uuid,
                forecast_horizon_days=forecast_horizon_days,
                forecast_origin_date=origin_date,
                forecast_calculation_run_uuid=forecast_run_uuid,
                evaluation_mode=evaluation_mode,
                actual_min_coverage=actual_min_coverage,
                croston_alpha=croston_alpha,
                adi_threshold=adi_threshold,
                cv2_threshold=cv2_threshold,
            )
            completed_origins += 1
            estimate_rows += estimate_result.affected_rows
            detail_rows += detail_result.affected_rows
            _update_run_progress(
                engine,
                settings,
                run_uuid,
                completed_origins,
                estimate_rows,
                detail_rows,
            )
            if progress_callback is not None:
                progress_callback(
                    completed_origins,
                    len(origins),
                    origin_date,
                    detail_result.affected_rows,
                )

        metric_rows = aggregate_backtest_metrics(
            engine,
            settings,
            run_uuid,
            scope_version_uuid,
            model_version_uuid,
            evaluation_from,
            evaluation_to,
            forecast_horizon_days,
            evaluation_mode,
        )
        _finish_run(
            engine,
            settings,
            run_uuid,
            "COMPLETED",
            completed_origins,
            estimate_rows,
            detail_rows,
            metric_rows,
        )
    except Exception as exc:
        _finish_run(
            engine,
            settings,
            run_uuid,
            "FAILED",
            completed_origins,
            estimate_rows,
            detail_rows,
            metric_rows,
            str(exc)[:2000],
        )
        raise

    return RollingBacktestResult(
        calculation_run_uuid=run_uuid,
        origin_from=origin_from,
        origin_to=origin_to,
        evaluation_from=evaluation_from,
        evaluation_to=evaluation_to,
        forecast_horizon_days=forecast_horizon_days,
        evaluation_mode=evaluation_mode,
        origin_count=len(origins),
        estimate_rows=estimate_rows,
        detail_rows=detail_rows,
        metric_rows=metric_rows,
    )
