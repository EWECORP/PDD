\set ON_ERROR_STOP on

-- Smoke test transaccional posterior a migracion v2.7.
-- Inserta una cadena minima y siempre ejecuta ROLLBACK.

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

DO $validate$
DECLARE
    missing text[];
    sample record;
    plan_id bigint;
    trip_id bigint;
    stop_id bigint;
    trip_line_id bigint;
    import_id bigint;
    planned numeric(18,6);
BEGIN
    SELECT array_agg(name ORDER BY name)
    INTO missing
    FROM unnest(ARRAY[
        'stock_management.pdd_dispatch_plan',
        'stock_management.pdd_dispatch_trip',
        'stock_management.pdd_dispatch_trip_stop',
        'stock_management.pdd_dispatch_trip_line',
        'stock_management.pdd_dispatch_line_allocation',
        'stock_management.pdd_valkimia_status_mapping',
        'stock_management.pdd_integration_checkpoint'
    ]) required(name)
    WHERE to_regclass(name) IS NULL;

    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'Faltan entidades v2.7: %', missing;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'stock_management'
          AND table_name = 'pdd_current_backlog_line'
          AND column_name = 'available_to_plan_quantity'
          AND is_generated = 'ALWAYS'
    ) THEN
        RAISE EXCEPTION 'available_to_plan_quantity no es columna generada';
    END IF;

    SELECT * INTO sample
    FROM stock_management.pdd_current_backlog_line
    ORDER BY priority_score DESC, backlog_line_id
    LIMIT 1;

    IF sample.backlog_line_id IS NULL THEN
        RAISE EXCEPTION 'No hay una linea de backlog para el smoke test';
    END IF;

    planned := least(sample.total_open_quantity, 1::numeric);

    INSERT INTO stock_management.pdd_dispatch_plan (
        plan_code, business_date, origin_cd, backlog_snapshot_version,
        status, planned_by
    ) VALUES (
        'VALIDATION-V27-' || txid_current()::text,
        sample.business_date, 41, sample.snapshot_version,
        'DRAFT', 'pdd.validation'
    ) RETURNING dispatch_plan_id INTO plan_id;

    INSERT INTO stock_management.pdd_dispatch_trip (
        dispatch_plan_id, trip_number, trip_code, status, created_by
    ) VALUES (
        plan_id, 1, 'VALIDATION-V27-TRIP-' || txid_current()::text,
        'DRAFT', 'pdd.validation'
    ) RETURNING dispatch_trip_id INTO trip_id;

    INSERT INTO stock_management.pdd_dispatch_trip_stop (
        dispatch_trip_id, stop_sequence, sucursal
    ) VALUES (
        trip_id, 1, sample.sucursal
    ) RETURNING dispatch_trip_stop_id INTO stop_id;

    INSERT INTO stock_management.pdd_dispatch_trip_line (
        dispatch_trip_id, dispatch_trip_stop_id, backlog_line_uuid,
        backlog_line_version, backlog_snapshot_version, codigo_articulo,
        sucursal, c_proveedor_primario, planned_quantity, status,
        input_checksum
    ) VALUES (
        trip_id, stop_id, sample.backlog_line_uuid,
        sample.row_version, sample.snapshot_version, sample.codigo_articulo,
        sample.sucursal, sample.c_proveedor_primario, planned, 'DRAFT',
        repeat('a', 64)
    ) RETURNING dispatch_trip_line_id INTO trip_line_id;

    INSERT INTO stock_management.pdd_valkimia_import (
        idempotency_key, adapter_code, origin_cd, backlog_snapshot_version,
        status, requested_by, line_count, total_imported_quantity,
        payload_checksum, dispatch_trip_id, dispatch_trip_stop_id
    ) VALUES (
        'VALIDATION-V27-' || txid_current()::text,
        'VALKIMIA_LEGACY', 41, sample.snapshot_version,
        'PENDING', 'pdd.validation', 1, planned,
        repeat('b', 64), trip_id, stop_id
    ) RETURNING valkimia_import_id INTO import_id;

    INSERT INTO stock_management.pdd_valkimia_import_line (
        valkimia_import_id, dispatch_trip_line_id, backlog_line_uuid,
        backlog_line_version, codigo_articulo, sucursal,
        imported_quantity, normalized_status
    ) VALUES (
        import_id, trip_line_id, sample.backlog_line_uuid,
        sample.row_version, sample.codigo_articulo, sample.sucursal,
        planned, 'IMPORTED'
    );

    RAISE NOTICE
        'OK v2.7: plan %, viaje %, parada %, linea %, importacion %',
        plan_id, trip_id, stop_id, trip_line_id, import_id;
END
$validate$;

ROLLBACK;

SELECT
    to_regclass('stock_management.pdd_dispatch_plan') IS NOT NULL AS plan_ok,
    to_regclass('stock_management.pdd_dispatch_trip') IS NOT NULL AS trip_ok,
    to_regclass('stock_management.pdd_dispatch_trip_line') IS NOT NULL AS line_ok,
    to_regclass('stock_management.pdd_valkimia_status_mapping') IS NOT NULL AS mapping_ok,
    to_regclass('stock_management.pdd_integration_checkpoint') IS NOT NULL AS checkpoint_ok;
