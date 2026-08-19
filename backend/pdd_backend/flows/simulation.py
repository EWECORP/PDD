from __future__ import annotations

from uuid import UUID

from prefect import flow, get_run_logger, task

from pdd_backend.config import OperationalSettings
from pdd_backend.db import build_operational_engine
from pdd_backend.jobs.simulation import simulate_directed_needs_and_publish


@task(name="PDD - Simular, validar y consolidar necesidades E C A")
def simulate_directed_needs_task(
    batch_code: str,
    created_by: str,
    lines_per_type: int = 6,
    shared_pairs: int = 2,
    daily_calculation_run_uuid: str | None = None,
) -> dict:
    settings = OperationalSettings.from_env()
    engine = build_operational_engine(settings)
    try:
        return simulate_directed_needs_and_publish(
            target_engine=engine,
            target_settings=settings,
            batch_code=batch_code,
            created_by=created_by,
            lines_per_type=lines_per_type,
            shared_pairs=shared_pairs,
            daily_calculation_run_uuid=(
                UUID(daily_calculation_run_uuid)
                if daily_calculation_run_uuid
                else None
            ),
        ).serializable()
    finally:
        engine.dispose()


@flow(name="PDD - Simular ECA y publicar backlog DESA")
def pdd_simulate_directed_needs_flow(
    batch_code: str,
    created_by: str,
    lines_per_type: int = 6,
    shared_pairs: int = 2,
    daily_calculation_run_uuid: str | None = None,
) -> dict:
    logger = get_run_logger()
    result = simulate_directed_needs_task(
        batch_code=batch_code,
        created_by=created_by,
        lines_per_type=lines_per_type,
        shared_pairs=shared_pairs,
        daily_calculation_run_uuid=daily_calculation_run_uuid,
    )
    logger.info(
        "Simulacion E/C/A consolidada: batch=%s, fecha=%s, cabeceras=%s, "
        "lineas=%s, totales=%s, backlog=%s, snapshot=%s",
        result["simulation"]["batch_code"],
        result["simulation"]["business_date"],
        result["simulation"]["header_count"],
        result["simulation"]["line_count"],
        result["simulation"]["type_totals"],
        result["backlog"]["backlog_lines"],
        result["backlog"]["snapshot_version"],
    )
    return result
