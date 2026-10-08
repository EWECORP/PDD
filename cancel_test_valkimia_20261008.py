"""Cancel the seven disposable Valkimia pilot imports in Connexa TEST.

Run without arguments for a read-only preflight; use --apply for the guarded,
single-transaction cancellation. Requires backend/.env and asyncpg.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from dotenv import dotenv_values


EXPECTED = {
    5: "5379e2bb-3c9c-4e6e-9df8-88048667baa8",
    6: "081fcdc4-6537-48dd-a1c6-d81827124846",
    7: "838dd3d3-ffd4-4ff0-9aac-db5570a0f927",
    8: "89abccc7-d5a1-4d21-9675-e4d9d4a884a2",
    9: "9f163e56-7ee8-49ea-8d9d-c5c43c89c7c0",
    10: "48fd20ee-4411-4c0f-9167-65d1586ed421",
    11: "ae605f93-4384-4ba2-bd6d-e5296102496a",
}
IDS = list(EXPECTED)
ACTOR = "pdd.test.cleanup"
REASON = (
    "Cancelacion de siete artefactos de prueba Valkimia, confirmados "
    "descartables el 08/10/2026, para validar el backlog diario en TEST"
)
AUDIT = json.dumps({"test_cleanup": {"actor": ACTOR, "reason": REASON}})


async def count_updated(conn: asyncpg.Connection, sql: str, *args: object) -> int:
    return int(await conn.fetchval(f"WITH changed AS ({sql} RETURNING 1) SELECT count(*) FROM changed", *args))


async def preflight(conn: asyncpg.Connection, lock: bool) -> tuple[list[int], list[int], int, int]:
    if await conn.fetchval("SELECT current_database()") != "connexa_platform_test":
        raise RuntimeError("Destination is not connexa_platform_test")
    suffix = " FOR UPDATE OF i, t, p" if lock else ""
    rows = await conn.fetch(
        """
        SELECT i.valkimia_import_id, i.valkimia_import_uuid, i.status,
               i.origin_cd, i.imported_at, i.last_polled_at,
               i.line_count, i.total_imported_quantity,
               t.dispatch_trip_id, t.status AS trip_status,
               p.dispatch_plan_id, p.status AS plan_status
        FROM stock_management.pdd_valkimia_import i
        JOIN stock_management.pdd_dispatch_trip t ON t.dispatch_trip_id = i.dispatch_trip_id
        JOIN stock_management.pdd_dispatch_plan p ON p.dispatch_plan_id = t.dispatch_plan_id
        WHERE i.valkimia_import_id = ANY($1::bigint[])
        ORDER BY i.valkimia_import_id
        """ + suffix,
        IDS,
    )
    if len(rows) != len(IDS):
        raise RuntimeError(f"Expected seven imports, found {len(rows)}")
    for row in rows:
        ident = row["valkimia_import_id"]
        if (
            str(row["valkimia_import_uuid"]) != EXPECTED[ident]
            or row["status"] != "PENDING"
            or row["origin_cd"] != 41
            or row["imported_at"] is not None
            or row["last_polled_at"] is not None
            or row["trip_status"] != "PUBLISH_PENDING"
            or row["plan_status"] != "APPROVED"
        ):
            raise RuntimeError(f"Import {ident} changed; cancellation aborted")
    if await conn.fetchval(
        """SELECT count(*) FROM stock_management.pdd_valkimia_import
           WHERE origin_cd=41 AND status IN ('PENDING','ACCEPTED','PARTIAL')"""
    ) != len(IDS):
        raise RuntimeError("Other active Valkimia imports exist")
    trip_ids = [row["dispatch_trip_id"] for row in rows]
    plan_ids = [row["dispatch_plan_id"] for row in rows]
    if len(set(trip_ids)) != 7 or len(set(plan_ids)) != 7:
        raise RuntimeError("Trips or plans are shared")
    for table, key, values in (
        ("pdd_dispatch_trip", "dispatch_plan_id", plan_ids),
        ("pdd_valkimia_import", "dispatch_trip_id", trip_ids),
    ):
        n = await conn.fetchval(
            f"SELECT count(*) FROM stock_management.{table} WHERE {key}=ANY($1::bigint[])",
            values,
        )
        if n != 7:
            raise RuntimeError(f"Unexpected related rows in {table}: {n}")
    lines = await conn.fetchrow(
        """
        SELECT count(*) AS n,
               count(*) FILTER (WHERE l.status_id <> 1 OR l.last_external_status IS NOT NULL
                   OR l.last_polled_at IS NOT NULL OR l.last_external_updated_at IS NOT NULL
                   OR l.accepted_quantity <> 0
                   OR l.prepared_quantity <> 0 OR l.dispatched_quantity <> 0
                   OR l.delivered_quantity <> 0 OR l.cancelled_quantity <> 0
                   OR l.rejected_quantity <> 0 OR t.status <> 'PUBLISH_PENDING'
                   OR t.published_quantity <> l.imported_quantity
                   OR t.accepted_quantity <> 0 OR t.prepared_quantity <> 0
                   OR t.dispatched_quantity <> 0 OR t.delivered_quantity <> 0
                   OR t.rejected_quantity <> 0 OR t.cancelled_quantity <> 0) AS invalid,
               sum(l.imported_quantity) AS quantity
        FROM stock_management.pdd_valkimia_import_line l
        JOIN stock_management.pdd_dispatch_trip_line t
          ON t.dispatch_trip_line_id=l.dispatch_trip_line_id
        WHERE l.valkimia_import_id=ANY($1::bigint[])
        """,
        IDS,
    )
    if lines["n"] != 1589 or lines["invalid"] != 0 or lines["quantity"] != 184945:
        raise RuntimeError(f"Line data changed: {dict(lines)}")
    if sum(row["line_count"] for row in rows) != 1589 or sum(
        row["total_imported_quantity"] for row in rows
    ) != 184945:
        raise RuntimeError("Import header totals changed")
    for table in ("pdd_execution_event", "pdd_valkimia_batch_event", "pdd_valkimia_dispatch"):
        n = await conn.fetchval(
            f"SELECT count(*) FROM stock_management.{table} WHERE valkimia_import_id=ANY($1::bigint[])",
            IDS,
        )
        if n:
            raise RuntimeError(f"External activity found in {table}: {n}")
    messages = await conn.fetch(
        """
        SELECT integration_message_id, payload_reference, interface_code, direction,
               message_type, status, attempt_count, processed_at
        FROM stock_management.pdd_integration_message
        WHERE payload_reference=ANY($1::text[])
        """ + (" FOR UPDATE" if lock else ""),
        [f"pdd_valkimia_import:{value}" for value in EXPECTED.values()],
    )
    if len(messages) != 7 or any(
        m["interface_code"] != "VALKIMIA_LEGACY"
        or m["direction"] != "OUTBOUND"
        or m["message_type"] != "VALKIMIA_IMPORT_REQUESTED"
        or m["status"] != "PENDING"
        or m["attempt_count"] != 0
        or m["processed_at"] is not None
        for m in messages
    ):
        raise RuntimeError("Outbound message state changed")
    stops = await conn.fetchval(
        """SELECT count(*) FROM stock_management.pdd_dispatch_trip_stop
           WHERE dispatch_trip_id=ANY($1::bigint[]) AND status='PLANNED'""",
        trip_ids,
    )
    all_stops = await conn.fetchval(
        """SELECT count(*) FROM stock_management.pdd_dispatch_trip_stop
           WHERE dispatch_trip_id=ANY($1::bigint[])""",
        trip_ids,
    )
    if stops != all_stops or stops != 9:
        raise RuntimeError("Trip stops changed")
    return trip_ids, plan_ids, lines["n"], stops


async def main(apply: bool) -> None:
    env = dotenv_values(Path(__file__).parent / "backend" / ".env")
    conn = await asyncpg.connect(
        host=env["PGP_TEST_HOST"], port=int(env.get("PGP_TEST_PORT") or 5432),
        database=env["PGP_TEST_DB"], user=env["PGP_TEST_USER"],
        password=env["PGP_TEST_PASSWORD"], timeout=10,
    )
    try:
        async with conn.transaction(readonly=not apply):
            trips, plans, line_count, stop_count = await preflight(conn, lock=apply)
            print(f"Preflight OK: 7 imports, {line_count} lines, {stop_count} stops, 7 plans")
            if not apply:
                return
            changed = {}
            changed["import_lines"] = await count_updated(conn, """
                UPDATE stock_management.pdd_valkimia_import_line
                   SET status_id=7, cancelled_quantity=imported_quantity,
                       last_updated_at=clock_timestamp(), row_version=row_version+1
                 WHERE valkimia_import_id=ANY($1::bigint[]) AND status_id=1
            """, IDS)
            changed["trip_lines"] = await count_updated(conn, """
                UPDATE stock_management.pdd_dispatch_trip_line
                   SET status='CANCELLED', cancelled_quantity=published_quantity,
                       updated_at=clock_timestamp(), row_version=row_version+1
                 WHERE dispatch_trip_id=ANY($1::bigint[]) AND status='PUBLISH_PENDING'
            """, trips)
            changed["stops"] = await count_updated(conn, """
                UPDATE stock_management.pdd_dispatch_trip_stop
                   SET status='CANCELLED', updated_at=clock_timestamp(), row_version=row_version+1
                 WHERE dispatch_trip_id=ANY($1::bigint[]) AND status='PLANNED'
            """, trips)
            changed["trips"] = await count_updated(conn, """
                UPDATE stock_management.pdd_dispatch_trip
                   SET status='CANCELLED', updated_at=clock_timestamp(), row_version=row_version+1
                 WHERE dispatch_trip_id=ANY($1::bigint[]) AND status='PUBLISH_PENDING'
            """, trips)
            changed["plans"] = await count_updated(conn, """
                UPDATE stock_management.pdd_dispatch_plan
                   SET status='CANCELLED', cancelled_by=$2, cancelled_at=clock_timestamp(),
                       cancellation_reason=$3, updated_at=clock_timestamp(), row_version=row_version+1
                 WHERE dispatch_plan_id=ANY($1::bigint[]) AND status='APPROVED'
            """, plans, ACTOR, REASON)
            changed["imports"] = await count_updated(conn, """
                UPDATE stock_management.pdd_valkimia_import
                   SET status='CANCELLED', detail=coalesce(detail,'{}'::jsonb) || $2::jsonb
                 WHERE valkimia_import_id=ANY($1::bigint[]) AND status='PENDING'
            """, IDS, AUDIT)
            changed["messages"] = await count_updated(conn, """
                UPDATE stock_management.pdd_integration_message
                   SET status='DEAD_LETTER', next_attempt_at=NULL,
                       processed_at=clock_timestamp(), error_detail=$2
                 WHERE payload_reference=ANY($1::text[]) AND status='PENDING' AND attempt_count=0
            """, [f"pdd_valkimia_import:{value}" for value in EXPECTED.values()], REASON)
            expected = {"import_lines": 1589, "trip_lines": 1589, "stops": 9,
                        "trips": 7, "plans": 7, "imports": 7, "messages": 7}
            if changed != expected:
                raise RuntimeError(f"Unexpected update counts: {changed}")
            remaining = await conn.fetchval("""
                SELECT count(*) FROM stock_management.pdd_valkimia_import
                WHERE origin_cd=41 AND status IN ('PENDING','ACCEPTED','PARTIAL')
            """)
            if remaining:
                raise RuntimeError(f"Active imports remain: {remaining}")
            print("Cancelled in one transaction:", changed)
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
