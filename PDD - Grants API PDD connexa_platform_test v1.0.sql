-- PDD API v1.0 - privilegios minimos para el adaptador HTTP.
-- Ejecutar en connexa_platform_test con ON_ERROR_STOP y un rol existente.
-- Cambiar connexa_pdd_api si la plataforma define otro nombre.

BEGIN;

DO $guard$
BEGIN
    IF current_database() <> 'connexa_platform_test' THEN
        RAISE EXCEPTION 'Este script solo admite connexa_platform_test; actual=%', current_database();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'connexa_pdd_api') THEN
        RAISE EXCEPTION 'Debe crear previamente el rol LOGIN connexa_pdd_api mediante el gestor de secretos';
    END IF;
END
$guard$;

GRANT CONNECT ON DATABASE connexa_platform_test TO connexa_pdd_api;
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
    stock_management.pdd_integration_message,
    stock_management.pdd_business_event_log
TO connexa_pdd_api;

GRANT INSERT, UPDATE ON TABLE
    stock_management.pdd_directed_need
TO connexa_pdd_api;

GRANT INSERT, UPDATE, DELETE ON TABLE
    stock_management.pdd_directed_need_line
TO connexa_pdd_api;

GRANT INSERT ON TABLE
    stock_management.pdd_directed_need_version,
    stock_management.pdd_integration_message,
    stock_management.pdd_business_event_log
TO connexa_pdd_api;

GRANT USAGE, SELECT ON SEQUENCE
    stock_management.pdd_directed_need_directed_need_id_seq,
    stock_management.pdd_directed_need_line_directed_need_line_id_seq,
    stock_management.pdd_directed_need_version_directed_need_version_id_seq,
    stock_management.pdd_integration_message_integration_message_id_seq,
    stock_management.pdd_business_event_log_business_event_id_seq
TO connexa_pdd_api;

COMMIT;
