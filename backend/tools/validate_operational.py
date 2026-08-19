from __future__ import annotations

import json

from sqlalchemy import text

from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.operational_contract import OPERATIONAL_TABLES


SOURCE_COLUMNS = {
    ("src", "base_productos_vigentes"): {
        "c_sucu_empr", "c_articulo", "m_vende_por_peso",
        "q_factor_compra", "full_capacity_pallet", "q_peso_unit_art",
        "fecha_extraccion",
    },
    ("src", "base_stock_sucursal"): {
        "codigo_articulo", "codigo_sucursal", "fecha_stock", "stock",
        "pedido_pendiente", "transito_pendiente", "transfer_pendiente",
        "pedido_pendiente_fecha", "dias_preparacion", "q_dias_stock",
        "q_dias_sobre_stock", "fecha_extraccion",
    },
    ("src", "mv_base_oc_pendientes"): {
        "c_articulo", "c_sucu_destino", "pendientes", "q_peso_unit_art",
        "m_vende_por_peso", "q_factor_compra", "u_prefijo_oc",
        "u_sufijo_oc", "f_emision", "c_proveedor", "fuente_origen",
        "fecha_extraccion", "cdc_lsn", "estado_sincronizacion",
    },
    ("src", "sucursales_excluidas"): {"c_sucu_empr"},
    ("datamart", "dm_pdd_scope_article"): {
        "scope_version_uuid", "codigo_articulo",
    },
    ("datamart", "dm_pdd_scope_pair"): {
        "scope_version_uuid", "codigo_articulo", "destination_branch",
    },
}


def main() -> None:
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        with source_engine.connect() as source:
            source_database = source.execute(text("SELECT current_database()" )).scalar_one()
            source_columns = {
                (row[0], row[1], row[2])
                for row in source.execute(
                    text(
                        """
                        SELECT n.nspname, c.relname, a.attname
                        FROM pg_catalog.pg_attribute AS a
                        JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
                        JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                        WHERE a.attnum > 0 AND NOT a.attisdropped
                          AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
                          AND ((n.nspname = 'src' AND c.relname IN (
                            'base_productos_vigentes', 'base_stock_sucursal',
                            'sucursales_excluidas', 'mv_base_oc_pendientes'
                        )) OR (n.nspname = 'datamart' AND c.relname IN (
                            'dm_pdd_scope_article', 'dm_pdd_scope_pair'
                        )))
                        """
                    )
                )
            }
        with target_engine.connect() as target:
            target_database = target.execute(text("SELECT current_database()" )).scalar_one()
            existing = {
                row[0]
                for row in target.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = 'stock_management'
                        """
                    )
                )
            }
        missing = sorted(set(OPERATIONAL_TABLES) - existing)
        legacy = sorted(
            table for table in existing
            if table in {name.removeprefix("pdd_") for name in OPERATIONAL_TABLES}
        )
        missing_source_columns = sorted(
            f"{schema}.{table}.{column}"
            for (schema, table), columns in SOURCE_COLUMNS.items()
            for column in columns
            if (schema, table, column) not in source_columns
        )
        result = {
            "source_database": source_database,
            "target_environment": target_settings.target_environment,
            "target_database": target_database,
            "publisher_contract": "OK" if not missing else "INCOMPLETE",
            "missing_tables": missing,
            "missing_source_columns": missing_source_columns,
            "legacy_unprefixed_tables": legacy,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if missing or missing_source_columns:
            raise SystemExit(2)
    finally:
        target_engine.dispose()
        source_engine.dispose()


if __name__ == "__main__":
    main()
