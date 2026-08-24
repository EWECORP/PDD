/*
===============================================================================
PDD - Migración catálogo de tipos de vehículo v3.0
Base destino : connexa_platform_test / connexa_platform_diarco /
               connexa_platform_ms
Esquema      : stock_management
Propietario  : equipo BACK Java Stock Management
Ejecución    : Flyway, como nueva migración aprobada y con ON_ERROR_STOP

IMPORTANTE
- No modificar migraciones Flyway ya aplicadas (v2.7, v2.8 o v2.9).
- Este archivo no incluye BEGIN/COMMIT ni comandos exclusivos de psql.
- El catálogo se crea vacío. Los valores observados en Valkimia deben cargarse
  solamente después de confirmar código, unidad y vigencia con el negocio.
- Los viajes históricos permanecen válidos: vehicle_type_id es nullable.
===============================================================================
*/

DO $preconditions$
BEGIN
    IF current_database() NOT IN (
        'connexa_platform_test',
        'connexa_platform_diarco',
        'connexa_platform_ms'
    ) THEN
        RAISE EXCEPTION
            'Base no autorizada para la migración PDD v3.0: %',
            current_database();
    END IF;

    IF to_regnamespace('stock_management') IS NULL THEN
        RAISE EXCEPTION 'No existe el esquema stock_management';
    END IF;

    IF to_regclass('stock_management.pdd_dispatch_trip') IS NULL THEN
        RAISE EXCEPTION
            'No existe stock_management.pdd_dispatch_trip; aplicar antes la migración de planificación v2.7';
    END IF;
END
$preconditions$;

CREATE TABLE IF NOT EXISTS stock_management.pdd_vehicle_type (
    vehicle_type_id                 bigint GENERATED ALWAYS AS IDENTITY,
    vehicle_type_uuid               uuid NOT NULL DEFAULT gen_random_uuid(),
    vehicle_type_code               varchar(40) NOT NULL,
    description                     varchar(160) NOT NULL,
    valkimia_type_code              varchar(40),

    max_payload_weight_kg           numeric(18,6),
    max_volume_m3                   numeric(18,9),
    max_pallets                     numeric(18,6),

    is_active                       boolean NOT NULL DEFAULT true,
    is_plannable                    boolean NOT NULL DEFAULT false,
    display_order                   integer,
    attributes                      jsonb NOT NULL DEFAULT '{}'::jsonb,

    row_version                     integer NOT NULL DEFAULT 1,
    created_by                      varchar(100) NOT NULL,
    created_at                      timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_by                      varchar(100) NOT NULL,
    updated_at                      timestamptz NOT NULL DEFAULT clock_timestamp(),

    CONSTRAINT pdd_vehicle_type_pkey
        PRIMARY KEY (vehicle_type_id),
    CONSTRAINT uq_pdd_vehicle_type_uuid
        UNIQUE (vehicle_type_uuid),
    CONSTRAINT uq_pdd_vehicle_type_code
        UNIQUE (vehicle_type_code),
    CONSTRAINT ck_pdd_vehicle_type_code
        CHECK (
            vehicle_type_code = btrim(vehicle_type_code)
            AND vehicle_type_code ~ '^[A-Z0-9][A-Z0-9_-]*$'
        ),
    CONSTRAINT ck_pdd_vehicle_type_description
        CHECK (btrim(description) <> ''),
    CONSTRAINT ck_pdd_vehicle_type_valkimia_code
        CHECK (
            valkimia_type_code IS NULL
            OR btrim(valkimia_type_code) <> ''
        ),
    CONSTRAINT ck_pdd_vehicle_type_weight
        CHECK (
            max_payload_weight_kg IS NULL
            OR max_payload_weight_kg > 0
        ),
    CONSTRAINT ck_pdd_vehicle_type_volume
        CHECK (
            max_volume_m3 IS NULL
            OR max_volume_m3 > 0
        ),
    CONSTRAINT ck_pdd_vehicle_type_pallets
        CHECK (
            max_pallets IS NULL
            OR max_pallets > 0
        ),
    CONSTRAINT ck_pdd_vehicle_type_plannable
        CHECK (
            NOT is_plannable
            OR (
                is_active
                AND max_payload_weight_kg IS NOT NULL
                AND max_volume_m3 IS NOT NULL
                AND max_pallets IS NOT NULL
            )
        ),
    CONSTRAINT ck_pdd_vehicle_type_display_order
        CHECK (display_order IS NULL OR display_order > 0),
    CONSTRAINT ck_pdd_vehicle_type_attributes
        CHECK (jsonb_typeof(attributes) = 'object'),
    CONSTRAINT ck_pdd_vehicle_type_row_version
        CHECK (row_version > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdd_vehicle_type_valkimia_code
    ON stock_management.pdd_vehicle_type (valkimia_type_code)
    WHERE valkimia_type_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_pdd_vehicle_type_planning
    ON stock_management.pdd_vehicle_type (
        is_active,
        is_plannable,
        display_order,
        description
    );

ALTER TABLE stock_management.pdd_dispatch_trip
    ADD COLUMN IF NOT EXISTS vehicle_type_id bigint,
    ADD COLUMN IF NOT EXISTS vehicle_type_code varchar(40),
    ADD COLUMN IF NOT EXISTS vehicle_type_catalog_row_version integer;

DO $trip_vehicle_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_pdd_dispatch_trip_vehicle_type'
          AND conrelid =
              'stock_management.pdd_dispatch_trip'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_dispatch_trip
            ADD CONSTRAINT fk_pdd_dispatch_trip_vehicle_type
            FOREIGN KEY (vehicle_type_id)
            REFERENCES stock_management.pdd_vehicle_type (vehicle_type_id)
            ON UPDATE RESTRICT
            ON DELETE RESTRICT;
    END IF;
END
$trip_vehicle_fk$;

DO $trip_vehicle_snapshot_check$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_pdd_dispatch_trip_vehicle_snapshot'
          AND conrelid =
              'stock_management.pdd_dispatch_trip'::regclass
    ) THEN
        ALTER TABLE stock_management.pdd_dispatch_trip
            ADD CONSTRAINT ck_pdd_dispatch_trip_vehicle_snapshot
            CHECK (
                vehicle_type_id IS NULL
                OR (
                    vehicle_type_code IS NOT NULL
                    AND btrim(vehicle_type_code) <> ''
                    AND vehicle_type IS NOT NULL
                    AND btrim(vehicle_type) <> ''
                    AND vehicle_type_catalog_row_version IS NOT NULL
                    AND vehicle_type_catalog_row_version > 0
                    AND max_weight_kg IS NOT NULL
                    AND max_volume_m3 IS NOT NULL
                    AND max_pallets IS NOT NULL
                )
            );
    END IF;
END
$trip_vehicle_snapshot_check$;

CREATE INDEX IF NOT EXISTS ix_pdd_dispatch_trip_vehicle_type
    ON stock_management.pdd_dispatch_trip (vehicle_type_id)
    WHERE vehicle_type_id IS NOT NULL;

COMMENT ON TABLE stock_management.pdd_vehicle_type IS
    'Catálogo canónico Connexa de tipos de vehículo habilitados para planificar viajes PDD.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.vehicle_type_code IS
    'Código canónico e inmutable de Connexa. No depende de la descripción visible.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.valkimia_type_code IS
    'Código opcional del tipo equivalente en Valkimia; debe ser único cuando se informa.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.max_payload_weight_kg IS
    'Carga útil máxima en kilogramos. NULL significa dato no confirmado; cero no es una capacidad válida.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.max_volume_m3 IS
    'Volumen útil máximo en metros cúbicos. NULL significa dato no confirmado; cero no es una capacidad válida.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.max_pallets IS
    'Posiciones equivalentes de pallet admitidas. NULL significa dato no confirmado; cero no es una capacidad válida.';

COMMENT ON COLUMN stock_management.pdd_vehicle_type.is_plannable IS
    'Sólo puede ser true cuando el tipo está activo y las tres capacidades están confirmadas y son positivas.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.vehicle_type_id IS
    'Referencia al catálogo utilizado al crear o cambiar el vehículo del viaje. Nullable únicamente para compatibilidad histórica.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.vehicle_type_code IS
    'Snapshot del código canónico del tipo de vehículo aplicado al viaje.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.vehicle_type_catalog_row_version IS
    'Versión del registro de catálogo cuyas capacidades fueron copiadas al viaje.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.vehicle_type IS
    'Snapshot de la descripción del tipo de vehículo; no debe resolverse dinámicamente desde el catálogo.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.max_weight_kg IS
    'Snapshot de capacidad máxima de peso aplicado al viaje.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.max_volume_m3 IS
    'Snapshot de capacidad máxima de volumen aplicado al viaje.';

COMMENT ON COLUMN stock_management.pdd_dispatch_trip.max_pallets IS
    'Snapshot de capacidad máxima de pallets aplicado al viaje.';

