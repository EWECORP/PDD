from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from prefect import flow, get_run_logger, task

from pdd_backend.config import Settings
from pdd_backend.db import build_engine
from pdd_backend.flows.analytical import _uuid, pdd_features_flow
from pdd_backend.freshness import read_source_freshness
from pdd_backend.jobs.backtest import run_rolling_backtest
from pdd_backend.runtime_registry import resolve_runtime_selection
from pdd_backend.windows import build_pdvb_windows


DEFAULT_CONFIGURATION_VERSION_UUID = "2f916828-c59d-4190-a795-29ac5cfc1a66"
DEFAULT_PIPELINE_REVISION = "DAILY_PIPELINE_V3"


@task(name="PDD - Resolver ventana semanal de backtesting")
def resolve_weekly_backtest_context_task(
    lookback_days: int,
    forecast_horizon_days: int,
    scope_version_uuid: str | None,
    model_version_uuid: str | None,
) -> dict:
    if lookback_days <= 0:
        raise ValueError("lookback_days debe ser positivo")
    if forecast_horizon_days <= 0:
        raise ValueError("forecast_horizon_days debe ser positivo")
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        freshness = read_source_freshness(engine)
        common_closed_date = freshness.common_closed_date
        if common_closed_date is None:
            raise RuntimeError("No se pudo determinar el cierre comun para backtesting")
        with engine.connect() as connection:
            runtime = resolve_runtime_selection(
                connection,
                settings.runtime_environment,
                settings.runtime_process_code,
                explicit_scope_uuid=(
                    UUID(scope_version_uuid) if scope_version_uuid else None
                ),
                explicit_model_uuid=(
                    UUID(model_version_uuid) if model_version_uuid else None
                ),
                legacy_scope_uuid=settings.scope_version_uuid,
                legacy_model_uuid=settings.model_version_uuid,
                default_configuration_uuid=UUID(
                    DEFAULT_CONFIGURATION_VERSION_UUID
                ),
                default_pipeline_revision=DEFAULT_PIPELINE_REVISION,
            )
        origin_to = common_closed_date - timedelta(days=forecast_horizon_days)
        origin_from = origin_to - timedelta(days=lookback_days - 1)
        return {
            "origin_from": origin_from.isoformat(),
            "origin_to": origin_to.isoformat(),
            "common_closed_date": common_closed_date.isoformat(),
            "runtime": runtime.serializable(),
        }
    finally:
        engine.dispose()


@task(name="PDD - Ejecutar backtest rolling-origin")
def rolling_backtest_task(
    origin_from: date,
    origin_to: date,
    scope_version_uuid: str | None,
    model_version_uuid: str | None,
    forecast_horizon_days: int,
    max_origins: int,
    evaluation_mode: str,
    actual_min_coverage: Decimal,
    croston_alpha: Decimal,
    adi_threshold: Decimal,
    cv2_threshold: Decimal,
    sample_percent: Decimal,
) -> dict:
    logger = get_run_logger()
    settings = Settings.from_env()
    scope_uuid = _uuid(
        scope_version_uuid,
        settings.scope_version_uuid,
        "scope_version_uuid",
    )
    model_uuid = _uuid(
        model_version_uuid,
        settings.model_version_uuid,
        "model_version_uuid",
    )
    engine = build_engine(settings)
    try:
        logger.info(
            "Backtest rolling-origin %s a %s; horizonte=%s; modo=%s; muestra=%s%%",
            origin_from,
            origin_to,
            forecast_horizon_days,
            evaluation_mode,
            sample_percent,
        )
        result = run_rolling_backtest(
            engine,
            settings,
            origin_from,
            origin_to,
            scope_uuid,
            model_uuid,
            forecast_horizon_days=forecast_horizon_days,
            max_origins=max_origins,
            evaluation_mode=evaluation_mode,
            actual_min_coverage=actual_min_coverage,
            croston_alpha=croston_alpha,
            adi_threshold=adi_threshold,
            cv2_threshold=cv2_threshold,
            sample_percent=sample_percent,
            progress_callback=(
                lambda completed, total, origin, rows, estimate_s, detail_s: logger.info(
                    "Origen %s completado (%s/%s); detalle=%s; "
                    "pdvb=%.1fs; detalle=%.1fs",
                    origin,
                    completed,
                    total,
                    rows,
                    estimate_s,
                    detail_s,
                )
            ),
        )
        logger.info(
            "Backtest completo: run=%s, origenes=%s, detalle=%s, metricas=%s",
            result.calculation_run_uuid,
            result.origin_count,
            result.detail_rows,
            result.metric_rows,
        )
        return result.serializable()
    finally:
        engine.dispose()


@flow(name="PDD - Backtest rolling-origin", log_prints=True)
def pdd_rolling_backtest_flow(
    origin_from: date,
    origin_to: date,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
    forecast_horizon_days: int = 1,
    max_origins: int = 120,
    evaluation_mode: str = "POINT_DAILY",
    actual_min_coverage: Decimal = Decimal("0.70"),
    croston_alpha: Decimal = Decimal("0.10"),
    adi_threshold: Decimal = Decimal("1.32"),
    cv2_threshold: Decimal = Decimal("0.49"),
    sample_percent: Decimal = Decimal("100"),
) -> dict:
    if origin_to < origin_from:
        raise ValueError("origin_to no puede ser anterior a origin_from")
    if forecast_horizon_days <= 0:
        raise ValueError("forecast_horizon_days debe ser positivo")

    first_windows = build_pdvb_windows(origin_from)
    last_windows = build_pdvb_windows(origin_to)
    evaluation_to = origin_to + timedelta(days=forecast_horizon_days)

    # Aunque se materialicen observaciones futuras para evaluar, cada estimacion
    # filtra estrictamente sus ventanas hasta origin_date - 1.
    seasonal_features = pdd_features_flow(
        first_windows.seasonal_start,
        last_windows.seasonal_end,
        scope_version_uuid,
    )
    current_and_actual_features = pdd_features_flow(
        first_windows.previous_start,
        evaluation_to,
        scope_version_uuid,
        wait_for=[seasonal_features],
    )
    backtest = rolling_backtest_task(
        origin_from,
        origin_to,
        scope_version_uuid,
        model_version_uuid,
        forecast_horizon_days,
        max_origins,
        evaluation_mode,
        actual_min_coverage,
        croston_alpha,
        adi_threshold,
        cv2_threshold,
        sample_percent,
        wait_for=[current_and_actual_features],
    )
    return {
        "seasonal_features": seasonal_features,
        "current_and_actual_features": current_and_actual_features,
        "backtest": backtest,
    }


@flow(name="PDD - Monitoreo semanal del modelo activo", log_prints=True)
def pdd_weekly_model_monitoring_flow(
    lookback_days: int = 56,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
    forecast_horizon_days: int = 1,
    max_origins: int = 56,
    evaluation_mode: str = "POINT_DAILY",
    actual_min_coverage: Decimal = Decimal("0.70"),
    sample_percent: Decimal = Decimal("100"),
) -> dict:
    context = resolve_weekly_backtest_context_task(
        lookback_days,
        forecast_horizon_days,
        scope_version_uuid,
        model_version_uuid,
    )
    runtime = context["runtime"]
    result = pdd_rolling_backtest_flow(
        date.fromisoformat(context["origin_from"]),
        date.fromisoformat(context["origin_to"]),
        runtime["scope_version_uuid"],
        runtime["model_version_uuid"],
        forecast_horizon_days,
        max_origins,
        evaluation_mode,
        actual_min_coverage,
        Decimal("0.10"),
        Decimal("1.32"),
        Decimal("0.49"),
        sample_percent,
    )
    return {"context": context, "result": result}
