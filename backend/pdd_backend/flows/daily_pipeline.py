from __future__ import annotations

from datetime import date
from uuid import UUID

from prefect import flow, get_run_logger, task

from pdd_backend.clock import business_today
from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.flows.analytical import _uuid, pdd_features_flow
from pdd_backend.flows.operational_inputs import (
    daily_decas_task,
    inspect_stock_readiness_task,
    publish_backlog_task,
    publish_item_logistics_task,
)
from pdd_backend.flows.publisher import publish_pdvb_task
from pdd_backend.jobs.daily_pipeline import (
    pipeline_stage_revision,
    pipeline_stage_uuid,
    read_published_pdvb_run,
    read_daily_source_state,
    refresh_open_purchase_orders,
    resolve_daily_pipeline_context,
)
from pdd_backend.jobs.pdvb import calculate_pdvb


DEFAULT_CONFIGURATION_VERSION_UUID = "2f916828-c59d-4190-a795-29ac5cfc1a66"


@task(
    name="PDD - Refrescar OC pendientes canonicas",
    retries=2,
    retry_delay_seconds=120,
)
def refresh_open_purchase_orders_task() -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        return refresh_open_purchase_orders(engine, settings).serializable()
    finally:
        engine.dispose()


@task(name="PDD - Resolver fecha y cierre diario")
def resolve_daily_context_task(
    business_date: date | None,
    scope_version_uuid: str | None,
    model_version_uuid: str | None,
    force: bool,
) -> dict:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    scope_uuid = _uuid(
        scope_version_uuid,
        source_settings.scope_version_uuid,
        "scope_version_uuid",
    )
    model_uuid = _uuid(
        model_version_uuid,
        source_settings.model_version_uuid,
        "model_version_uuid",
    )
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        state = read_daily_source_state(source_engine, target_engine, scope_uuid)
        context = resolve_daily_pipeline_context(
            state,
            requested_business_date=business_date,
            today=business_today(),
            force=force,
        )
        return {
            **context.serializable(),
            "scope_version_uuid": str(scope_uuid),
            "model_version_uuid": str(model_uuid),
        }
    finally:
        target_engine.dispose()
        source_engine.dispose()


@task(name="PDD - Calcular detalle PDVB diario", retries=1, retry_delay_seconds=60)
def daily_pdvb_task(
    business_date: date,
    scope_version_uuid: str,
    model_version_uuid: str,
    calculation_run_uuid: str,
) -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        result, run_uuid = calculate_pdvb(
            engine,
            settings,
            business_date,
            UUID(scope_version_uuid),
            UUID(model_version_uuid),
            UUID(calculation_run_uuid),
        )
        return {**result.__dict__, "calculation_run_uuid": str(run_uuid)}
    finally:
        engine.dispose()


@task(name="PDD - Validar destino operativo DESA")
def validate_desa_target_task() -> dict:
    settings = OperationalSettings.from_env()
    if settings.target_environment != "DESA":
        raise RuntimeError(
            "PDD_OPERATIONAL_PUBLISH_DESA_DAILY solo puede ejecutarse con "
            "PDD_OPERATIONAL_TARGET_ENV=DESA"
        )
    return {
        "target_environment": settings.target_environment,
        "target_database": settings.pg_database,
    }


@task(
    name="PDD - Esperar corrida PDVB publicada",
    retries=6,
    retry_delay_seconds=600,
)
def require_published_pdvb_task(
    calculation_run_uuid: str,
    business_date: date,
    scope_version_uuid: str,
    model_version_uuid: str,
) -> dict:
    settings = Settings.from_env()
    engine = build_engine(settings)
    try:
        return read_published_pdvb_run(
            source_engine=engine,
            calculation_run_uuid=UUID(calculation_run_uuid),
            business_date=business_date,
            scope_version_uuid=UUID(scope_version_uuid),
            model_version_uuid=UUID(model_version_uuid),
            origin_cd=settings.origin_cd,
        ).serializable()
    finally:
        engine.dispose()


@flow(name="PDD - Orquestador diario completo", log_prints=True)
def pdd_operational_daily_flow(
    business_date: date | None = None,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
    configuration_version_uuid: str = DEFAULT_CONFIGURATION_VERSION_UUID,
    created_by: str = "pdd.daily.orchestrator",
    pipeline_revision: str = "DAILY_PIPELINE_V2",
    force: bool = False,
) -> dict:
    logger = get_run_logger()
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")
    configuration_uuid = UUID(configuration_version_uuid)

    context = resolve_daily_context_task(
        business_date,
        scope_version_uuid,
        model_version_uuid,
        force,
    )
    if context["status"] == "SKIPPED":
        logger.info(
            "Pipeline diario omitido: fecha=%s, motivo=%s, backlog_actual=%s",
            context["business_date"],
            context["reason"],
            context["source_state"]["current_backlog_date"],
        )
        return {
            "status": "SKIPPED",
            "context": context,
        }

    target_date = date.fromisoformat(context["business_date"])
    cutoff_date = date.fromisoformat(context["cutoff_date"])
    feature_start = date.fromisoformat(context["feature_start"])
    scope_uuid = UUID(context["scope_version_uuid"])
    model_uuid = UUID(context["model_version_uuid"])

    readiness = inspect_stock_readiness_task(
        target_date,
        str(scope_uuid),
        wait_for=[context],
    )
    if readiness["status"] != "READY":
        raise RuntimeError(
            "Fuentes operativas no preparadas: "
            + ", ".join(readiness["blockers"])
        )
    stock_date = date.fromisoformat(readiness["stock_date"])

    run_ids = {
        stage: str(
            pipeline_stage_uuid(
                stage,
                target_date,
                scope_uuid,
                model_uuid,
                configuration_uuid,
                pipeline_stage_revision(stage, pipeline_revision, stock_date),
            )
        )
        for stage in ("PDVB", "ITEM_LOGISTICS", "DAILY_DECAS", "BACKLOG")
    }

    features = pdd_features_flow(
        feature_start,
        cutoff_date,
        str(scope_uuid),
        wait_for=[readiness],
    )
    pdvb = daily_pdvb_task(
        target_date,
        str(scope_uuid),
        str(model_uuid),
        run_ids["PDVB"],
        wait_for=[features],
    )
    pdvb_publication = publish_pdvb_task(
        pdvb["calculation_run_uuid"],
        created_by,
        wait_for=[pdvb],
    )
    logistics = publish_item_logistics_task(
        target_date,
        created_by,
        str(scope_uuid),
        run_ids["ITEM_LOGISTICS"],
        wait_for=[pdvb_publication],
    )
    daily_decas = daily_decas_task(
        target_date,
        stock_date,
        pdvb["calculation_run_uuid"],
        logistics["calculation_run_uuid"],
        str(configuration_uuid),
        created_by,
        str(scope_uuid),
        run_ids["DAILY_DECAS"],
        wait_for=[logistics],
    )
    backlog = publish_backlog_task(
        daily_decas["calculation_run_uuid"],
        created_by,
        run_ids["BACKLOG"],
        wait_for=[daily_decas],
    )

    logger.info(
        "Pipeline diario completado: fecha=%s, fecha_stock=%s, PDVB=%s, DAILY_DECAS=%s, "
        "backlog=%s, lineas=%s",
        target_date,
        stock_date,
        pdvb["calculation_run_uuid"],
        daily_decas["calculation_run_uuid"],
        backlog["calculation_run_uuid"],
        backlog["backlog_lines"],
    )
    return {
        "status": "COMPLETED",
        "pipeline_revision": pipeline_revision,
        "context": context,
        "run_ids": run_ids,
        "readiness": readiness,
        "features": features,
        "pdvb": pdvb,
        "pdvb_publication": pdvb_publication,
        "item_logistics": logistics,
        "daily_decas": daily_decas,
        "backlog": backlog,
    }


@flow(name="PDD - Publicacion operativa diaria DESA", log_prints=True)
def pdd_operational_publish_desa_flow(
    business_date: date | None = None,
    scope_version_uuid: str | None = None,
    model_version_uuid: str | None = None,
    configuration_version_uuid: str = DEFAULT_CONFIGURATION_VERSION_UUID,
    created_by: str = "pdd.operational.publisher.desa",
    pipeline_revision: str = "DAILY_PIPELINE_V2",
    source_calculation_run_uuid: str | None = None,
    force: bool = False,
) -> dict:
    """Materializa en DESA una corrida analítica ya calculada y publicada por TEST."""
    logger = get_run_logger()
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")
    configuration_uuid = UUID(configuration_version_uuid)

    target = validate_desa_target_task()
    context = resolve_daily_context_task(
        business_date,
        scope_version_uuid,
        model_version_uuid,
        force,
        wait_for=[target],
    )
    if context["status"] == "SKIPPED":
        logger.info(
            "Publicacion diaria DESA omitida: fecha=%s, motivo=%s, backlog_actual=%s",
            context["business_date"],
            context["reason"],
            context["source_state"]["current_backlog_date"],
        )
        return {
            "status": "SKIPPED",
            "context": context,
            "target": target,
        }

    target_date = date.fromisoformat(context["business_date"])
    scope_uuid = UUID(context["scope_version_uuid"])
    model_uuid = UUID(context["model_version_uuid"])
    expected_pdvb_uuid = pipeline_stage_uuid(
        "PDVB",
        target_date,
        scope_uuid,
        model_uuid,
        configuration_uuid,
        pipeline_revision,
    )
    pdvb_uuid = (
        UUID(source_calculation_run_uuid)
        if source_calculation_run_uuid
        else expected_pdvb_uuid
    )

    analytical_pdvb = require_published_pdvb_task(
        str(pdvb_uuid),
        target_date,
        str(scope_uuid),
        str(model_uuid),
        wait_for=[context],
    )
    readiness = inspect_stock_readiness_task(
        target_date,
        str(scope_uuid),
        wait_for=[analytical_pdvb],
    )
    if readiness["status"] != "READY":
        raise RuntimeError(
            "Fuentes operativas no preparadas: "
            + ", ".join(readiness["blockers"])
        )
    stock_date = date.fromisoformat(readiness["stock_date"])

    run_ids = {
        stage: str(
            pipeline_stage_uuid(
                stage,
                target_date,
                scope_uuid,
                model_uuid,
                configuration_uuid,
                pipeline_stage_revision(stage, pipeline_revision, stock_date),
            )
        )
        for stage in ("ITEM_LOGISTICS", "DAILY_DECAS", "BACKLOG")
    }
    run_ids["PDVB"] = str(pdvb_uuid)

    pdvb_publication = publish_pdvb_task(
        analytical_pdvb["calculation_run_uuid"],
        created_by,
        wait_for=[readiness],
    )
    logistics = publish_item_logistics_task(
        target_date,
        created_by,
        str(scope_uuid),
        run_ids["ITEM_LOGISTICS"],
        wait_for=[pdvb_publication],
    )
    daily_decas = daily_decas_task(
        target_date,
        stock_date,
        analytical_pdvb["calculation_run_uuid"],
        logistics["calculation_run_uuid"],
        str(configuration_uuid),
        created_by,
        str(scope_uuid),
        run_ids["DAILY_DECAS"],
        wait_for=[logistics],
    )
    backlog = publish_backlog_task(
        daily_decas["calculation_run_uuid"],
        created_by,
        run_ids["BACKLOG"],
        wait_for=[daily_decas],
    )

    logger.info(
        "Publicacion diaria DESA completada: fecha=%s, fecha_stock=%s, PDVB=%s, "
        "DAILY_DECAS=%s, backlog=%s, lineas=%s",
        target_date,
        stock_date,
        analytical_pdvb["calculation_run_uuid"],
        daily_decas["calculation_run_uuid"],
        backlog["calculation_run_uuid"],
        backlog["backlog_lines"],
    )
    return {
        "status": "COMPLETED",
        "pipeline_revision": pipeline_revision,
        "context": context,
        "target": target,
        "run_ids": run_ids,
        "analytical_pdvb": analytical_pdvb,
        "readiness": readiness,
        "pdvb_publication": pdvb_publication,
        "item_logistics": logistics,
        "daily_decas": daily_decas,
        "backlog": backlog,
    }
