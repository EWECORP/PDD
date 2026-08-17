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
                     FROM src.mv_base_oc_pendientes) AS open_po_row_count
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
    if state.branch_stock_date is None or state.branch_stock_date < business_date:
        raise RuntimeError(
            "La posicion de stock de sucursal no alcanza la fecha operativa "
            f"{business_date}; disponible={state.branch_stock_date}"
        )
    if (
        state.open_po_as_of_ts is None
        or state.open_po_as_of_ts.date() < business_date
    ):
        raise RuntimeError(
            "La vista canonica de OC no quedo actualizada para la fecha operativa "
            f"{business_date}; as_of={state.open_po_as_of_ts}"
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
