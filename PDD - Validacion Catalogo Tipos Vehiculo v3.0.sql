/*
===============================================================================
PDD - Validación catálogo de tipos de vehículo v3.0
Ejecución: lectura posterior a la migración y a la carga inicial confirmada.
Resultado esperado: todos los booleanos de contrato en true y todos los
contadores de inconsistencias en cero.
===============================================================================
*/

-- 1. Contrato físico mínimo.
WITH expected_columns(column_name) AS (
    VALUES
        ('vehicle_type_id'),
        ('vehicle_type_uuid'),
        ('vehicle_type_code'),
        ('description'),
        ('valkimia_type_code'),
        ('max_payload_weight_kg'),
        ('max_volume_m3'),
        ('max_pallets'),
        ('is_active'),
        ('is_plannable'),
        ('display_order'),
        ('attributes'),
        ('row_version'),
        ('created_by'),
        ('created_at'),
        ('updated_by'),
        ('updated_at')
),
missing_columns AS (
    SELECT e.column_name
    FROM expected_columns e
    LEFT JOIN information_schema.columns c
      ON c.table_schema = 'stock_management'
     AND c.table_name = 'pdd_vehicle_type'
     AND c.column_name = e.column_name
    WHERE c.column_name IS NULL
)
SELECT
    to_regclass('stock_management.pdd_vehicle_type') IS NOT NULL
        AS tabla_creada,
    NOT EXISTS (SELECT 1 FROM missing_columns)
        AS columnas_completas,
    EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_pdd_dispatch_trip_vehicle_type'
          AND conrelid =
              'stock_management.pdd_dispatch_trip'::regclass
    ) AS fk_viaje_creada,
    EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pdd_dispatch_trip_vehicle_snapshot'
          AND conrelid =
              'stock_management.pdd_dispatch_trip'::regclass
    ) AS check_snapshot_creado;

-- 2. Integridad del catálogo.
SELECT
    count(*) AS tipos,
    count(*) FILTER (WHERE is_active) AS activos,
    count(*) FILTER (WHERE is_active AND is_plannable) AS planificables,
    count(*) FILTER (
        WHERE max_payload_weight_kg IS NOT NULL
          AND max_payload_weight_kg <= 0
    ) AS pesos_invalidos,
    count(*) FILTER (
        WHERE max_volume_m3 IS NOT NULL
          AND max_volume_m3 <= 0
    ) AS volumenes_invalidos,
    count(*) FILTER (
        WHERE max_pallets IS NOT NULL
          AND max_pallets <= 0
    ) AS pallets_invalidos,
    count(*) FILTER (
        WHERE is_plannable
          AND (
              NOT is_active
              OR max_payload_weight_kg IS NULL
              OR max_volume_m3 IS NULL
              OR max_pallets IS NULL
          )
    ) AS planificables_incompletos
FROM stock_management.pdd_vehicle_type;

-- 3. Duplicados lógicos. Debe devolver cero filas.
SELECT 'VEHICLE_TYPE_CODE' AS duplicate_key, vehicle_type_code AS value,
       count(*) AS records
FROM stock_management.pdd_vehicle_type
GROUP BY vehicle_type_code
HAVING count(*) > 1
UNION ALL
SELECT 'VALKIMIA_TYPE_CODE', valkimia_type_code, count(*)
FROM stock_management.pdd_vehicle_type
WHERE valkimia_type_code IS NOT NULL
GROUP BY valkimia_type_code
HAVING count(*) > 1;

-- 4. Integridad de viajes vinculados.
SELECT
    count(*) FILTER (WHERE t.vehicle_type_id IS NOT NULL) AS viajes_vinculados,
    count(*) FILTER (
        WHERE t.vehicle_type_id IS NOT NULL
          AND v.vehicle_type_id IS NULL
    ) AS referencias_huerfanas,
    count(*) FILTER (
        WHERE t.vehicle_type_id IS NOT NULL
          AND (
              t.vehicle_type_code IS NULL
              OR btrim(t.vehicle_type_code) = ''
              OR t.vehicle_type IS NULL
              OR btrim(t.vehicle_type) = ''
              OR t.vehicle_type_catalog_row_version IS NULL
              OR t.max_weight_kg IS NULL
              OR t.max_volume_m3 IS NULL
              OR t.max_pallets IS NULL
          )
    ) AS snapshots_incompletos,
    count(*) FILTER (
        WHERE t.vehicle_type_id IS NOT NULL
          AND t.vehicle_type_code <> v.vehicle_type_code
    ) AS codigos_snapshot_distintos
FROM stock_management.pdd_dispatch_trip t
LEFT JOIN stock_management.pdd_vehicle_type v
  ON v.vehicle_type_id = t.vehicle_type_id;

-- 5. Catálogo visible para planificación.
SELECT
    vehicle_type_uuid,
    vehicle_type_code,
    description,
    valkimia_type_code,
    max_payload_weight_kg,
    max_volume_m3,
    max_pallets,
    is_active,
    is_plannable,
    display_order,
    row_version,
    updated_at,
    updated_by
FROM stock_management.pdd_vehicle_type
ORDER BY display_order NULLS LAST, description, vehicle_type_code;

