from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Connection


ALLOWED_PARTITIONED_TABLES = {
    "dm_pdd_stock_diario",
    "dm_pdd_venta_diaria",
    "dm_pdd_pdvb_estimate_detail",
    "dm_pdd_pdvb_backtest_detail",
}


@dataclass(frozen=True)
class MonthRange:
    start: date
    end: date

    @property
    def suffix(self) -> str:
        return f"{self.start.year:04d}_{self.start.month:02d}"


def first_day_next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def iter_months(start_date: date, end_date: date) -> Iterator[MonthRange]:
    if end_date < start_date:
        raise ValueError("end_date no puede ser anterior a start_date")
    current = date(start_date.year, start_date.month, 1)
    final = date(end_date.year, end_date.month, 1)
    while current <= final:
        next_month = first_day_next_month(current)
        yield MonthRange(current, next_month)
        current = next_month


def ensure_monthly_partitions(
    connection: Connection,
    table_name: str,
    start_date: date,
    end_date: date,
) -> list[str]:
    if table_name not in ALLOWED_PARTITIONED_TABLES:
        raise ValueError(f"Tabla particionada no autorizada: {table_name}")

    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
        {"lock_name": f"pdd.partition.datamart.{table_name}"},
    )
    created_or_existing: list[str] = []
    for month in iter_months(start_date, end_date):
        partition_name = f"{table_name}_{month.suffix}"
        # table_name proviene de una allowlist y el sufijo solo contiene digitos/_;
        # los valores de borde permanecen parametrizados.
        ddl = text(
            f"CREATE TABLE IF NOT EXISTS datamart.{partition_name} "
            f"PARTITION OF datamart.{table_name} "
            "FOR VALUES FROM (:from_date) TO (:to_date)"
        )
        connection.execute(
            ddl,
            {"from_date": month.start, "to_date": month.end},
        )
        created_or_existing.append(partition_name)
    return created_or_existing

