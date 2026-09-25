from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import Engine, text

from ..config import Settings
from ..db import transactional_connection


REFRESH_OPEN_PO_SQL = "REFRESH MATERIALIZED VIEW src.mv_base_oc_pendientes"
PIPELINE_UUID_NAMESPACE = UUID("ed496ec6-4098-5c46-85ed-bff20fed24f5")


@dataclass(frozen=True)
class OpenPurchaseOrdersRefreshResult:
    refreshed_at: datetime
    source_as_of_ts: datetime | None
    row_count: int
    positive_lines: int
    excluded_negative_lines: int

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "refreshed_at": self.refreshed_at.isoformat(),
            "source_as_of_ts": (
                self.source_as_of_ts.isoformat() if self.source_as_of_ts else None
            ),
        }


@dataclass(frozen=True)
class DailySourceState:
    raw_sales_date: date | None
    enriched_sales_date: date | None
    stock_source_date: date | None
    canonical_stock_date: date | None
    scoped_sales_date: date | None
    branch_stock_date: date | None
    open_po_as_of_ts: datetime | None
    open_po_row_count: int
    source_sync_run_uuid: str | None
    source_sync_business_date: date | None
    source_sync_status: str | None
    source_sync_refresh_mode: str | None
    source_sync_finished_at: datetime | None
    current_backlog_date: date | None

    def serializable(self) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key, value in self.__dict__.items()
        }


@dataclass(frozen=True)
class DailyPipelineContext:
    status: str
    reason: str | None
    business_date: date
    cutoff_date: date
    feature_start: date | None
    source_state: DailySourceState

    def serializable(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "business_date": self.business_date.isoformat(),
            "cutoff_date": self.cutoff_date.isoformat(),
            "feature_start": (
                self.feature_start.isoformat() if self.feature_start else None
            ),
            "source_state": self.source_state.serializable(),
        }


@dataclass(frozen=True)
class PublishedPdvbRun:
    calculation_run_uuid: UUID
    business_date: date
    model_version_uuid: UUID
    scope_version_uuid: UUID
    origin_cd: int
    row_count: int
    expected_pair_count: int
    publication_batch_uuid: UUID
    published_at: datetime

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "business_date": self.business_date.isoformat(),
            "model_version_uuid": str(self.model_version_uuid),
            "scope_version_uuid": str(self.scope_version_uuid),
            "publication_batch_uuid": str(self.publication_batch_uuid),
            "published_at": self.published_at.isoformat(),
        }


def validate_published_pdvb_run(
    row: dict[str, Any] | None,
    calculation_run_uuid: UUID,
) -> PublishedPdvbRun:
    """Valida que una corrida PDVB completa ya haya atravesado publicación TEST."""
    if row is None:
        raise RuntimeError(
            "La corrida analitica PDVB requerida por DESA no esta disponible: "
            f"{calculation_run_uuid}"
        )

    row_count = int(row["row_count"])
    distinct_pair_count = int(row["distinct_pair_count"])
    expected_pair_count = int(row["expected_pair_count"])
    if row_count != expected_pair_count or distinct_pair_count != expected_pair_count:
        raise RuntimeError(
            "La corrida analitica PDVB no cubre exactamente el scope congelado: "
            f"corrida={calculation_run_uuid}, filas={row_count}, "
            f"pares={distinct_pair_count}, esperados={expected_pair_count}"
        )

    published_row_count = int(row["published_row_count"])
    published_at_row_count = int(row["published_at_row_count"])
    publication_batch_count = int(row["publication_batch_count"])
    if (
        published_row_count != row_count
        or published_at_row_count != row_count
        or publication_batch_count != 1
        or row["publication_batch_uuid"] is None
        or row["published_at"] is None
    ):
        raise RuntimeError(
            "La corrida analitica PDVB todavia no fue publicada completamente por "
            "el proceso operativo precedente: "
            f"corrida={calculation_run_uuid}, publicadas={published_row_count}/"
            f"{row_count}, fechas={published_at_row_count}/{row_count}, "
            f"lotes={publication_batch_count}"
        )

    return PublishedPdvbRun(
        calculation_run_uuid=UUID(str(row["calculation_run_uuid"])),
        business_date=row["business_date"],
        model_version_uuid=UUID(str(row["model_version_uuid"])),
        scope_version_uuid=UUID(str(row["scope_version_uuid"])),
        origin_cd=int(row["origin_cd"]),
        row_count=row_count,
        expected_pair_count=expected_pair_count,
        publication_batch_uuid=UUID(str(row["publication_batch_uuid"])),
        published_at=row["published_at"],
    )


def read_published_pdvb_run(
    source_engine: Engine,
    calculation_run_uuid: UUID,
    business_date: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    origin_cd: int,
) -> PublishedPdvbRun:
    """Lee la corrida determinística de TEST que DESA está autorizado a materializar."""
    with source_engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT
                    e.calculation_run_uuid,
                    e.business_date,
                    e.model_version_uuid,
                    e.scope_version_uuid,
                    e.origin_cd,
                    count(*)::bigint AS row_count,
                    count(DISTINCT (e.codigo_articulo, e.sucursal))::bigint
                        AS distinct_pair_count,
                    s.pair_count::bigint AS expected_pair_count,
                    count(*) FILTER (
                        WHERE e.publication_batch_uuid IS NOT NULL
                    )::bigint AS published_row_count,
                    count(*) FILTER (
                        WHERE e.published_at IS NOT NULL
                    )::bigint AS published_at_row_count,
                    count(DISTINCT e.publication_batch_uuid)::integer
                        AS publication_batch_count,
                    min(e.publication_batch_uuid::text)::uuid
                        AS publication_batch_uuid,
                    max(e.published_at) AS published_at
                FROM datamart.dm_pdd_pdvb_estimate_detail AS e
                INNER JOIN datamart.dm_pdd_scope_version AS s
                    ON s.scope_version_uuid = e.scope_version_uuid
                WHERE e.calculation_run_uuid = CAST(:calculation_run_uuid AS uuid)
                  AND e.business_date = CAST(:business_date AS date)
                  AND e.scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                  AND e.model_version_uuid = CAST(:model_version_uuid AS uuid)
                  AND e.origin_cd = :origin_cd
                GROUP BY
                    e.calculation_run_uuid,
                    e.business_date,
                    e.model_version_uuid,
                    e.scope_version_uuid,
                    e.origin_cd,
                    s.pair_count
                """
            ),
            {
                "calculation_run_uuid": calculation_run_uuid,
                "business_date": business_date,
                "scope_version_uuid": scope_version_uuid,
                "model_version_uuid": model_version_uuid,
                "origin_cd": origin_cd,
            },
        ).mappings().all()
    if len(rows) > 1:
        raise RuntimeError(
            "La corrida analitica PDVB produjo mas de un snapshot logico: "
            f"{calculation_run_uuid}"
        )
    return validate_published_pdvb_run(
        dict(rows[0]) if rows else None,
        calculation_run_uuid,
    )


def refresh_open_purchase_orders(
    source_engine: Engine,
    source_settings: Settings,
) -> OpenPurchaseOrdersRefreshResult:
    """Refresca la fuente canonica de OC y devuelve su fotografia de control."""
    with transactional_connection(source_engine, source_settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": "pdd.source.refresh.mv_base_oc_pendientes"},
        )
        connection.execute(text(REFRESH_OPEN_PO_SQL))
        row = connection.execute(
            text(
                """
                SELECT
                    clock_timestamp() AS refreshed_at,
                    max(fecha_extraccion) AS source_as_of_ts,
                    count(*)::bigint AS row_count,
                    count(*) FILTER (WHERE pendientes > 0)::bigint
                        AS positive_lines,
                    count(*) FILTER (WHERE pendientes < 0)::bigint
                        AS excluded_negative_lines
                FROM src.mv_base_oc_pendientes
                """
            )
        ).mappings().one()
    return OpenPurchaseOrdersRefreshResult(**dict(row))


def read_daily_source_state(
    source_engine: Engine,
    target_engine: Engine,
    scope_version_uuid: UUID,
) -> DailySourceState:
    with source_engine.connect() as connection:
        source = connection.execute(
            text(
                """
                SELECT
                    (SELECT max(fecha)::date
                     FROM src.base_ventas_extendida) AS raw_sales_date,
                    (SELECT max(fecha)::date
                     FROM datamart.dm_bve_ventas_enriquecidas)
                        AS enriched_sales_date,
                    (
                        SELECT max(
                            least(
                                (
                                    date_trunc(
                                        'month',
                                        make_date(c_anio::integer, c_mes::integer, 1)
                                    ) + interval '1 month - 1 day'
                                )::date,
                                coalesce(
                                    fecha_proceso::date - 1,
                                    (
                                        date_trunc(
                                            'month',
                                            make_date(
                                                c_anio::integer,
                                                c_mes::integer,
                                                1
                                            )
                                        ) + interval '1 month - 1 day'
                                    )::date
                                )
                            )
                        )
                        FROM src.t710_estadis_stock
                    ) AS stock_source_date,
                    (SELECT max(stock_date)
                     FROM datamart.dm_pdd_stock_diario) AS canonical_stock_date,
                    (SELECT max(sales_date)
                     FROM datamart.dm_pdd_venta_diaria
                     WHERE scope_version_uuid = CAST(:scope_uuid AS uuid))
                        AS scoped_sales_date,
                    (SELECT max(fecha_stock)::date
                     FROM src.base_stock_sucursal) AS branch_stock_date,
                    (SELECT max(fecha_extraccion)
                     FROM src.mv_base_oc_pendientes) AS open_po_as_of_ts,
                    (SELECT count(*)::bigint
                     FROM src.mv_base_oc_pendientes) AS open_po_row_count,
                    source_sync.source_sync_run_uuid,
                    source_sync.business_date AS source_sync_business_date,
                    source_sync.status AS source_sync_status,
                    source_sync.refresh_mode AS source_sync_refresh_mode,
                    source_sync.finished_at AS source_sync_finished_at
                FROM (VALUES (1)) AS anchor(dummy)
                LEFT JOIN LATERAL (
                    SELECT
                        r.source_sync_run_uuid::text AS source_sync_run_uuid,
                        r.business_date,
                        r.status,
                        r.refresh_mode,
                        r.finished_at
                    FROM audit.pdd_source_sync_run AS r
                    WHERE r.status IN ('READY', 'BLOCKED', 'FAILED')
                    ORDER BY r.business_date DESC, r.started_at DESC
                    LIMIT 1
                ) AS source_sync ON true
                """
            ),
            {"scope_uuid": scope_version_uuid},
        ).mappings().one()

    with target_engine.connect() as connection:
        current_backlog_date = connection.execute(
            text(
                """
                SELECT max(r.business_date)
                FROM stock_management.pdd_calculation_run AS r
                INNER JOIN stock_management.pdd_distribution_scope_version AS s
                    ON s.scope_version_id = r.scope_version_id
                WHERE r.run_type = 'PUBLISH'
                  AND r.scope_id = '41:BACKLOG'
                  AND r.status = 'SUCCEEDED'
                  AND r.is_current
                  AND s.scope_version_uuid = CAST(:scope_uuid AS uuid)
                """
            ),
            {"scope_uuid": scope_version_uuid},
        ).scalar_one()

    return DailySourceState(
        **dict(source),
        current_backlog_date=current_backlog_date,
    )


def resolve_daily_pipeline_context(
    state: DailySourceState,
    requested_business_date: date | None,
    today: date,
    force: bool = False,
) -> DailyPipelineContext:
    upstream = {
        "raw_sales_date": state.raw_sales_date,
        "enriched_sales_date": state.enriched_sales_date,
        "stock_source_date": state.stock_source_date,
    }
    missing = [name for name, value in upstream.items() if value is None]
    if missing:
        raise RuntimeError(
            "No se pudo determinar el cierre de las fuentes analiticas: "
            + ", ".join(missing)
        )

    common_closed_date = min(value for value in upstream.values() if value is not None)
    business_date = requested_business_date or common_closed_date + timedelta(days=1)
    cutoff_date = business_date - timedelta(days=1)

    if business_date > today:
        raise RuntimeError(
            f"La fecha operativa {business_date} es futura; fecha local actual={today}"
        )
    stale = [
        f"{name}={value}"
        for name, value in upstream.items()
        if value is None or value < cutoff_date
    ]
    if stale:
        raise RuntimeError(
            f"Las fuentes no alcanzan el corte {cutoff_date}: " + ", ".join(stale)
        )
    if (
        state.source_sync_business_date != business_date
        or state.source_sync_status != "READY"
    ):
        raise RuntimeError(
            "El contrato auditado de fuentes no esta READY para la fecha operativa "
            f"{business_date}; run={state.source_sync_run_uuid}, "
            f"fecha={state.source_sync_business_date}, status={state.source_sync_status}"
        )
    # La foto reconstruida durante D representa la posición al cierre de D-1.
    # La evidencia de que fue extraída en D ya forma parte del contrato fuente
    # auditado y vuelve a validarse en inspect_stock_readiness.
    if state.branch_stock_date is None or state.branch_stock_date < cutoff_date:
        raise RuntimeError(
            "La posicion de stock de sucursal no alcanza el cierre requerido "
            f"{cutoff_date}; disponible={state.branch_stock_date}"
        )
    if (
        not force
        and state.current_backlog_date is not None
        and state.current_backlog_date >= business_date
    ):
        return DailyPipelineContext(
            status="SKIPPED",
            reason="NO_NEW_CLOSED_DATE",
            business_date=business_date,
            cutoff_date=cutoff_date,
            feature_start=None,
            source_state=state,
        )

    if state.canonical_stock_date is None or state.scoped_sales_date is None:
        raise RuntimeError(
            "El scope no tiene features canonicas previas. Ejecute primero "
            "PDD_INITIAL_BACKFILL_MANUAL."
        )
    latest_complete_feature = min(
        state.canonical_stock_date,
        state.scoped_sales_date,
    )
    feature_start = min(latest_complete_feature + timedelta(days=1), cutoff_date)

    return DailyPipelineContext(
        status="READY",
        reason=None,
        business_date=business_date,
        cutoff_date=cutoff_date,
        feature_start=feature_start,
        source_state=state,
    )


def pipeline_stage_uuid(
    stage: str,
    business_date: date,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    configuration_version_uuid: UUID,
    pipeline_revision: str,
) -> UUID:
    normalized_stage = stage.strip().upper()
    normalized_revision = pipeline_revision.strip().upper()
    if not normalized_stage or not normalized_revision:
        raise ValueError("stage y pipeline_revision son obligatorios")
    identity = "|".join(
        (
            normalized_revision,
            normalized_stage,
            business_date.isoformat(),
            str(scope_version_uuid),
            str(model_version_uuid),
            str(configuration_version_uuid),
        )
    )
    return uuid5(PIPELINE_UUID_NAMESPACE, identity)


def pipeline_stage_revision(
    stage: str,
    pipeline_revision: str,
    stock_date: date,
) -> str:
    """Version operational stages by the effective stock snapshot date."""
    normalized_stage = stage.strip().upper()
    if normalized_stage in {"DAILY_DECAS", "BACKLOG"}:
        return f"{pipeline_revision}:STOCK:{stock_date.isoformat()}"
    return pipeline_revision
