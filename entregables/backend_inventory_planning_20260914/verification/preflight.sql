-- SOLO SELECT. Ejecutar antes del reset y guardar el resultado.
SELECT current_database(),current_setting('server_version');
SELECT count(*) AS test_replenishment_rows FROM inventory.inv_product_site_replenishment;
SELECT column_name,data_type,is_nullable,column_default FROM information_schema.columns
 WHERE table_schema='inventory' AND table_name='inv_product_site_replenishment' ORDER BY ordinal_position;
SELECT conrelid::regclass AS source,pg_get_constraintdef(oid) FROM pg_constraint
 WHERE contype='f' AND confrelid='inventory.inv_product_site_replenishment'::regclass;
SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger
 WHERE tgrelid='inventory.inv_product_site_replenishment'::regclass AND NOT tgisinternal;
SELECT version,script,success FROM inventory.flyway_schema_history ORDER BY installed_rank;
SELECT count(*) AS products_with_multiple_principal FROM (
 SELECT product_id FROM inventory.inv_logistic_variable WHERE active AND principal
 GROUP BY product_id HAVING count(*)>1) x;
