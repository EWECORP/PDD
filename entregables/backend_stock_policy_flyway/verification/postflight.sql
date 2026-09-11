SELECT v.id,v.status,count(r.id) AS rule_count
FROM supply_planning.spl_stock_policy_version v
LEFT JOIN supply_planning.spl_stock_policy_rule r ON r.policy_version_id=v.id
GROUP BY v.id,v.status;

SELECT mapping_status,count(*) FROM supply_planning.spl_stock_policy_import_row
GROUP BY mapping_status;

-- Debe devolver cero filas: rubros que no pertenecen a la familia seleccionada.
SELECT r.id,r.family_category_id,r.category_id
FROM supply_planning.spl_stock_policy_rule r
JOIN supply_planning.spl_category c ON c.id=r.category_id
WHERE c.parent_id IS DISTINCT FROM r.family_category_id;

SELECT indexname,indexdef FROM pg_indexes
WHERE schemaname='supply_planning' AND indexname LIKE 'spl_stock_policy%';
