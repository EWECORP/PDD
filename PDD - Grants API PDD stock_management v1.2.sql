\set ON_ERROR_STOP on

-- Privilegios minimos PDD para backend Java Stock Management.
-- Admite TEST, DESA y Produccion. El rol debe existir en el ambiente.

BEGIN;

DO $guard$
BEGIN
    IF current_database() NOT IN (
        'connexa_platform_test',
        'connexa_platform_diarco',
        'connexa_platform_ms'
    ) THEN
        RAISE EXCEPTION 'Base no admitida para grants PDD: %', current_database();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'connexa_pdd_api') THEN
        RAISE EXCEPTION
            'Debe crear previamente el rol LOGIN connexa_pdd_api mediante el gestor de secretos';
    END IF;

    EXECUTE format(
        'GRANT CONNECT ON DATABASE %I TO connexa_pdd_api',
        current_database()
    );
END
$guard$;

GRANT USAGE ON SCHEMA stock_management TO connexa_pdd_api;

GRANT SELECT ON TABLE
    stock_management.pdd_current_backlog_line,
    stock_management.pdd_backlog_source_allocation,
    stock_management.pdd_calculation_run,
    stock_management.pdd_source_snapshot,
    stock_management.pdd_branch_stock_position,
    stock_management.pdd_need_snapshot,
    stock_management.pdd_distribution_scope_pair,
    stock_management.pdd_item_logistics_snapshot,
    stock_management.pdd_configuration_version,
    stock_management.pdd_directed_need,
    stock_management.pdd_directed_need_line,
    stock_management.pdd_directed_need_version,
    stock_management.pdd_dispatch_plan,
    stock_management.pdd_dispatch_trip,
    stock_management.pdd_dispatch_trip_stop,
    stock_management.pdd_dispatch_trip_line,
    stock_management.pdd_dispatch_line_allocation,
    stock_management.pdd_valkimia_import,
    stock_management.pdd_valkimia_import_line,
    stock_management.pdd_execution_event,
    stock_management.pdd_valkimia_status_mapping,
    stock_management.pdd_integration_checkpoint,
    stock_management.pdd_integration_message,
    stock_management.pdd_business_event_log
TO connexa_pdd_api;

GRANT INSERT, UPDATE ON TABLE
    stock_management.pdd_directed_need,
    stock_management.pdd_dispatch_plan,
    stock_management.pdd_valkimia_import,
    stock_management.pdd_valkimia_import_line,
    stock_management.pdd_execution_event,
    stock_management.pdd_valkimia_status_mapping,
    stock_management.pdd_integration_message,
    stock_management.pdd_integration_checkpoint
TO connexa_pdd_api;

GRANT INSERT, UPDATE, DELETE ON TABLE
    stock_management.pdd_directed_need_line,
    stock_management.pdd_dispatch_trip,
    stock_management.pdd_dispatch_trip_stop,
    stock_management.pdd_dispatch_trip_line,
    stock_management.pdd_dispatch_line_allocation
TO connexa_pdd_api;

GRANT INSERT ON TABLE
    stock_management.pdd_directed_need_version,
    stock_management.pdd_business_event_log
TO connexa_pdd_api;

GRANT UPDATE (
    active_planned_quantity,
    active_imported_quantity,
    prepared_quantity,
    in_transit_quantity,
    row_version
) ON stock_management.pdd_current_backlog_line
TO connexa_pdd_api;

GRANT USAGE, SELECT ON SEQUENCE
    stock_management.pdd_directed_need_directed_need_id_seq,
    stock_management.pdd_directed_need_line_directed_need_line_id_seq,
    stock_management.pdd_directed_need_version_directed_need_version_id_seq,
    stock_management.pdd_dispatch_plan_dispatch_plan_id_seq,
    stock_management.pdd_dispatch_trip_dispatch_trip_id_seq,
    stock_management.pdd_dispatch_trip_stop_dispatch_trip_stop_id_seq,
    stock_management.pdd_dispatch_trip_line_dispatch_trip_line_id_seq,
    stock_management.pdd_dispatch_line_allocation_dispatch_line_allocation_id_seq,
    stock_management.pdd_valkimia_import_valkimia_import_id_seq,
    stock_management.pdd_valkimia_import_line_valkimia_import_line_id_seq,
    stock_management.pdd_execution_event_execution_event_id_seq,
    stock_management.pdd_valkimia_status_mapping_valkimia_status_mapping_id_seq,
    stock_management.pdd_integration_checkpoint_integration_checkpoint_id_seq,
    stock_management.pdd_integration_message_integration_message_id_seq,
    stock_management.pdd_business_event_log_business_event_id_seq
TO connexa_pdd_api;

COMMIT;
