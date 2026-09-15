-- Parametro :pairs_json: [{"product_code":"10166","site_code":"11"}, ...].
-- Ejecutar en CONNEXA, no en diarco_data. No filtra por proveedor primario.
-- El caller debe enviar pares unicos; LEFT JOIN conserva faltantes para rechazarlos.
WITH scope AS (
 SELECT * FROM jsonb_to_recordset(CAST(:pairs_json AS jsonb))
 AS x(product_code text,site_code text)
)
SELECT x.product_code,x.site_code,p.id AS inventory_product_id,s.id AS inventory_site_id,
 q.*,l.logistic_variable_id,l.selection_row_version,l.usable_for_forecast,
 l.purchase_factor,l.weight_in_gr,l.uom_id,l.units_per_box,l.units_per_pallet,l.volume,
 current_timestamp AS captured_at
FROM scope x
LEFT JOIN inventory.inv_product p ON p.ext_code=x.product_code
LEFT JOIN inventory.inv_site s ON s.code=x.site_code
LEFT JOIN inventory.inv_planning_parameters_v q ON q.product_id=p.id AND q.site_id=s.id
LEFT JOIN inventory.inv_planning_logistics_v l ON l.product_id=p.id;
