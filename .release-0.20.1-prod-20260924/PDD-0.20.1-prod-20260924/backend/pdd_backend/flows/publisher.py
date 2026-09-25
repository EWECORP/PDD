from __future__ import annotations

from uuid import UUID

from prefect import flow, get_run_logger, task

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.jobs.publisher import publish_pdvb


@task(name="PDD - Publicar PDVB en stock_management")
def publish_pdvb_task(
    calculation_run_uuid: str,
    created_by: str,
) -> dict:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        result = publish_pdvb(
            source_engine,
            source_settings,
            target_engine,
            target_settings,
            UUID(calculation_run_uuid),
            created_by,
        )
        return result.serializable()
    finally:
        target_engine.dispose()
        source_engine.dispose()


@flow(name="PDD - Publicar PDVB en stock_management", log_prints=True)
def pdd_publish_pdvb_flow(
    calculation_run_uuid: str,
    created_by: str,
) -> dict:
    logger = get_run_logger()
    result = publish_pdvb_task(calculation_run_uuid, created_by)
    logger.info(
        "Publicacion PDVB completada: corrida=%s, destino=stock_management.pdd_pdvb_current",
        calculation_run_uuid,
    )
    return {"publication": result}
