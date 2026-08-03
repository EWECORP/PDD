from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from prefect import flow, get_run_logger, task

from ..clock import business_today
from ..config import Settings
from ..db import build_engine
from ..freshness import read_source_freshness, require_closed_through
from ..jobs.backtest import generate_backtest_detail
from ..jobs.pdvb import calculate_pdvb
from ..jobs.sales_daily import load_sales_daily
from ..jobs.stock_daily import load_stock_daily
from ..windows import build_pdvb_windows


def _uuid(value: str | None, fallback: UUID | None, name: str) -> UUID:
    if value:
        return UUID(value)
    if fallback:
        return fallback
    raise RuntimeError(f"Debe informar {name} o configurarlo en el entorno")


@task(name="PDD - Normalizar stock diario", retries=2, retry_delay_seconds=60)
def stock_daily_task(start_date: date, end_date: date) -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        result = load_stock_daily(engine, settings, start_date, end_date)
        return result.__dict__
    finally:
        engine.dispose()


@task(name="PDD - Validar cierre comun")
def freshness_gate_task(end_date: date) -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        freshness = read_source_freshness(engine)
        common = require_closed_through(freshness, end_date)
        return {**freshness.__dict__, "common_closed_date": common}
    finally:
        engine.dispose()


@task(name="PDD - Construir venta diaria", retries=2, retry_delay_seconds=60)
def sales_daily_task(
    start_date: date,
    end_date: date,
    scope_version_uuid: str | None,
) -> dict:
    settings = Settings.from_env()
    scope_uuid = _uuid(
        scope_version_uuid,
        settings.scope_version_uuid,
        "scope_version_uuid",
    )
    engine = build_engine(settings)
    try:
        result = load_sales_daily(
            engine,
            settings,
            start_date,
            end_date,
            scope_uuid,
        )
        return result.__dict__
    finally:
        engine.dispose()


@task(name="PDD - Calcular detalle PDVB", retries=1, retry_delay_seconds=60)
def pdvb_task(
    business_date: date,
    scope_version_uuid: str | None,
    model_version_uuid: str | None,
) -> dict:
    settings = Settings.from_env()
    scope_uuid = _uuid(scope_version_uuid, settings.scope_version_uuid, "scope_version_uuid")
    model_uuid = _uuid(model_version_uuid, settings.model_version_uuid, "model_version_uuid")
    engine = build_engine(settings)
    try:
        result, calculation_run_uuid = calculate_pdvb(
            engine,
            settings,
            business_date,
            scope_uuid,
            model_uuid,
        )
        return {**result.__dict__, "calculation_run_uuid": str(calculation_run_uuid)}
    finally:
        engine.dispose()


@task(name="PDD - Generar backtest", retries=1, retry_delay_seconds=60)
def backtest_task(
    evaluation_from: date,
    evaluation_to: date,
    scope_version_uuid: str | None,
    model_version_uuid: str | None,
    forecast_horizon_days: int,
) -> dict:
    settings = Settings.from_env()
    scope_uuid = _uuid(scope_version_uuid, settings.scope_version_uuid, "scope_version_uuid")
    model_uuid = _uuid(model_version_uuid, settings.model_version_uuid, "model_version_uuid")
    engine = build_engine(settings)
    try:
        result, calculation_run_uuid = generate_backtest_detail(
            engine,
            settings,
            evaluation_from,
            evaluation_to,
            scope_uuid,
            model_uuid,
            forecast_horizon_days=forecast_horizon_days,
        )
        return {**result.__dict__, "calculation_run_uuid": str(calculation_run_uuid)}
    finally:
        engine.dispose()


@flow(name="PDD - Preparar features diarco_data", log_prints=True)
def pdd_features_flow(
    start_date: date,
    end_date: date,
    scope_version_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    stock_result = stock_daily_task(start_date, end_date)
    freshness = freshness_gate_task(end_date, wait_for=[stock_result])
    sales_result = sales_daily_task(
        start_date,
        end_date,
        scope_version_uuid,
        wait_for=[freshness],
    )
    logger.info("Features PDD preparadas: %s a %s", start_date, end_date)
    return {
        "stock": stock_result,
        "freshness": freshness,
        "sales": sales_result,
    }


@flow(name="PDD - Backfill inicial y PDVB", log_prints=True)
def pdd_initial_backfill_flow(
    business_date: date | None = None,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
) -> dict:
    target_date = business_date or business_today()
    windows = build_pdvb_windows(target_date)

    # Se cargan solo las ventanas utilizadas, evitando materializar los meses
    # intermedios entre la ventana estacional y la reciente.
    seasonal = pdd_features_flow(
        windows.seasonal_start,
        windows.seasonal_end,
        scope_version_uuid,
    )
    current = pdd_features_flow(
        windows.previous_start,
        windows.recent_end,
        scope_version_uuid,
        wait_for=[seasonal],
    )
    pdvb = pdvb_task(
        target_date,
        scope_version_uuid,
        model_version_uuid,
        wait_for=[current],
    )
    return {"seasonal_features": seasonal, "current_features": current, "pdvb": pdvb}


@flow(name="PDD - Corrida analitica diaria", log_prints=True)
def pdd_daily_flow(
    business_date: date | None = None,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
) -> dict:
    target_date = business_date or business_today()
    cutoff_date = target_date - timedelta(days=1)
    features = pdd_features_flow(cutoff_date, cutoff_date, scope_version_uuid)
    pdvb = pdvb_task(
        target_date,
        scope_version_uuid,
        model_version_uuid,
        wait_for=[features],
    )
    return {"features": features, "pdvb": pdvb}


@flow(name="PDD - Backtest analitico", log_prints=True)
def pdd_backtest_flow(
    evaluation_from: date,
    evaluation_to: date,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
    forecast_horizon_days: int = 1,
) -> dict:
    result = backtest_task(
        evaluation_from,
        evaluation_to,
        scope_version_uuid,
        model_version_uuid,
        forecast_horizon_days,
    )
    return {"backtest": result}

