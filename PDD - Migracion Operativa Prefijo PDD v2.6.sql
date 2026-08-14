\set ON_ERROR_STOP on

BEGIN;

DO $guard$
BEGIN
    IF current_database() NOT IN ('connexa_platform_test', 'connexa_platform_ms') THEN
        RAISE EXCEPTION
            'Migracion PDD operativa v2.6: base incorrecta (%).', current_database();
    END IF;
END
$guard$;

-- stock_management es compartido por otros modulos de CONNEXA. Esta migracion
-- hace explicita la propiedad de todas las entidades PDD sin perder datos.
DO $rename_tables$
DECLARE
    old_name text;
    new_name text;
    pdd_tables constant text[] := ARRAY[
        'configuration_version',
        'pdvb_model_version',
        'distribution_scope_version',
        'distribution_scope_article',
        'distribution_scope_pair',
        'calculation_run',
        'source_snapshot',
        'pdvb_publication_batch',
        'pdvb_publication_stage',
        'pdvb_estimate',
        'pdvb_current',
        'pdvb_quality_issue',
        'pdvb_backtest_metric',
        'item_logistics_snapshot',
        'branch_stock_position',
        'cd_stock_position',
        'need_snapshot',
        'directed_need',
        'directed_need_line',
        'directed_need_version',
        'current_backlog_line',
        'backlog_source_allocation',
        'valkimia_import',
        'valkimia_import_line',
        'execution_event',
        'integration_message',
        'business_event_log'
    ];
BEGIN
    FOREACH old_name IN ARRAY pdd_tables LOOP
        new_name := 'pdd_' || old_name;
        IF to_regclass(format('stock_management.%I', old_name)) IS NOT NULL
           AND to_regclass(format('stock_management.%I', new_name)) IS NOT NULL THEN
            RAISE EXCEPTION
                'No se puede migrar: existen simultaneamente %.% y %.%',
                'stock_management', old_name, 'stock_management', new_name;
        ELSIF to_regclass(format('stock_management.%I', old_name)) IS NOT NULL THEN
            EXECUTE format(
                'ALTER TABLE stock_management.%I RENAME TO %I',
                old_name, new_name
            );
        END IF;
    END LOOP;
END
$rename_tables$;

-- Normaliza tambien nombres de constraints e indices para impedir colisiones
-- futuras en el mismo esquema. Los OID y las FK permanecen inalterados.
DO $rename_constraints$
DECLARE
    item record;
    new_name text;
BEGIN
    FOR item IN
        SELECT c.conname, t.relname
        FROM pg_constraint AS c
        JOIN pg_class AS t ON t.oid = c.conrelid
        JOIN pg_namespace AS n ON n.oid = t.relnamespace
        WHERE n.nspname = 'stock_management'
          AND t.relname LIKE 'pdd\_%' ESCAPE '\'
          AND c.conname NOT LIKE '%pdd%'
    LOOP
        new_name := CASE
            WHEN item.conname ~ '^(ck|uq|fk)_' THEN
                regexp_replace(item.conname, '^(ck|uq|fk)_', '\1_pdd_')
            ELSE 'pdd_' || item.conname
        END;
        EXECUTE format(
            'ALTER TABLE stock_management.%I RENAME CONSTRAINT %I TO %I',
            item.relname, item.conname, new_name
        );
    END LOOP;
END
$rename_constraints$;

DO $rename_indexes$
DECLARE
    item record;
    new_name text;
BEGIN
    FOR item IN
        SELECT i.relname
        FROM pg_class AS i
        JOIN pg_namespace AS n ON n.oid = i.relnamespace
        JOIN pg_index AS x ON x.indexrelid = i.oid
        JOIN pg_class AS t ON t.oid = x.indrelid
        WHERE n.nspname = 'stock_management'
          AND t.relname LIKE 'pdd\_%' ESCAPE '\'
          AND i.relname NOT LIKE '%pdd%'
    LOOP
        new_name := CASE
            WHEN item.relname ~ '^(ix|uq)_' THEN
                regexp_replace(item.relname, '^(ix|uq)_', '\1_pdd_')
            ELSE 'pdd_' || item.relname
        END;
        IF to_regclass(format('stock_management.%I', new_name)) IS NULL THEN
            EXECUTE format(
                'ALTER INDEX stock_management.%I RENAME TO %I',
                item.relname, new_name
            );
        END IF;
    END LOOP;
END
$rename_indexes$;

COMMIT;
