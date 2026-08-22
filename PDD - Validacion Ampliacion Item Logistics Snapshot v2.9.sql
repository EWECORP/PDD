-- PDD - Validacion Ampliacion Item Logistics Snapshot v2.9
-- Script de solo lectura. Ejecutar despues de la migracion Flyway.

DO $preconditions$
DECLARE
    missing_columns text;
    missing_constraints text;
BEGIN
    IF current_database() NOT IN (
        'connexa_platform_test',
        'connexa_platform_diarco',
        'connexa_platform_ms'
    ) THEN
        RAISE EXCEPTION 'Base operacional PDD incorrecta: %', current_database();
    END IF;

    IF to_regclass('stock_management.pdd_item_logistics_snapshot') IS NULL THEN
        RAISE EXCEPTION
            'Falta stock_management.pdd_item_logistics_snapshot';
    END IF;

    SELECT string_agg(required.column_name, ', ' ORDER BY required.column_name)
    INTO missing_columns
    FROM (
        VALUES
            ('source_logistics_id'),
            ('supplier_code'),
            ('logistics_configuration_code'),
            ('source_valid_from'),
            ('sells_by_weight'),
            ('package_uom'),
            ('unit_gtin'),
            ('package_gtin'),
            ('source_reference'),
            ('unit_net_weight_kg'),
            ('unit_gross_weight_kg'),
            ('package_gross_weight_kg'),
            ('weight_basis'),
            ('package_length_cm'),
            ('package_width_cm'),
            ('package_height_cm'),
            ('package_volume_m3'),
            ('volume_method'),
            ('packages_per_layer'),
            ('layers_per_pallet'),
            ('units_per_pallet'),
            ('pallet_type'),
            ('pallet_length_cm'),
            ('pallet_width_cm'),
            ('loaded_pallet_height_cm'),
            ('pallet_gross_weight_kg'),
            ('stackable'),
            ('max_stack_levels'),
            ('fragile'),
            ('hazardous'),
            ('temperature_zone'),
            ('temperature_min_c'),
            ('temperature_max_c'),
            ('orientation_code'),
            ('packaging_quality_status'),
            ('weight_quality_status'),
            ('volume_quality_status'),
            ('pallet_quality_status'),
            ('quality_issue_codes'),
            ('verified_at'),
            ('verified_by'),
            ('attributes')
    ) AS required(column_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM information_schema.columns AS actual
        WHERE actual.table_schema = 'stock_management'
          AND actual.table_name = 'pdd_item_logistics_snapshot'
          AND actual.column_name = required.column_name
    );

    IF missing_columns IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan columnas: %', missing_columns;
    END IF;

    SELECT string_agg(required.constraint_name, ', '
                      ORDER BY required.constraint_name)
    INTO missing_constraints
    FROM (
        VALUES
            ('ck_pdd_item_logistics_overall_quality'),
            ('ck_pdd_item_logistics_effective_values'),
            ('ck_pdd_item_logistics_source_identity'),
            ('ck_pdd_item_logistics_package_uom'),
            ('ck_pdd_item_logistics_gtin'),
            ('ck_pdd_item_logistics_weight_values'),
            ('ck_pdd_item_logistics_weight_relation'),
            ('ck_pdd_item_logistics_weight_basis'),
            ('ck_pdd_item_logistics_package_dimensions'),
            ('ck_pdd_item_logistics_volume_values'),
            ('ck_pdd_item_logistics_volume_method'),
            ('ck_pdd_item_logistics_pallet_values'),
            ('ck_pdd_item_logistics_pallet_consistency'),
            ('ck_pdd_item_logistics_units_pallet_consistency'),
            ('ck_pdd_item_logistics_stack'),
            ('ck_pdd_item_logistics_temperature'),
            ('ck_pdd_item_logistics_handling_codes'),
            ('ck_pdd_item_logistics_axis_quality'),
            ('ck_pdd_item_logistics_quality_issues'),
            ('ck_pdd_item_logistics_verification'),
            ('ck_pdd_item_logistics_attributes')
    ) AS required(constraint_name)
    WHERE NOT EXISTS (
        SELECT 1
        FROM pg_constraint AS actual
        WHERE actual.conrelid =
              'stock_management.pdd_item_logistics_snapshot'::regclass
          AND actual.conname = required.constraint_name
          AND actual.contype = 'c'
          AND actual.convalidated
    );

    IF missing_constraints IS NOT NULL THEN
        RAISE EXCEPTION
            'Faltan checks validados: %', missing_constraints;
    END IF;
END
$preconditions$;

-- Inventario de columnas nuevas y nulabilidad efectiva.
SELECT
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'stock_management'
  AND table_name = 'pdd_item_logistics_snapshot'
  AND column_name IN (
      'source_logistics_id', 'supplier_code',
      'logistics_configuration_code', 'source_valid_from',
      'sells_by_weight', 'package_uom', 'unit_gtin', 'package_gtin',
      'source_reference', 'unit_net_weight_kg', 'unit_gross_weight_kg',
      'package_gross_weight_kg', 'weight_basis', 'package_length_cm',
      'package_width_cm', 'package_height_cm', 'package_volume_m3',
      'volume_method', 'packages_per_layer', 'layers_per_pallet',
      'units_per_pallet', 'pallet_type', 'pallet_length_cm',
      'pallet_width_cm', 'loaded_pallet_height_cm',
      'pallet_gross_weight_kg', 'stackable', 'max_stack_levels',
      'fragile', 'hazardous', 'temperature_zone', 'temperature_min_c',
      'temperature_max_c', 'orientation_code',
      'packaging_quality_status', 'weight_quality_status',
      'volume_quality_status', 'pallet_quality_status',
      'quality_issue_codes', 'verified_at', 'verified_by', 'attributes'
  )
ORDER BY ordinal_position;

-- Cobertura actual por eje. LOGISTICS_CONTRACT_V2_NOT_POPULATED identifica
-- filas insertadas por un publicador V1 despues de aplicar la migracion.
SELECT
    count(*) AS snapshots,
    count(DISTINCT calculation_run_id) AS corridas,
    count(DISTINCT codigo_articulo) AS articulos,
    count(*) FILTER (
        WHERE source_logistics_id IS NOT NULL
    ) AS con_identidad_canonica,
    count(*) FILTER (
        WHERE packaging_quality_status IN ('VERIFIED', 'SOURCE')
    ) AS packaging_fuente,
    count(*) FILTER (
        WHERE weight_quality_status IN ('VERIFIED', 'SOURCE')
    ) AS peso_fuente,
    count(*) FILTER (
        WHERE volume_quality_status IN ('VERIFIED', 'SOURCE')
    ) AS volumen_fuente,
    count(*) FILTER (
        WHERE pallet_quality_status IN ('VERIFIED', 'SOURCE')
    ) AS pallet_fuente,
    count(*) FILTER (
        WHERE 'LOGISTICS_CONTRACT_V2_NOT_POPULATED' =
              ANY (quality_issue_codes)
    ) AS pendientes_publicador_v2
FROM stock_management.pdd_item_logistics_snapshot;

SELECT
    packaging_quality_status,
    weight_quality_status,
    volume_quality_status,
    pallet_quality_status,
    count(*) AS snapshots
FROM stock_management.pdd_item_logistics_snapshot
GROUP BY
    packaging_quality_status,
    weight_quality_status,
    volume_quality_status,
    pallet_quality_status
ORDER BY snapshots DESC;

-- Debe devolver todos los contadores en cero.
SELECT
    count(*) FILTER (
        WHERE unit_net_weight_kg <= 0
           OR unit_gross_weight_kg <= 0
           OR package_gross_weight_kg <= 0
           OR unit_weight_kg <= 0
    ) AS pesos_invalidos,
    count(*) FILTER (
        WHERE package_length_cm <= 0
           OR package_width_cm <= 0
           OR package_height_cm <= 0
           OR package_volume_m3 <= 0
           OR unit_volume_m3 <= 0
    ) AS dimensiones_volumen_invalidos,
    count(*) FILTER (
        WHERE packages_per_layer <= 0
           OR layers_per_pallet <= 0
           OR packages_per_pallet <= 0
           OR units_per_pallet <= 0
    ) AS pallet_invalidos,
    count(*) FILTER (
        WHERE unit_net_weight_kg IS NOT NULL
          AND unit_gross_weight_kg IS NOT NULL
          AND unit_gross_weight_kg < unit_net_weight_kg
    ) AS bruto_menor_neto,
    count(*) FILTER (
        WHERE packages_per_layer IS NOT NULL
          AND layers_per_pallet IS NOT NULL
          AND packages_per_pallet IS NOT NULL
          AND packages_per_pallet <>
              packages_per_layer::numeric * layers_per_pallet::numeric
    ) AS pallet_inconsistente,
    count(*) FILTER (
        WHERE units_per_package IS NOT NULL
          AND packages_per_pallet IS NOT NULL
          AND units_per_pallet IS NOT NULL
          AND units_per_pallet <>
              units_per_package * packages_per_pallet
    ) AS unidades_pallet_inconsistentes,
    count(*) FILTER (
        WHERE packaging_quality_status IS NULL
           OR weight_quality_status IS NULL
           OR volume_quality_status IS NULL
           OR pallet_quality_status IS NULL
           OR quality_issue_codes IS NULL
           OR attributes IS NULL
    ) AS calidad_nula
FROM stock_management.pdd_item_logistics_snapshot;

-- Restricciones e indices instalados.
SELECT
    conname AS constraint_name,
    contype AS constraint_type,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'stock_management.pdd_item_logistics_snapshot'::regclass
ORDER BY contype, conname;

SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'stock_management'
  AND tablename = 'pdd_item_logistics_snapshot'
ORDER BY indexname;
