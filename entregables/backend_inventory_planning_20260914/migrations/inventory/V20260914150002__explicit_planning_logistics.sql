-- Seleccion explicita: preserva las variables existentes, aunque varias sean principales.
ALTER TABLE inventory.inv_logistic_variable
  ADD CONSTRAINT uq_inv_logistic_variable_product_id UNIQUE(product_id,id);

CREATE TABLE inventory.inv_product_planning_logistics (
  product_id uuid PRIMARY KEY REFERENCES inventory.inv_product(id) ON DELETE CASCADE,
  logistic_variable_id uuid NOT NULL,
  row_version bigint NOT NULL DEFAULT 1 CHECK(row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by text NOT NULL CHECK(btrim(updated_by) <> ''),
  CONSTRAINT fk_inv_planning_logistics_same_product FOREIGN KEY(product_id,logistic_variable_id)
    REFERENCES inventory.inv_logistic_variable(product_id,id) ON DELETE RESTRICT
);
CREATE TRIGGER tr_inv_planning_logistics_stamp BEFORE INSERT OR UPDATE OR DELETE
  ON inventory.inv_product_planning_logistics FOR EACH ROW EXECUTE FUNCTION inventory.inv_planning_stamp();
CREATE TRIGGER tr_inv_planning_logistics_audit AFTER INSERT OR UPDATE OR DELETE
  ON inventory.inv_product_planning_logistics FOR EACH ROW EXECUTE FUNCTION inventory.inv_planning_audit_write();
COMMENT ON TABLE inventory.inv_product_planning_logistics IS
  'Una variable logistica elegida explicitamente por producto para PDD/FORECAST. No se carga automaticamente ni altera principal.';

CREATE VIEW inventory.inv_planning_logistics_v AS
SELECT s.product_id,s.logistic_variable_id,s.row_version AS selection_row_version,
  v.active,v.principal,v.purchase_factor,v.weight_in_gr,v.uom_id,
  v.boxes_per_layer,v.pallet_layers,v.units_per_box,v.units_per_pallet,v.volume,
  (v.active AND v.principal AND v.purchase_factor > 0 AND v.purchase_factor < 'Infinity'::float8
   AND v.uom_id IS NOT NULL AND btrim(v.uom_id) <> ''
   AND (v.uom_id='unidad' OR (v.weight_in_gr > 0 AND v.weight_in_gr < 'Infinity'::float8))) IS TRUE
   AS usable_for_forecast
FROM inventory.inv_product_planning_logistics s
JOIN inventory.inv_logistic_variable v ON v.id=s.logistic_variable_id AND v.product_id=s.product_id;

CREATE VIEW inventory.inv_planning_parameters_v AS
SELECT ps.product_id,ps.site_id,ps.id AS product_site_id,
  r.id AS replenishment_id,r.row_version AS replenishment_row_version,
  r.target_stock_days,r.overstock_days,r.minimum_order_quantity,r.order_multiple,
  r.preparation_days,r.lead_time_days,r.transit_days,
  ps.supply_type,ps.supplying_site_id,s.code AS supplying_site_code,
  ps.active AS product_site_active,ps.active_for_purchase,ps.active_for_transfer
FROM inventory.inv_product_site ps
JOIN inventory.inv_product_site_replenishment r ON r.product_site_id=ps.id AND r.active
LEFT JOIN inventory.inv_site s ON s.id=ps.supplying_site_id;
COMMENT ON VIEW inventory.inv_planning_parameters_v IS
  'Lectura de parametros activos, maximo una fila por par. Consumidor aplica elegibilidad propia, detecta faltantes y congela valores/revision. No filtra proveedor ni consolida OC.';
