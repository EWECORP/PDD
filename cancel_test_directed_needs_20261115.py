"""Close two disposable E needs in TEST that block backlog publication.

Run without arguments for a read-only preflight. ``--apply`` performs all
changes and version records in one guarded transaction.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text


EXPECTED = {
    22: "5b707849-de51-4950-b759-d7cd531becbc",
    24: "f5a7b514-8ff9-472b-83f3-27513acf60c7",
}
LINE_IDS = {73, 74, 75, 76, 295, 296, 297}
ACTOR = "pdd.test.cleanup.20261115"
REASON = (
    "Cancelacion de necesidades E de prueba descartables para articulo 29714 "
    "fuera del scope PDD TEST, autorizada el 15/11/2026"
)
LATEST_DAILY_RUN_ID = 115
LATEST_BUSINESS_DATE = "2026-11-13"


def main(apply: bool) -> None:
    os.environ["PDD_ENV_PATH"] = str(
        Path(__file__).parent / "backend" / ".env"
    )
    sys.path.insert(0, str(Path(__file__).parent / "backend"))
    from pdd_backend.config import OperationalSettings
    from pdd_backend.db import build_operational_engine

    settings = OperationalSettings.from_env()
    if settings.target_environment != "TEST" or settings.pg_database != "connexa_platform_test":
        raise RuntimeError("Esta limpieza solo puede ejecutarse en TEST")
    engine = build_operational_engine(settings)
    try:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '60s'"))
            if conn.execute(text("SELECT current_database()")).scalar_one() != "connexa_platform_test":
                raise RuntimeError("Base de datos inesperada")

            lock = " FOR UPDATE" if apply else ""
            needs = conn.execute(
                text(
                    """SELECT directed_need_id,directed_need_uuid,need_type,status,
                              version_no,closed_at,valid_from,valid_to
                       FROM stock_management.pdd_directed_need
                       WHERE directed_need_id=ANY(CAST(:ids AS bigint[]))
                       ORDER BY directed_need_id""" + lock
                ),
                {"ids": list(EXPECTED)},
            ).mappings().all()
            if len(needs) != 2 or any(
                str(row["directed_need_uuid"]) != EXPECTED[row["directed_need_id"]]
                or row["need_type"] != "E"
                or row["status"] != "ACTIVE"
                or row["version_no"] != 2
                or row["closed_at"] is not None
                for row in needs
            ):
                raise RuntimeError("Las necesidades cambiaron; cancelacion abortada")

            lines = conn.execute(
                text(
                    """SELECT directed_need_line_id,directed_need_id,sucursal,
                              codigo_articulo,status,original_quantity,
                              prepared_allocated_quantity,cancelled_quantity,
                              open_quantity,row_version
                       FROM stock_management.pdd_directed_need_line
                       WHERE directed_need_id=ANY(CAST(:ids AS bigint[]))
                       ORDER BY directed_need_line_id""" + lock
                ),
                {"ids": list(EXPECTED)},
            ).mappings().all()
            if {row["directed_need_line_id"] for row in lines} != LINE_IDS or any(
                row["codigo_articulo"] != 29714
                or row["status"] != "OPEN"
                or row["prepared_allocated_quantity"] != 0
                or row["cancelled_quantity"] != 0
                or row["open_quantity"] != row["original_quantity"]
                for row in lines
            ) or sum(row["open_quantity"] for row in lines) != 565:
                raise RuntimeError("Las lineas cambiaron; cancelacion abortada")

            history = conn.execute(
                text(
                    """SELECT directed_need_id,version_no,after_state
                       FROM stock_management.pdd_directed_need_version
                       WHERE directed_need_id=ANY(CAST(:ids AS bigint[]))
                         AND version_no=2"""
                ),
                {"ids": list(EXPECTED)},
            ).mappings().all()
            if len(history) != 2 or any(
                row["after_state"].get("status") != "ACTIVE" for row in history
            ):
                raise RuntimeError("Historial inesperado; cancelacion abortada")

            orphaned = conn.execute(
                text(
                    """SELECT count(*)
                       FROM stock_management.pdd_directed_need d
                       JOIN stock_management.pdd_directed_need_line l
                         ON l.directed_need_id=d.directed_need_id
                       LEFT JOIN stock_management.pdd_branch_stock_position b
                         ON b.calculation_run_id=:run_id
                        AND b.sucursal=l.sucursal
                        AND b.codigo_articulo=l.codigo_articulo
                       WHERE d.status='ACTIVE'
                         AND d.valid_from<=CAST(:business_date AS date)
                         AND (d.valid_to IS NULL OR d.valid_to>=CAST(:business_date AS date))
                         AND l.open_quantity>0
                         AND (b.branch_stock_position_id IS NULL
                              OR b.calculation_status='BLOCKED')"""
                ),
                {"run_id": LATEST_DAILY_RUN_ID, "business_date": LATEST_BUSINESS_DATE},
            ).scalar_one()
            if orphaned != 7:
                raise RuntimeError(f"Bloqueo cambio: {orphaned} lineas, esperadas 7")

            print("Preflight OK: 2 necesidades E, 7 lineas, 565 unidades abiertas")
            if not apply:
                return

            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            correlation_id = uuid4()
            changed_lines = conn.execute(
                text(
                    """UPDATE stock_management.pdd_directed_need_line
                       SET status='CANCELLED',cancelled_quantity=original_quantity,
                           last_activity_at=:now,row_version=row_version+1
                       WHERE directed_need_line_id=ANY(CAST(:ids AS bigint[]))
                         AND status='OPEN'
                         AND prepared_allocated_quantity=0
                         AND cancelled_quantity=0
                       RETURNING directed_need_line_id"""
                ),
                {"ids": list(LINE_IDS), "now": now},
            ).scalars().all()
            if set(changed_lines) != LINE_IDS:
                raise RuntimeError("Actualizacion parcial de lineas; rollback")

            changed_needs = conn.execute(
                text(
                    """UPDATE stock_management.pdd_directed_need
                       SET status='CANCELLED',closed_at=:now,updated_at=:now,
                           updated_by=:actor,version_no=version_no+1
                       WHERE directed_need_id=ANY(CAST(:ids AS bigint[]))
                         AND status='ACTIVE' AND version_no=2
                       RETURNING directed_need_id,version_no"""
                ),
                {"ids": list(EXPECTED), "now": now, "actor": ACTOR},
            ).all()
            if {row[0] for row in changed_needs} != set(EXPECTED) or any(
                row[1] != 3 for row in changed_needs
            ):
                raise RuntimeError("Actualizacion parcial de cabeceras; rollback")

            for row in history:
                before = row["after_state"]
                after = {
                    **before,
                    "status": "CANCELLED",
                    "closedAt": now.isoformat(),
                    "updatedAt": now.isoformat(),
                    "updatedBy": ACTOR,
                    "versionNo": 3,
                }
                conn.execute(
                    text(
                        """INSERT INTO stock_management.pdd_directed_need_version
                           (directed_need_id,version_no,valid_from_ts,changed_by,
                            change_reason,before_state,after_state,correlation_id)
                           VALUES (:id,3,:now,:actor,:reason,
                                   CAST(:before AS jsonb),CAST(:after AS jsonb),:correlation_id)"""
                    ),
                    {
                        "id": row["directed_need_id"], "now": now,
                        "actor": ACTOR, "reason": REASON,
                        "before": json.dumps(before), "after": json.dumps(after),
                        "correlation_id": correlation_id,
                    },
                )

            remaining = conn.execute(
                text(
                    """SELECT count(*)
                       FROM stock_management.pdd_directed_need d
                       JOIN stock_management.pdd_directed_need_line l
                         ON l.directed_need_id=d.directed_need_id
                       WHERE d.directed_need_id=ANY(CAST(:ids AS bigint[]))
                         AND (d.status<>'CANCELLED' OR l.status<>'CANCELLED'
                              OR l.open_quantity<>0)"""
                ),
                {"ids": list(EXPECTED)},
            ).scalar_one()
            if remaining:
                raise RuntimeError("Cierre incompleto; rollback")
            print(
                "CANCELLED: 2 necesidades, 7 lineas; "
                f"versiones auditadas=2; correlation_id={correlation_id}"
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    main(args.apply)
