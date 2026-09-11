-- Solo lectura. Ejecutar antes de integrar las migraciones.
SELECT current_database(), current_setting('server_version');
SELECT table_name,column_name,udt_name,is_nullable
FROM information_schema.columns
WHERE table_schema='supply_planning'
  AND table_name IN ('spl_stock_policy_version','spl_stock_policy_rule',
                    'spl_stock_purchase_classification','spl_stock_policy_import_row')
ORDER BY table_name,ordinal_position;

SELECT to_regclass('supply_planning.spl_site') AS site_master,
       to_regclass('supply_planning.spl_supply_cluster') AS cluster_master,
       to_regclass('supply_planning.spl_category') AS category_master;

-- Comparar los objetos presentes con V2026091101. IF NOT EXISTS no valida drift.
-- Si no existen, Flyway los crea. Si difieren del DDL del borrador, detener y reconciliar.
