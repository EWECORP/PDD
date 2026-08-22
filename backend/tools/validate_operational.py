from __future__ import annotations

import json
import os

from sqlalchemy import text

from pdd_backend.config import OperationalSettings, Settings, load_environment
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.operational_contract import OPERATIONAL_TABLES


SOURCE_COLUMNS = {
    ("src", "base_productos_vigentes"): {
        "c_sucu_empr", "c_articulo", "cod_cd", "abastecimiento",
        "habilitado", "active_for_sale", "active_on_mix",
        "active_for_purchase", "fecha_extraccion",
    },
    ("src", "v_base_articulos_logistica_actual"): {
        "articulo_logistica_id", "c_articulo", "c_proveedor",
        "c_configuracion_logistica", "c_unidad_base", "m_vende_por_peso",
        "c_gtin_unidad", "c_tipo_bulto", "c_gtin_bulto",
        "q_unidades_por_bulto", "q_peso_neto_unitario_kg",
        "q_peso_bruto_unitario_kg", "q_peso_bruto_bulto_kg",
        "q_largo_bulto_cm", "q_ancho_bulto_cm", "q_alto_bulto_cm",
        "q_volumen_bulto_m3", "q_volumen_unitario_m3", "c_metodo_volumen",
        "q_bultos_por_capa", "q_capas_por_pallet", "q_bultos_por_pallet",
        "q_unidades_por_pallet", "c_tipo_pallet", "q_largo_pallet_cm",
        "q_ancho_pallet_cm", "q_alto_pallet_cargado_cm",
        "q_peso_bruto_pallet_kg", "m_apilable", "q_max_niveles_apilado",
        "m_fragil", "m_peligroso", "c_zona_temperatura",
        "q_temperatura_min_c", "q_temperatura_max_c", "c_orientacion",
        "c_calidad_embalaje", "c_calidad_peso", "c_calidad_volumen",
        "c_calidad_pallet", "f_vigencia_desde", "fuente_origen",
        "referencia_origen", "fecha_extraccion", "input_checksum",
        "atributos_adicionales",
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

TARGET_COLUMNS = {
    ("stock_management", "pdd_item_logistics_snapshot"): {
        "source_logistics_id", "supplier_code", "logistics_configuration_code",
        "source_valid_from", "sells_by_weight", "package_uom", "unit_gtin",
        "package_gtin", "source_reference", "unit_net_weight_kg",
        "unit_gross_weight_kg", "package_gross_weight_kg", "weight_basis",
        "package_length_cm", "package_width_cm", "package_height_cm",
        "package_volume_m3", "volume_method", "packages_per_layer",
        "layers_per_pallet", "units_per_pallet", "pallet_type",
        "pallet_length_cm", "pallet_width_cm", "loaded_pallet_height_cm",
        "pallet_gross_weight_kg", "stackable", "max_stack_levels", "fragile",
        "hazardous", "temperature_zone", "temperature_min_c",
        "temperature_max_c", "orientation_code", "packaging_quality_status",
        "weight_quality_status", "volume_quality_status",
        "pallet_quality_status", "quality_issue_codes", "verified_at",
        "verified_by", "attributes",
    },
}

REQUIRED_OPERATIONAL_ENV = (
    "PDD_OPERATIONAL_PG_HOST",
    "PDD_OPERATIONAL_PG_DB",
    "PDD_OPERATIONAL_PG_USER",
    "PDD_OPERATIONAL_PG_PASSWORD",
    "PDD_OPERATIONAL_TARGET_ENV",
)


def main() -> None:
    loaded_environment = load_environment()
    missing_environment = [
        name for name in REQUIRED_OPERATIONAL_ENV if not os.getenv(name)
    ]
    if missing_environment:
        print(
            json.dumps(
                {
                    "environment_file": (
                        str(loaded_environment) if loaded_environment else None
                    ),
                    "missing_environment_variables": missing_environment,
                    "publisher_contract": "ENVIRONMENT_INCOMPLETE",
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2)
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
                            'sucursales_excluidas', 'mv_base_oc_pendientes',
                            'v_base_articulos_logistica_actual'
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
            target_columns = {
                (row[0], row[1], row[2])
                for row in target.execute(
                    text(
                        """
                        SELECT table_schema, table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'stock_management'
                          AND table_name = 'pdd_item_logistics_snapshot'
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
        missing_target_columns = sorted(
            f"{schema}.{table}.{column}"
            for (schema, table), columns in TARGET_COLUMNS.items()
            for column in columns
            if (schema, table, column) not in target_columns
        )
        result = {
            "source_database": source_database,
            "target_environment": target_settings.target_environment,
            "target_database": target_database,
            "publisher_contract": (
                "OK" if not missing and not missing_target_columns else "INCOMPLETE"
            ),
            "missing_tables": missing,
            "missing_source_columns": missing_source_columns,
            "missing_target_columns": missing_target_columns,
            "legacy_unprefixed_tables": legacy,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if missing or missing_source_columns or missing_target_columns:
            raise SystemExit(2)
    finally:
        target_engine.dispose()
        source_engine.dispose()


if __name__ == "__main__":
    main()
