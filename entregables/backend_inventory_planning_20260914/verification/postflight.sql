-- SOLO SELECT. Repetir despues de migrar y despues de cargar parametros/selecciones.
SELECT table_schema,table_name,column_name,data_type,is_nullable FROM information_schema.columns
 WHERE (table_schema='inventory' AND table_name IN ('inv_product_site_replenishment','inv_product_planning_logistics'))
 OR (table_schema='supply_planning' AND table_name='spl_forecast_planning_input')
 ORDER BY table_schema,table_name,ordinal_position;
SELECT count(*) AS obsolete_columns FROM information_schema.columns
 WHERE table_schema='inventory' AND table_name='inv_product_site_replenishment'
 AND column_name IN ('target_coverage_days','safety_stock_days');
SELECT count(*) AS parameters FROM inventory.inv_product_site_replenishment;
SELECT count(*) AS selected_logistics,
 count(*) FILTER(WHERE NOT usable_for_forecast) AS unusable_selected_logistics
 FROM inventory.inv_planning_logistics_v;
SELECT count(*) AS active_parameters_on_inactive_pairs
 FROM inventory.inv_planning_parameters_v WHERE NOT product_site_active;
SELECT entity_name,operation,count(*) FROM inventory.inv_planning_parameter_audit GROUP BY 1,2;
-- Cobertura debe medirse contra el scope real enviado por cada consumidor,
-- usando application/read_parameters_by_codes.sql. Un conteo global no la certifica.
