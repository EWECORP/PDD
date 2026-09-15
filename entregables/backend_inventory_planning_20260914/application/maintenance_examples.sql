-- EJEMPLOS para adaptar al DAO/JDBC; no ejecutar como migracion/carga real.
-- Actor proviene del usuario autenticado o del servicio de carga identificado.
-- BEGIN/COMMIT los administra el servicio, en la misma conexion.
SELECT set_config('app.actor', :authenticated_actor, true);

INSERT INTO inventory.inv_product_site_replenishment(
 product_site_id,target_stock_days,overstock_days,minimum_order_quantity,preparation_days,
 order_multiple,lead_time_days,transit_days,active
) VALUES (
 CAST(:product_site_id AS uuid),:target_stock_days,:overstock_days,:minimum_order_quantity,
 :preparation_days,:order_multiple,:lead_time_days,:transit_days,:active
) RETURNING id,row_version,updated_at,updated_by;

UPDATE inventory.inv_product_site_replenishment
SET target_stock_days=:target_stock_days,overstock_days=:overstock_days,
 minimum_order_quantity=:minimum_order_quantity,preparation_days=:preparation_days,
 order_multiple=:order_multiple,lead_time_days=:lead_time_days,transit_days=:transit_days,active=:active
WHERE id=CAST(:id AS uuid) AND row_version=:expected_row_version
RETURNING id,row_version,updated_at,updated_by;
-- Cero filas: conflicto o registro inexistente; no reintentar pisando otra version.

INSERT INTO inventory.inv_product_planning_logistics(product_id,logistic_variable_id)
VALUES(CAST(:product_id AS uuid),CAST(:logistic_variable_id AS uuid))
RETURNING product_id,row_version;

UPDATE inventory.inv_product_planning_logistics
SET logistic_variable_id=CAST(:logistic_variable_id AS uuid)
WHERE product_id=CAST(:product_id AS uuid) AND row_version=:expected_row_version
RETURNING product_id,row_version;
