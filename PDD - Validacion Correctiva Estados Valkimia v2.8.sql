-- PDD - Validacion Correctiva Estados Valkimia v2.8
-- Solo lectura. Ejecutar despues de la migracion correctiva v2.8.

WITH required_status(name, is_terminal) AS (
    VALUES
        ('IMPORTED', false),
        ('ACCEPTED', false),
        ('PARTIAL', false),
        ('PREPARED', false),
        ('DISPATCHED', false),
        ('DELIVERED', true),
        ('CANCELLED', true),
        ('REJECTED', true),
        ('FAILED', true),
        ('UNKNOWN', false)
),
catalog_control AS (
    SELECT
        count(*) FILTER (WHERE actual.id IS NULL) AS required_missing,
        count(*) FILTER (
            WHERE actual.id IS NOT NULL
              AND actual.is_terminal IS DISTINCT FROM required.is_terminal
        ) AS terminality_mismatch
    FROM required_status AS required
    LEFT JOIN stock_management.pdd_valkimia_import_line_status AS actual
      ON actual.name = required.name
),
column_control AS (
    SELECT
        count(*) FILTER (
            WHERE table_name = 'pdd_execution_event'
              AND column_name = 'status_id'
              AND is_nullable = 'NO'
        ) AS event_status_fk_column,
        count(*) FILTER (
            WHERE table_name = 'pdd_execution_event'
              AND column_name = 'normalized_status'
        ) AS legacy_event_status_column,
        count(*) FILTER (
            WHERE table_name = 'pdd_valkimia_status_mapping'
              AND column_name = 'is_terminal'
        ) AS duplicated_terminality_column
    FROM information_schema.columns
    WHERE table_schema = 'stock_management'
      AND table_name IN (
          'pdd_execution_event',
          'pdd_valkimia_status_mapping'
      )
),
fk_control AS (
    SELECT count(*) AS event_status_fk
    FROM pg_constraint
    WHERE conrelid = 'stock_management.pdd_execution_event'::regclass
      AND contype = 'f'
      AND confrelid =
          'stock_management.pdd_valkimia_import_line_status'::regclass
),
index_control AS (
    SELECT count(*) AS line_status_index
    FROM pg_indexes
    WHERE schemaname = 'stock_management'
      AND tablename = 'pdd_valkimia_import_line'
      AND indexname = 'ix_pdd_valkimia_import_line_status_updated'
),
data_control AS (
    SELECT
        count(*) FILTER (WHERE status.id IS NULL) AS orphan_events
    FROM stock_management.pdd_execution_event AS event
    LEFT JOIN stock_management.pdd_valkimia_import_line_status AS status
      ON status.id = event.status_id
)
SELECT
    catalog.required_missing = 0 AS required_statuses_ok,
    catalog.terminality_mismatch = 0 AS terminality_ok,
    columns.event_status_fk_column = 1 AS event_status_column_ok,
    columns.legacy_event_status_column = 0 AS legacy_event_status_removed,
    columns.duplicated_terminality_column = 0 AS duplicated_terminality_removed,
    fk.event_status_fk = 1 AS event_status_fk_ok,
    indexes.line_status_index = 1 AS line_status_index_ok,
    data.orphan_events = 0 AS event_data_integrity_ok
FROM catalog_control AS catalog
CROSS JOIN column_control AS columns
CROSS JOIN fk_control AS fk
CROSS JOIN index_control AS indexes
CROSS JOIN data_control AS data;

SELECT
    id,
    name,
    description,
    is_terminal,
    is_active,
    display_order
FROM stock_management.pdd_valkimia_import_line_status
ORDER BY display_order;

SELECT
    table_name,
    constraint_name,
    constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'stock_management'
  AND table_name IN (
      'pdd_valkimia_import_line',
      'pdd_valkimia_status_mapping',
      'pdd_execution_event'
  )
  AND constraint_type IN ('FOREIGN KEY', 'CHECK')
ORDER BY table_name, constraint_name;
