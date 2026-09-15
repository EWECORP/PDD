"""Captura de TEST de solo lectura; conserva la evidencia histórica del 11/09.

No ejecutar los validadores de migraciones: esta auditoría no admite DDL/DML,
ni siquiera con rollback. No consulta filas de tablas externas.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from relevar_base import config, queries
from consultas_auditoria_inventory import QUALITY_QUERIES


def main():
    result = {"captured_at": datetime.now(timezone.utc).isoformat()}
    conn = psycopg2.connect(
        **{k: config["PGP_TEST_" + v] for k, v in
           [("host", "HOST"), ("port", "PORT"), ("dbname", "DB"),
            ("user", "USER"), ("password", "PASSWORD")]},
        connect_timeout=15,
        options="-c default_transaction_read_only=on -c statement_timeout=45000",
    )
    try:
        conn.set_session(readonly=True, isolation_level="REPEATABLE READ")
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("select current_database() as database, current_setting('server_version') as version, current_setting('transaction_read_only') as read_only, current_setting('transaction_isolation') as isolation")
            result["database"] = [dict(r) for r in cur.fetchall()]
            if result["database"][0]["database"] != "connexa_platform_test":
                raise RuntimeError("La conexión no corresponde a connexa_platform_test")
            for key in ("tables", "columns", "constraints", "indexes", "views", "triggers", "foreign_tables"):
                cur.execute(queries[key])
                result[key] = [dict(r) for r in cur.fetchall()]
            cur.execute("""select n.nspname as schema,p.proname as name,
                pg_get_function_identity_arguments(p.oid) as arguments,
                p.prokind as kind
                from pg_proc p join pg_namespace n on n.oid=p.pronamespace
                where n.nspname in ('inventory','supply_planning','stock_management')
                and p.prokind in ('f','p') order by 1,2,3""")
            result["routines"] = [dict(r) for r in cur.fetchall()]
            result["counts"] = []
            for table in result["tables"]:
                schema, name = table["schema"], table["name"]
                if table["kind"] not in ("r", "p"):
                    continue
                if schema not in ("inventory", "supply_planning"):
                    continue
                if not (schema == "inventory" and name in ("inv_product", "inv_site", "inv_category", "inv_product_site", "inv_product_site_assortment", "inv_product_supplier", "inv_supplier", "inv_logistic_variable", "inv_barcode", "inv_set_of_site", "inv_set_of_site_line")) and not any(term in name for term in ("policy", "replenishment", "classification", "cluster", "supply_site")):
                    continue
                cur.execute(sql.SQL("select count(*) as rows from {}.{}").format(sql.Identifier(schema), sql.Identifier(name)))
                result["counts"].append({"object": schema + "." + name, **dict(cur.fetchone())})
            result["quality"] = {}
            for key, query in QUALITY_QUERIES.items():
                cur.execute(query)
                result["quality"][key] = [dict(r) for r in cur.fetchall()]
        dest = Path(__file__).with_name("catalogo_test_inventory_20260914.json")
        dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(json.dumps({"database": result["database"], "counts": result["counts"], "catalog_sizes": {k: len(v) for k, v in result.items() if isinstance(v, list)}}, ensure_ascii=False))
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except psycopg2.Error as exc:
        message = str(exc)
        for suffix in ("PASSWORD", "HOST", "USER", "DB"):
            value = config.get("PGP_TEST_" + suffix)
            if value:
                message = message.replace(value, "<" + suffix + ">")
        raise SystemExit(message)
