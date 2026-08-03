"""Valida SQL PDD contra diarco_data sin ejecutar INSERT ni persistir DDL."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from pdd_backend.config import Settings
from pdd_backend.db import build_engine, load_sql, transactional_connection
from pdd_backend.partitioning import ensure_monthly_partitions
from pdd_backend.windows import build_pdvb_windows


def main() -> None:
    settings = Settings.from_env()
    engine = build_engine(settings)
    scope_uuid = uuid4()
    model_uuid = uuid4()
    run_uuid = uuid4()
    business_date = date(2026, 8, 2)
    windows = build_pdvb_windows(business_date)

    cases = [
        (
            "stock/upsert_stock_daily.sql",
            {"start_date": date(2026, 8, 1), "end_date": date(2026, 8, 1), "origin_cd": 41},
        ),
        (
            "sales/upsert_sales_daily.sql",
            {
                "start_date": date(2026, 8, 1),
                "end_date": date(2026, 8, 1),
                "origin_cd": 41,
                "scope_version_uuid": scope_uuid,
                "feature_run_uuid": uuid4(),
            },
        ),
        (
            "pdvb/insert_pdvb_detail.sql",
            {
                "business_date": business_date,
                "cutoff_date": windows.cutoff_date,
                "recent_start": windows.recent_start,
                "recent_end": windows.recent_end,
                "previous_start": windows.previous_start,
                "previous_end": windows.previous_end,
                "seasonal_start": windows.seasonal_start,
                "seasonal_end": windows.seasonal_end,
                "origin_cd": 41,
                "scope_version_uuid": scope_uuid,
                "model_version_uuid": model_uuid,
                "calculation_run_uuid": run_uuid,
                "recent_base_weight": Decimal("0.60"),
                "previous_base_weight": Decimal("0.25"),
                "seasonal_base_weight": Decimal("0.15"),
                "minimum_recent_eligible_days": 7,
                "minimum_total_eligible_days": 14,
                "warning_coverage": Decimal("0.70"),
            },
        ),
        (
            "backtest/insert_backtest_detail.sql",
            {
                "evaluation_from": date(2026, 8, 1),
                "evaluation_to": date(2026, 8, 1),
                "forecast_horizon_days": 1,
                "scope_version_uuid": scope_uuid,
                "model_version_uuid": model_uuid,
                "calculation_run_uuid": uuid4(),
                "origin_cd": 41,
            },
        ),
    ]

    try:
        with transactional_connection(engine, settings) as connection:
            connection.execute(text("SELECT 1"))
        print("OK conexion y timeouts transaccionales")

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                names = ensure_monthly_partitions(
                    connection,
                    "dm_pdd_stock_diario",
                    date(2035, 1, 1),
                    date(2035, 2, 1),
                )
                assert len(names) == 2
                print("OK gestor de particiones (rollback)")
            finally:
                transaction.rollback()

        with engine.connect() as connection:
            for relative_path, parameters in cases:
                connection.execute(
                    text("EXPLAIN (COSTS FALSE) " + load_sql(relative_path)),
                    parameters,
                ).all()
                connection.rollback()
                print(f"OK plan SQL: {relative_path}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

