/*
===============================================================================
PDD - Grants catálogo de tipos de vehículo v1.0
Aplicar después de la migración v3.0 cuando el microservicio utilice el rol
connexa_pdd_api. No otorga DELETE: la baja es lógica.
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
            'Base no autorizada para grants PDD: %',
            current_database();
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'connexa_pdd_api'
    ) THEN
        RAISE EXCEPTION
            'No existe el rol connexa_pdd_api';
    END IF;

    IF to_regclass('stock_management.pdd_vehicle_type') IS NULL THEN
        RAISE EXCEPTION
            'No existe stock_management.pdd_vehicle_type; aplicar antes la migración v3.0';
    END IF;
END
$preconditions$;

GRANT USAGE ON SCHEMA stock_management TO connexa_pdd_api;

GRANT SELECT, INSERT, UPDATE ON TABLE
    stock_management.pdd_vehicle_type
TO connexa_pdd_api;

GRANT USAGE, SELECT ON SEQUENCE
    stock_management.pdd_vehicle_type_vehicle_type_id_seq
TO connexa_pdd_api;

