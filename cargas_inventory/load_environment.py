"""Carga versionada de parametros Inventory para TEST o PROD.

El proceso separa captura, preview, aplicacion y verificacion. Las aplicaciones
son aditivas e idempotentes: crean filas faltantes, pero nunca pisan parametros
ya administrados en Connexa. En PROD exige confirmacion explicita y el SHA256
del preview revisado.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import dotenv_values


CONTRACT_VERSION = "inventory-master-bootstrap-v2"
REPLENISHMENT_METHODS = {
    0: "Entrega desde CD",
    1: "Entrega Desde el Proveedor",
    2: "Cross Doking",
    3: "Entrega desde QX",
}
EXPECTED_DATABASES = {
    "TEST": "connexa_platform_test",
    "PROD": "connexa_platform_ms",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _environment() -> dict[str, str]:
    path = Path(
        os.environ.get(
            "PDD_ENV_PATH",
            Path(__file__).resolve().parents[1] / "backend" / ".env",
        )
    )
    values = {
        key: value
        for key, value in dotenv_values(path, interpolate=False).items()
        if value is not None
    }
    values.update(os.environ)
    return values


def _connect(values: dict[str, str], source: bool, readonly: bool):
    prefix = "PG_" if source else "PDD_OPERATIONAL_PG_"
    required = tuple(prefix + key for key in ("HOST", "PORT", "DB", "USER", "PASSWORD"))
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise RuntimeError("Missing database settings: " + ", ".join(missing))
    connection = psycopg2.connect(
        host=values[prefix + "HOST"],
        port=values[prefix + "PORT"],
        dbname=values[prefix + "DB"],
        user=values[prefix + "USER"],
        password=values[prefix + "PASSWORD"],
        connect_timeout=15,
        options="-c statement_timeout=600000 -c lock_timeout=10000",
    )
    connection.set_session(readonly=readonly, isolation_level="REPEATABLE READ")
    return connection


def _validate_target(connection, environment: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        database = cursor.fetchone()[0]
    expected = EXPECTED_DATABASES[environment]
    if database != expected:
        raise RuntimeError(
            f"Unexpected target database {database!r}; expected {expected!r}"
        )
    return database


def _production_guard(
    values: dict[str, str], environment: str, confirmation: str | None
) -> None:
    configured = values.get("PDD_OPERATIONAL_TARGET_ENV", "").strip().upper()
    if configured and configured != environment:
        raise RuntimeError(
            f"Configured target environment is {configured}, requested {environment}"
        )
    if environment != "PROD":
        return
    if values.get("PDD_OPERATIONAL_ALLOW_PRODUCTION", "").strip().lower() != "true":
        raise RuntimeError("PDD_OPERATIONAL_ALLOW_PRODUCTION=true is required")
    if confirmation != EXPECTED_DATABASES["PROD"]:
        raise RuntimeError(
            "PROD requires --confirm-production connexa_platform_ms"
        )


def extract(folder: Path, values: dict[str, str]) -> None:
    if folder.exists():
        raise RuntimeError("Capture directory must be new")
    folder.mkdir(parents=True)
    connection = _connect(values, source=True, readonly=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != "diarco_data":
                raise RuntimeError("Source database must be diarco_data")
            cursor.execute("SELECT max(fecha_stock) FROM src.base_stock_sucursal")
            closing = cursor.fetchone()[0]
            if closing is None:
                raise RuntimeError("No closing stock")
            cursor.execute(
                """SELECT count(*)-count(distinct(c_articulo,c_sucu_empr))
                   FROM src.base_productos_vigentes"""
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Duplicate product/site in source")
            cursor.execute(
                """SELECT count(*)-count(distinct(codigo_articulo,codigo_sucursal))
                   FROM src.base_stock_sucursal WHERE fecha_stock=%s""",
                (closing,),
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Duplicate product/site at closing")
            cursor.execute(
                """SELECT count(*) FROM src.t050_articulos
                   WHERE c_articulo IS NULL
                      OR c_articulo::text IN ('NaN','Infinity','-Infinity')
                      OR c_articulo<>trunc(c_articulo)
                      OR c_clasificacion_compra IS NULL
                      OR c_clasificacion_compra::text IN ('NaN','Infinity','-Infinity')
                      OR c_clasificacion_compra<>trunc(c_clasificacion_compra)"""
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Invalid article/classification codes in T050")
            cursor.execute(
                """SELECT count(*) FROM src.base_productos_vigentes
                   WHERE abastecimiento IS NULL OR abastecimiento NOT IN (0,1,2,3)"""
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Invalid replenishment method codes")
            cursor.execute(
                """SELECT count(*)-count(distinct(c_proveedor,c_sucursal))
                   FROM src.t055_lead_time_b2_sucursales"""
            )
            if cursor.fetchone()[0]:
                raise RuntimeError("Duplicate supplier/site lead time")
            queries = {
                "replenishment": cursor.mogrify(
                    """SELECT p.c_articulo::text product_code,
                              p.c_sucu_empr::text site_code,
                              p.pedido_min::numeric minimum_order_quantity,
                              s.q_dias_stock target_stock_days,
                              s.q_dias_sobre_stock overstock_days,
                              s.dias_preparacion preparation_days,
                              CASE p.abastecimiento
                                  WHEN 0 THEN 'Entrega desde CD'
                                  WHEN 1 THEN 'Entrega Desde el Proveedor'
                                  WHEN 2 THEN 'Cross Doking'
                                  WHEN 3 THEN 'Entrega desde QX'
                              END replenishment_method,
                              CASE WHEN p.abastecimiento=0
                                   THEN coalesce(t.dias_entrega,0)::numeric
                                   ELSE NULL::numeric END lead_time_days,
                              (s.codigo_articulo IS NULL) missing_stock,
                              (s.dias_preparacion IS NULL) missing_preparation
                       FROM src.base_productos_vigentes p
                       LEFT JOIN src.base_stock_sucursal s
                         ON s.codigo_articulo=p.c_articulo
                        AND s.codigo_sucursal=p.c_sucu_empr
                        AND s.fecha_stock=%s
                       LEFT JOIN src.t055_lead_time_b2_sucursales t
                         ON t.c_proveedor=0 AND t.c_sucursal=p.c_sucu_empr
                       ORDER BY p.c_articulo,p.c_sucu_empr""",
                    (closing,),
                ).decode(),
                "classification": """SELECT DISTINCT
                       c_articulo::bigint::text product_code,
                       c_clasificacion_compra::bigint::text classification_code
                       FROM src.t050_articulos ORDER BY 1,2""",
            }
            for name, query in queries.items():
                print("EXTRACT " + name, flush=True)
                with (folder / f"{name}.csv").open(
                    "w", encoding="utf-8", newline=""
                ) as output:
                    cursor.copy_expert(
                        "COPY (" + query + ") TO STDOUT WITH (FORMAT CSV, HEADER TRUE)",
                        output,
                    )
        manifest = {
            "contract_version": CONTRACT_VERSION,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "source_database": "diarco_data",
            "source_read_only": True,
            "stock_closing": str(closing),
            "sources": [
                "src.base_productos_vigentes",
                "src.base_stock_sucursal",
                "src.t050_articulos",
                "src.t055_lead_time_b2_sucursales",
            ],
            "replenishment_method_mapping": REPLENISHMENT_METHODS,
            "lead_time_rule": "CD_METHOD_SUPPLIER_0_BY_SITE_MISSING_ZERO",
            "sha256": {
                name: digest(folder / f"{name}.csv") for name in queries
            },
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
    finally:
        connection.rollback()
        connection.close()


def _load_staging(cursor, folder: Path) -> str:
    cursor.execute(
        """CREATE TEMP TABLE load_replenishment(
               product_code text,site_code text,minimum_order_quantity numeric,
               target_stock_days numeric,overstock_days numeric,
               preparation_days numeric,replenishment_method text,
               lead_time_days numeric,missing_stock boolean,
               missing_preparation boolean) ON COMMIT DROP;
           CREATE TEMP TABLE load_classification(
               product_code text,classification_code text) ON COMMIT DROP;"""
    )
    for name in ("replenishment", "classification"):
        with (folder / f"{name}.csv").open(
            encoding="utf-8", newline=""
        ) as source:
            cursor.copy_expert(
                f"COPY load_{name} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)",
                source,
            )
    cursor.execute("ANALYZE load_replenishment; ANALYZE load_classification")
    cursor.execute(
        "SELECT product_code FROM load_classification GROUP BY 1 HAVING count(*)>1 LIMIT 1"
    )
    if cursor.fetchone():
        raise RuntimeError("Multiple purchase classes per product in T050")
    cursor.execute(
        """SELECT t.id,t.value
           FROM inventory.inv_product_classification_type t
           JOIN inventory.inv_product_classification_value v
             ON v.classification_type_id=t.id
           GROUP BY t.id,t.value
           HAVING count(*)=7
              AND count(*) FILTER(
                  WHERE v.active AND v.code IN ('1','2','3','4','5','6','100')
              )=7"""
    )
    candidates = cursor.fetchall()
    if len(candidates) != 1:
        raise RuntimeError("Cannot uniquely resolve purchase classification catalog")
    type_id = str(candidates[0][0])
    cursor.execute(
        """CREATE TEMP TABLE load_resolved ON COMMIT DROP AS
           SELECT x.*,ps.id AS product_site_id,p.id AS product_id,
                  CASE WHEN x.missing_stock THEN 0
                       ELSE coalesce(x.target_stock_days,7) END AS resolved_target,
                  CASE WHEN x.missing_stock THEN 0
                       ELSE coalesce(x.overstock_days,0) END AS resolved_overstock,
                  coalesce(x.preparation_days,0) AS resolved_preparation
           FROM load_replenishment x
           LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
           LEFT JOIN inventory.inv_site s ON s.code=x.site_code
           LEFT JOIN inventory.inv_product_site ps
             ON ps.product_id=p.id AND ps.site_id=s.id"""
    )
    cursor.execute(
        """CREATE TEMP TABLE load_ready ON COMMIT DROP AS
           SELECT * FROM load_resolved
           WHERE product_site_id IS NOT NULL
             AND resolved_target IS NOT NULL
             AND resolved_overstock IS NOT NULL"""
    )
    cursor.execute(
        """SELECT count(*) FROM load_ready WHERE
           minimum_order_quantity IS NULL
           OR NOT (minimum_order_quantity>=0 AND minimum_order_quantity<'Infinity')
           OR minimum_order_quantity<>round(minimum_order_quantity,4)
           OR minimum_order_quantity>=100000000000000
           OR NOT (resolved_target>=0 AND resolved_target<1000000)
           OR NOT (resolved_overstock>=0 AND resolved_overstock<1000000)
           OR NOT (resolved_preparation>=0 AND resolved_preparation<1000000)
           OR replenishment_method IS NULL
           OR replenishment_method NOT IN (
               'Entrega desde CD','Entrega Desde el Proveedor',
               'Cross Doking','Entrega desde QX')
           OR (replenishment_method='Entrega desde CD' AND
               (lead_time_days IS NULL OR lead_time_days<0 OR
                lead_time_days>=1000000 OR
                lead_time_days<>round(lead_time_days,4)))
           OR (replenishment_method<>'Entrega desde CD' AND
               lead_time_days IS NOT NULL)"""
    )
    if cursor.fetchone()[0]:
        raise RuntimeError("Invalid numeric values or precision")
    cursor.execute(
        """CREATE TEMP TABLE load_classes ON COMMIT DROP AS
           SELECT x.*,p.id AS product_id,v.id AS value_id
           FROM load_classification x
           LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
           LEFT JOIN inventory.inv_product_classification_value v
             ON v.classification_type_id=%s::uuid
            AND v.code=x.classification_code AND v.active""",
        (type_id,),
    )
    cursor.execute("SELECT count(*) FROM load_classes WHERE value_id IS NULL")
    if cursor.fetchone()[0]:
        raise RuntimeError("T050 contains codes outside purchase catalog")
    cursor.execute(
        """CREATE TEMP TABLE load_logistics ON COMMIT DROP AS
           SELECT v.product_id,min(v.id::text)::uuid AS logistic_variable_id
           FROM inventory.inv_logistic_variable v
           WHERE v.active AND v.principal
             AND v.product_id IN (
                 SELECT product_id FROM load_ready
                 UNION SELECT product_id FROM load_classes WHERE product_id IS NOT NULL
             )
           GROUP BY v.product_id HAVING count(*)=1
             AND bool_and((v.purchase_factor>0
                 AND v.purchase_factor<'Infinity'::float8
                 AND v.uom_id IS NOT NULL AND btrim(v.uom_id)<>''
                 AND (v.uom_id='unidad' OR
                     (v.weight_in_gr>0 AND v.weight_in_gr<'Infinity'::float8)))
                 IS TRUE)"""
    )
    return type_id


def _metrics(cursor) -> dict[str, int]:
    queries = {
        "replenishment_source": "SELECT count(*) FROM load_resolved",
        "unmapped_pairs": "SELECT count(*) FROM load_resolved WHERE product_site_id IS NULL",
        "replenishment_ready": "SELECT count(*) FROM load_ready",
        "target_null_default_7": "SELECT count(*) FROM load_ready WHERE NOT missing_stock AND target_stock_days IS NULL",
        "overstock_null_default_0": "SELECT count(*) FROM load_ready WHERE NOT missing_stock AND overstock_days IS NULL",
        "missing_stock_zero": "SELECT count(*) FROM load_ready WHERE missing_stock",
        "null_preparation_zero": "SELECT count(*) FROM load_ready WHERE missing_preparation",
        "existing_replenishment": """SELECT count(*) FROM load_ready x JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=x.product_site_id""",
        "missing_replenishment": """SELECT count(*) FROM load_ready x LEFT JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=x.product_site_id WHERE r.id IS NULL""",
        "inactive_replenishment": """SELECT count(*) FROM load_ready x JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=x.product_site_id WHERE r.active IS NOT TRUE""",
        "conflicting_replenishment": """SELECT count(*) FROM load_ready x JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=x.product_site_id WHERE r.target_stock_days IS DISTINCT FROM x.resolved_target OR r.overstock_days IS DISTINCT FROM x.resolved_overstock OR r.minimum_order_quantity IS DISTINCT FROM x.minimum_order_quantity OR r.preparation_days IS DISTINCT FROM x.resolved_preparation OR r.replenishment_method IS DISTINCT FROM x.replenishment_method OR r.lead_time_days IS DISTINCT FROM x.lead_time_days""",
        "classification_source": "SELECT count(*) FROM load_classes",
        "classification_missing_product": "SELECT count(*) FROM load_classes WHERE product_id IS NULL",
        "classification_ready": "SELECT count(*) FROM load_classes WHERE product_id IS NOT NULL",
        "missing_classification": """SELECT count(*) FROM load_classes x WHERE x.product_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM inventory.inv_product_classification c WHERE c.product_id=x.product_id AND c.classification_type_id=(SELECT classification_type_id FROM inventory.inv_product_classification_value WHERE id=x.value_id) AND c.active)""",
        "conflicting_classification": """SELECT count(*) FROM load_classes x JOIN inventory.inv_product_classification c ON c.product_id=x.product_id AND c.classification_type_id=(SELECT classification_type_id FROM inventory.inv_product_classification_value WHERE id=x.value_id) AND c.active WHERE c.classification_value_id IS DISTINCT FROM x.value_id""",
        "logistic_unique_usable": "SELECT count(*) FROM load_logistics",
        "missing_logistics": """SELECT count(*) FROM load_logistics x LEFT JOIN inventory.inv_product_planning_logistics l ON l.product_id=x.product_id WHERE l.product_id IS NULL""",
        "conflicting_logistics": """SELECT count(*) FROM load_logistics x JOIN inventory.inv_product_planning_logistics l ON l.product_id=x.product_id WHERE l.logistic_variable_id IS DISTINCT FROM x.logistic_variable_id""",
    }
    result: dict[str, int] = {}
    for name, query in queries.items():
        cursor.execute(query)
        result[name] = cursor.fetchone()[0]
    return result


def run(
    folder: Path,
    values: dict[str, str],
    environment: str,
    apply: bool,
    verify: bool,
    confirmation: str | None,
    preview_sha256: str | None,
) -> None:
    _production_guard(values, environment, confirmation)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise RuntimeError("Capture contract is not supported")
    for name, checksum in manifest["sha256"].items():
        if digest(folder / f"{name}.csv") != checksum:
            raise RuntimeError(f"Capture checksum mismatch: {name}")
    preview_path = folder / f"preview-{environment.lower()}.json"
    if apply and environment == "PROD":
        if not preview_path.exists():
            raise RuntimeError("PROD apply requires an existing preview")
        reviewed_preview = json.loads(preview_path.read_text(encoding="utf-8"))
        if reviewed_preview.get("status") != "PREVIEW_OK":
            raise RuntimeError("PROD apply requires a PREVIEW_OK result")
        if reviewed_preview.get("environment") != "PROD":
            raise RuntimeError("Reviewed preview does not belong to PROD")
        if reviewed_preview.get("manifest", {}).get("sha256") != manifest["sha256"]:
            raise RuntimeError("Reviewed preview belongs to another capture")
        actual_preview_sha = digest(preview_path)
        if preview_sha256 != actual_preview_sha:
            raise RuntimeError(
                "PROD apply requires --preview-sha256 " + actual_preview_sha
            )

    # PostgreSQL no permite CREATE TEMP/COPY FROM dentro de una transaccion
    # READ ONLY. Preview y verify necesitan staging temporal, pero nunca
    # ejecutan DML persistente y finalizan explicitamente con ROLLBACK.
    connection = _connect(values, source=False, readonly=False)
    committed = False
    output = folder / (
        f"result-{environment.lower()}.json"
        if apply
        else f"verification-{environment.lower()}.json"
        if verify
        else preview_path.name
    )
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "mode": "APPLY" if apply else "VERIFY" if verify else "PREVIEW",
        "contract_version": CONTRACT_VERSION,
        "manifest": manifest,
        "rules": {
            "existing_rows": "PRESERVE_AND_REPORT_CONFLICTS",
            "new_replenishment_active": True,
            "missing_stock_days": 0,
            "existing_null_target_days": 7,
            "existing_null_overstock_days": 0,
            "replenishment_method": "SGM_ABASTECIMIENTO_0_TO_3",
            "cd_lead_time": "SUPPLIER_0_BY_SITE_MISSING_ZERO",
        },
        "status": "RUNNING",
    }
    try:
        report["database"] = _validate_target(connection, environment)
        with connection.cursor() as cursor:
            if apply:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext('inventory_master_bootstrap_v2'))"
                )
                cursor.execute(
                    """LOCK TABLE inventory.inv_product_site_replenishment,
                       inventory.inv_product_classification,
                       inventory.inv_product_planning_logistics
                       IN SHARE ROW EXCLUSIVE MODE"""
                )
                cursor.execute(
                    "SELECT set_config('app.actor',%s,true)",
                    (f"ETL:inventory_master_bootstrap:{environment}:{folder.name}",),
                )
            type_id = _load_staging(cursor, folder)
            report["purchase_classification_type_uuid"] = type_id
            report["counts"] = _metrics(cursor)
            conflicts = {
                name: report["counts"][name]
                for name in (
                    "conflicting_replenishment",
                    "conflicting_classification",
                    "conflicting_logistics",
                )
                if report["counts"][name]
            }
            if conflicts and (apply or verify):
                raise RuntimeError(
                    "Existing managed values conflict with capture; bootstrap never "
                    f"overwrites them: {conflicts}"
                )
            if apply:
                statements = {
                    "replenishment_inserted": """INSERT INTO inventory.inv_product_site_replenishment(product_site_id,target_stock_days,overstock_days,minimum_order_quantity,preparation_days,replenishment_method,lead_time_days,active) SELECT product_site_id,resolved_target,resolved_overstock,minimum_order_quantity,resolved_preparation,replenishment_method,lead_time_days,true FROM load_ready x WHERE NOT EXISTS (SELECT 1 FROM inventory.inv_product_site_replenishment r WHERE r.product_site_id=x.product_site_id) ON CONFLICT(product_site_id) DO NOTHING""",
                    "classification_inserted": """INSERT INTO inventory.inv_product_classification(product_id,classification_type_id,classification_value_id,valid_from,active) SELECT x.product_id,%s::uuid,x.value_id,CURRENT_DATE,true FROM load_classes x WHERE x.product_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM inventory.inv_product_classification c WHERE c.product_id=x.product_id AND c.classification_type_id=%s::uuid AND c.active)""",
                    "logistics_inserted": """INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id) SELECT product_id,logistic_variable_id FROM load_logistics ON CONFLICT(product_id) DO NOTHING""",
                }
                for name, statement in statements.items():
                    if name == "classification_inserted":
                        cursor.execute(statement, (type_id, type_id))
                    else:
                        cursor.execute(statement)
                    report["counts"][name] = cursor.rowcount
                cursor.execute(
                    """SELECT count(*) FROM load_ready x
                       LEFT JOIN inventory.inv_product_site_replenishment r
                         ON r.product_site_id=x.product_site_id
                       WHERE r.id IS NULL OR r.active IS NOT TRUE"""
                )
                if cursor.fetchone()[0]:
                    raise RuntimeError("Missing or inactive replenishment after apply")
                report["counts"] = {
                    **report["counts"],
                    **_metrics(cursor),
                }
            if apply or verify:
                incomplete = {
                    name: report["counts"][name]
                    for name in (
                        "missing_replenishment",
                        "inactive_replenishment",
                        "missing_classification",
                        "missing_logistics",
                    )
                    if report["counts"][name]
                }
                if incomplete:
                    raise RuntimeError(f"Inventory verification incomplete: {incomplete}")
            report["status"] = (
                "VALIDATED_PENDING_COMMIT"
                if apply
                else "VERIFIED"
                if verify
                else "PREVIEW_REVIEW_REQUIRED"
                if conflicts
                else "PREVIEW_OK"
            )
            output.write_text(
                json.dumps(report, indent=2, default=str), encoding="utf-8"
            )
        if apply:
            connection.commit()
            committed = True
            report["status"] = "COMMITTED"
        else:
            connection.rollback()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        output.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        print(json.dumps(report, indent=2, default=str))
        if not apply and not verify:
            print("PREVIEW_SHA256=" + digest(output))
    except Exception:
        if not committed:
            connection.rollback()
        report["status"] = (
            "ERROR_AFTER_COMMIT" if committed else "FAILED_OR_COMMIT_UNCERTAIN"
        )
        output.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        raise
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--environment", choices=("TEST", "PROD"), required=True)
    parser.add_argument("--extract", action="store_true")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--confirm-production")
    parser.add_argument("--preview-sha256")
    args = parser.parse_args()
    values = _environment()
    if args.extract:
        extract(args.directory, values)
        print("CAPTURE_READY=" + str(args.directory))
        return
    run(
        args.directory,
        values,
        args.environment,
        args.apply,
        args.verify,
        args.confirm_production,
        args.preview_sha256,
    )


if __name__ == "__main__":
    main()
