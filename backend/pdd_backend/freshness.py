from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class SourceFreshness:
    raw_sales_date: date | None
    enriched_sales_date: date | None
    stock_source_date: date | None
    canonical_stock_date: date | None

    @property
    def common_closed_date(self) -> date | None:
        values = (
            self.raw_sales_date,
            self.enriched_sales_date,
            self.stock_source_date,
            self.canonical_stock_date,
        )
        if any(value is None for value in values):
            return None
        return min(value for value in values if value is not None)


def read_source_freshness(engine: Engine) -> SourceFreshness:
    sql = text(
        """
        SELECT
            (SELECT max(fecha)::date FROM src.base_ventas_extendida) AS raw_sales_date,
            (SELECT max(fecha)::date FROM datamart.dm_bve_ventas_enriquecidas)
                AS enriched_sales_date,
            (
                SELECT max(
                    least(
                        (
                            date_trunc('month', make_date(c_anio::integer, c_mes::integer, 1))
                            + interval '1 month - 1 day'
                        )::date,
                        coalesce(
                            fecha_proceso::date - 1,
                            (
                                date_trunc('month', make_date(c_anio::integer, c_mes::integer, 1))
                                + interval '1 month - 1 day'
                            )::date
                        )
                    )
                )
                FROM src.t710_estadis_stock
            ) AS stock_source_date,
            (SELECT max(stock_date) FROM datamart.dm_pdd_stock_diario)
                AS canonical_stock_date
        """
    )
    with engine.connect() as connection:
        row = connection.execute(sql).mappings().one()
    return SourceFreshness(**dict(row))


def require_closed_through(freshness: SourceFreshness, requested_end: date) -> date:
    common = freshness.common_closed_date
    if common is None:
        raise RuntimeError(f"No se pudo determinar el cierre comun de fuentes: {freshness}")
    if requested_end > common:
        raise RuntimeError(
            f"La fecha solicitada {requested_end} supera el cierre comun {common}. "
            f"Fuentes: {freshness}"
        )
    return common

