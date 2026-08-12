"""Valida SQL PDD contra diarco_data sin ejecutar INSERT ni persistir DDL."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from pdd_backend.config import Settings
from pdd_backend.db import build_engine, load_sql, transactional_connection
from pdd_backend.partitioning import ensure_monthly_partitions
from pdd_backend.scope_rules import scope_exclusion_policy_json
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
            {
                "start_date": date(2026, 8, 1),
                "end_date": date(2026, 8, 1),
                "origin_cd": 41,
                "scope_version_uuid": scope_uuid,
            },
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
            valid_month_expansion = connection.execute(
                text(
                    """
                    WITH months(source_year, source_month, expected_days) AS (
                        VALUES (2025, 2, 28), (2026, 6, 30), (2026, 8, 31)
                    ),
                    expanded AS (
                        SELECT
                            m.source_year,
                            m.source_month,
                            m.expected_days,
                            make_date(m.source_year, m.source_month, 1)
                                + (d.source_day - 1) AS stock_date
                        FROM months AS m
                        CROSS JOIN generate_series(1, 31) AS d(source_day)
                        WHERE d.source_day <= extract(
                            day FROM (
                                date_trunc(
                                    'month',
                                    make_date(m.source_year, m.source_month, 1)
                                ) + interval '1 month - 1 day'
                            )
                        )
                    ),
                    verified AS (
                        SELECT
                            source_year,
                            source_month,
                            expected_days,
                            count(*) AS actual_days,
                            max(stock_date) AS actual_month_end
                        FROM expanded
                        GROUP BY source_year, source_month, expected_days
                    )
                    SELECT bool_and(
                        actual_days = expected_days
                        AND actual_month_end = (
                            make_date(source_year, source_month, 1)
                            + (expected_days - 1)
                        )
                    )
                    FROM verified
                    """
                )
            ).scalar_one()
            assert valid_month_expansion
        print("OK conexion y timeouts transaccionales")
        print("OK expansion segura de fin de mes (28/30/31 dias)")

        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(
                    text(load_sql("scope/prepare_scope_snapshot.sql")),
                    {
                        "origin_cd": settings.origin_cd,
                        "exclusion_policy_json": scope_exclusion_policy_json(),
                    },
                )
                excluded_count = connection.execute(
                    text("SELECT count(*) FROM pdd_scope_excluded_categories")
                ).scalar_one()
                assert excluded_count == 2
                print("OK politica de exclusiones del scope (rollback)")
            finally:
                transaction.rollback()

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
