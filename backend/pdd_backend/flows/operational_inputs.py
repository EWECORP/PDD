from __future__ import annotations

from datetime import date
from uuid import UUID

from prefect import flow, get_run_logger, task

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.jobs.operational_inputs import (
    inspect_stock_readiness,
    publish_item_logistics,
)
from pdd_backend.jobs.daily_decas import run_daily_decas
from pdd_backend.jobs.backlog import publish_current_backlog


@task(name="PDD - Publicar datos logisticos de articulos")
def publish_item_logistics_task(
    business_date: date,
    created_by: str,
    scope_version_uuid: str | None = None,
    calculation_run_uuid: str | None = None,
) -> dict:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    scope_uuid = source_settings.require_scope_uuid(
        UUID(scope_version_uuid) if scope_version_uuid else None
    )
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        return publish_item_logistics(
            source_engine=source_engine,
            source_settings=source_settings,
            target_engine=target_engine,
            target_settings=target_settings,
            business_date=business_date,
            scope_version_uuid=scope_uuid,
            created_by=created_by,
            calculation_run_uuid=(
                UUID(calculation_run_uuid) if calculation_run_uuid else None
            ),
        ).serializable()
    finally:
        target_engine.dispose()
        source_engine.dispose()


@flow(name="PDD - Publicar datos logisticos en stock_management", log_prints=True)
def pdd_publish_item_logistics_flow(
    business_date: date,
    created_by: str,
    scope_version_uuid: str | None = None,
    calculation_run_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    result = publish_item_logistics_task(
        business_date,
        created_by,
        scope_version_uuid,
        calculation_run_uuid,
    )
    logger.info(
        "Datos logisticos publicados: corrida=%s, registros=%s, calidad=%s",
        result["calculation_run_uuid"],
        result["published_rows"],
        result["quality_counts"],
    )
    return {"item_logistics": result}


@task(name="PDD - Diagnosticar fuente de stock")
def inspect_stock_readiness_task(
    expected_through: date,
    scope_version_uuid: str | None = None,
) -> dict:
    settings = Settings.from_env()
    scope_uuid = settings.require_scope_uuid(
        UUID(scope_version_uuid) if scope_version_uuid else None
    )
    engine = build_engine(settings)
    try:
        return inspect_stock_readiness(
            engine,
            scope_uuid,
            expected_through,
        ).serializable()
    finally:
        engine.dispose()


@flow(name="PDD - Diagnosticar preparacion de stock", log_prints=True)
def pdd_stock_readiness_flow(
    expected_through: date,
    scope_version_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    result = inspect_stock_readiness_task(expected_through, scope_version_uuid)
    logger.info(
        "Diagnostico stock: estado=%s, fecha=%s, cobertura=%s/%s, "
        "pares_sucursal_excluida=%s, faltantes_no_explicados=%s, "
        "sucursales_excluidas=%s, bloqueos=%s",
        result["status"],
        result["stock_date"],
        result["covered_pairs"],
        result["scope_pairs"],
        result["excluded_branch_pairs"],
        result["unexplained_missing_pairs"],
        result["excluded_branches"],
        result["blockers"],
    )
    return {"stock_readiness": result}


@task(name="PDD - Construir posiciones y necesidades D y S")
def daily_decas_task(
    business_date: date,
    pdvb_calculation_run_uuid: str,
    logistics_calculation_run_uuid: str,
    configuration_version_uuid: str,
    created_by: str,
    scope_version_uuid: str | None = None,
    calculation_run_uuid: str | None = None,
) -> dict:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    scope_uuid = source_settings.require_scope_uuid(
        UUID(scope_version_uuid) if scope_version_uuid else None
    )
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        return run_daily_decas(
            source_engine=source_engine,
            source_settings=source_settings,
            target_engine=target_engine,
            target_settings=target_settings,
            business_date=business_date,
            scope_version_uuid=scope_uuid,
            pdvb_calculation_run_uuid=UUID(pdvb_calculation_run_uuid),
            logistics_calculation_run_uuid=UUID(logistics_calculation_run_uuid),
            configuration_version_uuid=UUID(configuration_version_uuid),
            created_by=created_by,
            calculation_run_uuid=(
                UUID(calculation_run_uuid) if calculation_run_uuid else None
            ),
        ).serializable()
    finally:
        target_engine.dispose()
        source_engine.dispose()


@flow(name="PDD - Calcular posiciones y necesidades D y S", log_prints=True)
def pdd_daily_decas_flow(
    business_date: date,
    pdvb_calculation_run_uuid: str,
    logistics_calculation_run_uuid: str,
    configuration_version_uuid: str,
    created_by: str,
    scope_version_uuid: str | None = None,
    calculation_run_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    result = daily_decas_task(
        business_date,
        pdvb_calculation_run_uuid,
        logistics_calculation_run_uuid,
        configuration_version_uuid,
        created_by,
        scope_version_uuid,
        calculation_run_uuid,
    )
    logger.info(
        "DAILY_DECAS completado: corrida=%s, posiciones=%s, necesidades=%s, "
        "stock_cd=%s, pdvb_bloqueados_excluidos=%s",
        result["calculation_run_uuid"],
        result["branch_positions"],
        result["need_rows"],
        result["cd_positions"],
        result["excluded_blocked_pdvb"],
    )
    return {"daily_decas": result}


@task(name="PDD - Consolidar y publicar backlog DECAS")
def publish_backlog_task(
    daily_calculation_run_uuid: str,
    created_by: str,
    calculation_run_uuid: str | None = None,
) -> dict:
    target_settings = OperationalSettings.from_env()
    target_engine = build_operational_engine(target_settings)
    try:
        return publish_current_backlog(
            target_engine=target_engine,
            target_settings=target_settings,
            source_daily_run_uuid=UUID(daily_calculation_run_uuid),
            created_by=created_by,
            calculation_run_uuid=(
                UUID(calculation_run_uuid) if calculation_run_uuid else None
            ),
        ).serializable()
    finally:
        target_engine.dispose()


@flow(name="PDD - Publicar backlog DECAS vigente", log_prints=True)
def pdd_publish_backlog_flow(
    daily_calculation_run_uuid: str,
    created_by: str,
    calculation_run_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    result = publish_backlog_task(
        daily_calculation_run_uuid,
        created_by,
        calculation_run_uuid,
    )
    logger.info(
        "Backlog DECAS publicado: corrida=%s, snapshot=%s, lineas=%s, "
        "fuentes=%s, totales=%s, frescura=%s",
        result["calculation_run_uuid"],
        result["snapshot_version"],
        result["backlog_lines"],
        result["allocation_rows"],
        result["type_totals"],
        result["freshness_counts"],
    )
    return {"backlog": result}
