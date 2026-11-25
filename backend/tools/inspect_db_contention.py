"""Diagnostico de sesiones PDD y bloqueos; no modifica ni termina sesiones."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from sqlalchemy import text

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine


ACTIVITY_SQL = text(
    """
    SELECT pid, application_name, state, wait_event_type, wait_event,
           pg_blocking_pids(pid) AS blocking_pids,
           EXTRACT(EPOCH FROM clock_timestamp() - query_start)::integer
               AS query_age_seconds,
           EXTRACT(EPOCH FROM clock_timestamp() - state_change)::integer
               AS state_age_seconds
    FROM pg_stat_activity
    WHERE datname = current_database() AND pid <> pg_backend_pid()
      AND backend_type = 'client backend'
    """
)


def classify_activity(
    rows: list[dict], *, active_seconds: int, lock_seconds: int,
    idle_transaction_seconds: int,
) -> tuple[list[dict], list[dict]]:
    pdd_pids = {
        row["pid"] for row in rows
        if "pdd" in (row["application_name"] or "").lower()
    }
    visible = []
    anomalies = []
    for row in rows:
        blockers = row["blocking_pids"] or []
        is_pdd = row["pid"] in pdd_pids
        blocked_by_pdd = bool(pdd_pids.intersection(blockers))
        if not (is_pdd or blocked_by_pdd):
            continue
        safe = {
            "pid": row["pid"],
            "application_name": row["application_name"],
            "state": row["state"],
            "wait_event_type": row["wait_event_type"],
            "wait_event": row["wait_event"],
            "blocking_pids": blockers,
            "query_age_seconds": row["query_age_seconds"],
            "state_age_seconds": row["state_age_seconds"],
        }
        visible.append(safe)
        reasons = []
        if is_pdd and row["state"] == "active" and (
            row["query_age_seconds"] or 0
        ) >= active_seconds:
            reasons.append("LONG_PDD_STATEMENT")
        if row["wait_event_type"] == "Lock" and (
            row["query_age_seconds"] or 0
        ) >= lock_seconds:
            reasons.append("LOCK_WAIT")
        if is_pdd and (row["state"] or "").startswith("idle in transaction") and (
            row["state_age_seconds"] or 0
        ) >= idle_transaction_seconds:
            reasons.append("IDLE_PDD_TRANSACTION")
        if blocked_by_pdd:
            reasons.append("OTHER_PROCESS_BLOCKED_BY_PDD")
        if reasons:
            anomalies.append({**safe, "reasons": reasons})
    return visible, anomalies


def inspect_database(engine, *, active_seconds, lock_seconds, idle_transaction_seconds):
    with engine.connect() as connection:
        database = connection.execute(text("SELECT current_database()")).scalar_one()
        full_visibility = connection.execute(
            text("SELECT pg_has_role(current_user, 'pg_read_all_stats', 'member')")
        ).scalar_one()
        rows = [dict(row) for row in connection.execute(ACTIVITY_SQL).mappings()]
    visible, anomalies = classify_activity(
        rows, active_seconds=active_seconds, lock_seconds=lock_seconds,
        idle_transaction_seconds=idle_transaction_seconds,
    )
    return {
        "database": database,
        "full_stats_visibility": full_visibility,
        "pdd_and_blocked_sessions": visible,
        "anomalies": anomalies,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-seconds", type=int, default=1_200)
    parser.add_argument("--lock-seconds", type=int, default=30)
    parser.add_argument("--idle-transaction-seconds", type=int, default=120)
    args = parser.parse_args()
    if min(args.active_seconds, args.lock_seconds, args.idle_transaction_seconds) <= 0:
        parser.error("Los umbrales deben ser positivos")
    source = Settings.from_env()
    target = OperationalSettings.from_env()
    if source.runtime_environment != target.target_environment:
        raise RuntimeError("Ambiente runtime y destino operativo inconsistentes")
    output = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": target.target_environment,
        "databases": [],
    }
    engines = [build_engine(source), build_operational_engine(target)]
    try:
        for engine in engines:
            output["databases"].append(
                inspect_database(
                    engine, active_seconds=args.active_seconds,
                    lock_seconds=args.lock_seconds,
                    idle_transaction_seconds=args.idle_transaction_seconds,
                )
            )
    finally:
        for engine in engines:
            engine.dispose()
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2))
    return 2 if any(db["anomalies"] for db in output["databases"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
