from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..config import Settings
from ..db import transactional_connection


RETENTION_DAYS = 21
def preview_backtest_retention(engine: Engine, days: int = RETENTION_DAYS) -> dict:
    if days <= 0:
        raise ValueError("days debe ser positivo")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT calculation_run_uuid, status, completed_at,
                       evaluation_from, evaluation_to,
                       detail_row_count, metric_row_count
                FROM datamart.dm_pdd_pdvb_backtest_run
                WHERE status IN ('COMPLETED', 'FAILED')
                  AND completed_at < :cutoff
                  AND NOT parameters ? 'detail_purged_at'
                ORDER BY completed_at, calculation_run_uuid
                """
            ),
            {"cutoff": cutoff},
        ).mappings().all()
        actual_rows = {
            row["calculation_run_uuid"]: connection.execute(
                text(
                    """
                    SELECT count(*)
                    FROM datamart.dm_pdd_pdvb_backtest_detail
                    WHERE calculation_run_uuid = :run_uuid
                    """
                ),
                {"run_uuid": row["calculation_run_uuid"]},
            ).scalar_one()
            for row in rows
        }
    return {
        "cutoff_utc": cutoff.isoformat(),
        "runs": [
            {
                "calculation_run_uuid": str(row["calculation_run_uuid"]),
                "status": row["status"],
                "completed_at": row["completed_at"].isoformat(),
                "evaluation_from": row["evaluation_from"].isoformat(),
                "evaluation_to": row["evaluation_to"].isoformat(),
                "recorded_detail_rows": row["detail_row_count"],
                "current_detail_rows": actual_rows[row["calculation_run_uuid"]],
                "retained_metric_rows": row["metric_row_count"],
            }
            for row in rows
        ],
        "recorded_detail_rows": sum(row["detail_row_count"] for row in rows),
        "current_detail_rows": sum(actual_rows.values()),
    }


def purge_backtest_detail(
    engine: Engine,
    settings: Settings,
    *,
    days: int = RETENTION_DAYS,
) -> dict:
    preview = preview_backtest_retention(engine, days)
    cutoff = datetime.fromisoformat(preview["cutoff_utc"])
    results = []
    for item in preview["runs"]:
        run_uuid = UUID(item["calculation_run_uuid"])
        deleted = 0
        evaluation_date = date.fromisoformat(item["evaluation_from"])
        evaluation_to = date.fromisoformat(item["evaluation_to"])
        while evaluation_date <= evaluation_to:
            with transactional_connection(engine, settings) as connection:
                # Serialize concurrent retention invocations without locking backtests.
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('pdd.job.backtest_retention'))")
                )
                eligible = connection.execute(
                    text(
                        """
                        SELECT 1 FROM datamart.dm_pdd_pdvb_backtest_run
                        WHERE calculation_run_uuid = :run_uuid
                          AND status IN ('COMPLETED', 'FAILED')
                          AND completed_at < :cutoff
                          AND NOT parameters ? 'detail_purged_at'
                        FOR UPDATE
                        """
                    ),
                    {"run_uuid": run_uuid, "cutoff": cutoff},
                ).scalar_one_or_none()
                if eligible is None:
                    break
                result = connection.execute(
                    text(
                        """
                        DELETE FROM datamart.dm_pdd_pdvb_backtest_detail
                        WHERE calculation_run_uuid = :run_uuid
                          AND evaluation_date = :evaluation_date
                        """
                    ),
                    {"run_uuid": run_uuid, "evaluation_date": evaluation_date},
                )
                deleted += result.rowcount
            evaluation_date += timedelta(days=1)
        with transactional_connection(engine, settings) as connection:
            connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('pdd.job.backtest_retention'))")
            )
            eligible = connection.execute(
                text(
                    """
                    SELECT 1 FROM datamart.dm_pdd_pdvb_backtest_run
                    WHERE calculation_run_uuid = :run_uuid
                      AND status IN ('COMPLETED', 'FAILED')
                      AND completed_at < :cutoff
                      AND NOT parameters ? 'detail_purged_at'
                    FOR UPDATE
                    """
                ),
                {"run_uuid": run_uuid, "cutoff": cutoff},
            ).scalar_one_or_none()
            if eligible is not None:
                remaining = connection.execute(
                    text(
                        """
                        SELECT count(*) FROM datamart.dm_pdd_pdvb_backtest_detail
                        WHERE calculation_run_uuid = :run_uuid
                        """
                    ),
                    {"run_uuid": run_uuid},
                ).scalar_one()
                if remaining:
                    raise RuntimeError(f"Detalle pendiente para {run_uuid}: {remaining}")
                connection.execute(
                    text(
                        """
                        UPDATE datamart.dm_pdd_pdvb_backtest_run
                        SET parameters = parameters || jsonb_build_object(
                            'detail_purged_at', clock_timestamp(),
                            'detail_retention_days', :days
                        )
                        WHERE calculation_run_uuid = :run_uuid
                        """
                    ),
                    {"run_uuid": run_uuid, "days": days},
                )
        results.append({"calculation_run_uuid": str(run_uuid), "deleted_rows": deleted})
    return {"cutoff_utc": preview["cutoff_utc"], "runs": results}
