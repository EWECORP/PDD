-- Fixture sintetico de relaciones afectadas, basado en baseline_test.json.
-- Solo base local descartable. No es una migracion ni una copia de datos TEST.
CREATE SCHEMA inventory;
CREATE SCHEMA supply_planning;
CREATE TABLE inventory.inv_product(id uuid PRIMARY KEY);
CREATE TABLE inventory.inv_site(id uuid PRIMARY KEY,code varchar NOT NULL UNIQUE);
CREATE TABLE inventory.inv_product_site(
 id uuid PRIMARY KEY,product_id uuid NOT NULL REFERENCES inventory.inv_product(id),
 site_id uuid NOT NULL REFERENCES inventory.inv_site(id),expected_stock_days float8 NOT NULL,
 supply_type varchar,supplying_site_id uuid REFERENCES inventory.inv_site(id),
 active boolean NOT NULL DEFAULT true,active_for_purchase boolean NOT NULL DEFAULT false,
 active_for_transfer boolean NOT NULL DEFAULT false,UNIQUE(product_id,site_id));
CREATE TABLE inventory.inv_product_site_replenishment(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 product_site_id uuid NOT NULL UNIQUE REFERENCES inventory.inv_product_site(id) ON DELETE CASCADE,
 replenishment_method varchar(80),target_coverage_days float8,safety_stock_days float8,
 minimum_order_quantity float8,order_multiple float8,lead_time_days float8,
 preparation_days float8,transit_days float8,replenishment_frequency varchar(80),
 active boolean NOT NULL DEFAULT true,created_at timestamp NOT NULL DEFAULT now());
CREATE TABLE inventory.inv_logistic_variable(
 id uuid PRIMARY KEY,product_id uuid NOT NULL REFERENCES inventory.inv_product(id),
 active boolean NOT NULL,principal boolean NOT NULL,purchase_factor float8,
 weight_in_gr float8,uom_id varchar,boxes_per_layer integer,pallet_layers integer,
 units_per_box integer,units_per_pallet integer,volume float8);
CREATE TABLE supply_planning.spl_supply_forecast_execution_execute_result(id uuid PRIMARY KEY);

INSERT INTO inventory.inv_product VALUES
 ('00000000-0000-0000-0000-000000000001'),('00000000-0000-0000-0000-000000000002');
INSERT INTO inventory.inv_site VALUES ('00000000-0000-0000-0000-000000000011','11');
INSERT INTO inventory.inv_product_site(id,product_id,site_id,expected_stock_days,active_for_purchase) VALUES
 ('00000000-0000-0000-0000-000000000021','00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000011',99,true),
 ('00000000-0000-0000-0000-000000000022','00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000011',99,true);
INSERT INTO inventory.inv_product_site_replenishment(product_site_id,target_coverage_days,safety_stock_days)
 VALUES('00000000-0000-0000-0000-000000000021',99,9);
INSERT INTO inventory.inv_logistic_variable(id,product_id,active,principal,purchase_factor,weight_in_gr,uom_id) VALUES
 ('00000000-0000-0000-0000-000000000031','00000000-0000-0000-0000-000000000001',true,true,1.5,2500,'kg'),
 ('00000000-0000-0000-0000-000000000032','00000000-0000-0000-0000-000000000001',true,true,4,1000,'unidad'),
 ('00000000-0000-0000-0000-000000000033','00000000-0000-0000-0000-000000000002',false,true,2,1000,'unidad');
INSERT INTO supply_planning.spl_supply_forecast_execution_execute_result VALUES ('00000000-0000-0000-0000-000000000051');
