/*
===============================================================================
PDD - Seed DESA de tipos de vehículo simulados v1.0

Base permitida : connexa_platform_diarco (DESA)
Esquema        : stock_management
Dependencia    : Migración catálogo de tipos de vehículo v3.0

ADVERTENCIAS
- Datos transitorios tomados visualmente de una pantalla de Valkimia.
- No ejecutar en TEST ni PROD.
- Los valores no constituyen datos maestros confirmados.
- Se asume peso en kg, volumen en m3 y capacidad en pallets equivalentes.
- Los ceros de la imagen se convierten en NULL y el tipo queda no planificable.
- El proceso es idempotente para filas previamente creadas por este mismo seed.
===============================================================================
*/

DO $preconditions$
DECLARE
    conflicting_rows integer;
BEGIN
    IF current_database() <> 'connexa_platform_diarco' THEN
        RAISE EXCEPTION
            'Seed exclusivo de DESA. Base actual: %',
            current_database();
    END IF;

    IF to_regclass('stock_management.pdd_vehicle_type') IS NULL THEN
        RAISE EXCEPTION
            'No existe stock_management.pdd_vehicle_type; aplicar antes la migración v3.0';
    END IF;

    SELECT count(*)
      INTO conflicting_rows
    FROM stock_management.pdd_vehicle_type current_row
    JOIN (
        VALUES
            ('TRACTOR',          '100'),
            ('SEMI_24P',         '101'),
            ('SEMI_28P',         '103'),
            ('SEMI_30P',         '104'),
            ('CTN_21P',          '105'),
            ('FURGON_24P',       '106'),
            ('FURGON_26P',       '107'),
            ('FURGON_28P',       '108'),
            ('FURGON_30P',       '109'),
            ('CHASIS',           '110'),
            ('FURGON_AM_TRUCK',  '111')
    ) AS seed(vehicle_type_code, valkimia_type_code)
      ON current_row.vehicle_type_code = seed.vehicle_type_code
      OR current_row.valkimia_type_code = seed.valkimia_type_code
    WHERE current_row.attributes ->> 'data_status' IS DISTINCT FROM
          'SIMULATED_DESA'
       OR current_row.vehicle_type_code <> seed.vehicle_type_code
       OR current_row.valkimia_type_code <> seed.valkimia_type_code;

    IF conflicting_rows > 0 THEN
        RAISE EXCEPTION
            'Hay % tipos existentes oficiales o con mapping incompatible. El seed no los sobrescribirá',
            conflicting_rows;
    END IF;
END
$preconditions$;

INSERT INTO stock_management.pdd_vehicle_type (
    vehicle_type_code,
    description,
    valkimia_type_code,
    max_payload_weight_kg,
    max_volume_m3,
    max_pallets,
    is_active,
    is_plannable,
    display_order,
    attributes,
    created_by,
    updated_by
)
VALUES
    (
        'TRACTOR', 'TRACTOR', '100',
        NULL, NULL, NULL,
        true, false, 1,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'zero_values_mapped_to_null', true,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'SEMI_24P', 'SEMI 24 P', '101',
        24000, 87, 21,
        true, true, 2,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'SEMI_28P', 'SEMI 28 P', '103',
        28000, 100, 28,
        true, true, 3,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'SEMI_30P', 'SEMI 30 P', '104',
        26000, 108, 30,
        true, true, 4,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'CTN_21P', 'CTN 21 P', '105',
        26000, 76, 21,
        true, true, 5,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'description_requires_confirmation', true,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'FURGON_24P', 'FURGON 24 P', '106',
        24000, 87, 24,
        true, true, 6,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'FURGON_26P', 'FURGON 26 P', '107',
        26000, 94, 26,
        true, true, 7,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'FURGON_28P', 'FURGON 28 P', '108',
        26000, 100, 28,
        true, true, 8,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'FURGON_30P', 'FURGON 30 P', '109',
        26000, 108, 30,
        true, true, 9,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'CHASIS', 'CHASIS', '110',
        6000, 25, NULL,
        true, false, 10,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'zero_values_mapped_to_null', true,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    ),
    (
        'FURGON_AM_TRUCK', 'FURGON AM TRUCK', '111',
        21000, 100, 30,
        true, true, 11,
        jsonb_build_object(
            'data_status', 'SIMULATED_DESA',
            'source', 'VALKIMIA_SCREENSHOT',
            'confirmed', false,
            'description_requires_confirmation', true,
            'weight_semantics', 'MAX_LOAD_WEIGHT_KG_UNCONFIRMED'
        ),
        'pdd.seed.image.desa', 'pdd.seed.image.desa'
    )
ON CONFLICT (vehicle_type_code) DO UPDATE
SET
    description = EXCLUDED.description,
    valkimia_type_code = EXCLUDED.valkimia_type_code,
    max_payload_weight_kg = EXCLUDED.max_payload_weight_kg,
    max_volume_m3 = EXCLUDED.max_volume_m3,
    max_pallets = EXCLUDED.max_pallets,
    is_active = EXCLUDED.is_active,
    is_plannable = EXCLUDED.is_plannable,
    display_order = EXCLUDED.display_order,
    attributes = EXCLUDED.attributes,
    row_version = stock_management.pdd_vehicle_type.row_version + 1,
    updated_by = EXCLUDED.updated_by,
    updated_at = clock_timestamp()
WHERE stock_management.pdd_vehicle_type.attributes ->> 'data_status' =
      'SIMULATED_DESA'
  AND ROW(
        stock_management.pdd_vehicle_type.description,
        stock_management.pdd_vehicle_type.valkimia_type_code,
        stock_management.pdd_vehicle_type.max_payload_weight_kg,
        stock_management.pdd_vehicle_type.max_volume_m3,
        stock_management.pdd_vehicle_type.max_pallets,
        stock_management.pdd_vehicle_type.is_active,
        stock_management.pdd_vehicle_type.is_plannable,
        stock_management.pdd_vehicle_type.display_order,
        stock_management.pdd_vehicle_type.attributes
      ) IS DISTINCT FROM ROW(
        EXCLUDED.description,
        EXCLUDED.valkimia_type_code,
        EXCLUDED.max_payload_weight_kg,
        EXCLUDED.max_volume_m3,
        EXCLUDED.max_pallets,
        EXCLUDED.is_active,
        EXCLUDED.is_plannable,
        EXCLUDED.display_order,
        EXCLUDED.attributes
      );

-- Resultado de la carga.
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
    attributes ->> 'data_status' AS data_status,
    row_version,
    updated_at
FROM stock_management.pdd_vehicle_type
WHERE attributes ->> 'data_status' = 'SIMULATED_DESA'
ORDER BY display_order, vehicle_type_code;

-- Resumen esperado: 11 tipos simulados y 9 planificables.
SELECT
    count(*) AS tipos_simulados,
    count(*) FILTER (WHERE is_plannable) AS tipos_planificables,
    count(*) FILTER (WHERE NOT is_plannable) AS tipos_no_planificables,
    count(*) FILTER (
        WHERE is_plannable
          AND (
              max_payload_weight_kg IS NULL
              OR max_volume_m3 IS NULL
              OR max_pallets IS NULL
          )
    ) AS planificables_incompletos
FROM stock_management.pdd_vehicle_type
WHERE attributes ->> 'data_status' = 'SIMULATED_DESA';
