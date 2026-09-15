# Diccionario focalizado de inventory y políticas — TEST 14/09/2026

Captura UTC: `2026-09-14T12:47:30.469323+00:00`. Fuente: [JSON de auditoría](catalogo_test_inventory_20260914.json).

Este documento describe estructura observada, no migraciones a ejecutar. Para equivalencias funcionales y brechas ver [informe 07](07_auditoria_inventory_test_20260914.md). Se conservó el diccionario histórico del 11/09.

## inventory.inv_barcode

Filas exactas: **24,586**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `barcode` | `character varying(255)` | YES | — |
| `description` | `character varying(255)` | YES | — |
| `quantity` | `double precision` | NO | — |
| `timestamp` | `timestamp without time zone` | NO | — |
| `parent_id` | `uuid` | YES | — |
| `product_id` | `uuid` | NO | — |
| `uom_id` | `character varying(255)` | NO | — |
| `barcode_type_id` | `bigint` | NO | — |
| `primary_barcode` | `boolean` | NO | `false` |
| `active` | `boolean` | NO | `true` |

### Restricciones

- `fk2wlc0pbxvgyueysg1bx8542cb`: `FOREIGN KEY (barcode_type_id) REFERENCES inventory.inv_barcode_type(id) ON DELETE RESTRICT`.
- `fk_inv_barcode_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `fknskx1xkwi8v15lapsw2djbvam`: `FOREIGN KEY (uom_id) REFERENCES inventory.inv_uom(id) ON DELETE RESTRICT`.
- `fkq5485i0o6xk3ipc2uu1m8t8rs`: `FOREIGN KEY (parent_id) REFERENCES inventory.inv_barcode(id) ON DELETE CASCADE`.
- `inv_barcode_pkey`: `PRIMARY KEY (id)`.
- `uk_61x9epwdaswyicg6is30aph94`: `UNIQUE (barcode)`.

### Índices

- `CREATE INDEX idx_inv_barcode_active ON inventory.inv_barcode USING btree (active) WHERE (active = true)`.
- `CREATE INDEX idx_inv_barcode_primary ON inventory.inv_barcode USING btree (primary_barcode) WHERE (primary_barcode = true)`.
- `CREATE UNIQUE INDEX inv_barcode_pkey ON inventory.inv_barcode USING btree (id)`.
- `CREATE INDEX ix_barcode_product_primary ON inventory.inv_barcode USING btree (product_id) WHERE primary_barcode`.
- `CREATE UNIQUE INDEX uk_61x9epwdaswyicg6is30aph94 ON inventory.inv_barcode USING btree (barcode)`.

## inventory.inv_brand

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `ext_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `manufacturer_id` | `uuid` | NO | — |

### Restricciones

- `fk_inv_brand_inv_manufacturer`: `FOREIGN KEY (manufacturer_id) REFERENCES inventory.inv_manufacturer(id) ON DELETE CASCADE`.
- `inv_brand_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_brand_ext_code`: `UNIQUE (ext_code)`.

### Índices

- `CREATE UNIQUE INDEX inv_brand_pkey ON inventory.inv_brand USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_brand_ext_code ON inventory.inv_brand USING btree (ext_code)`.

## inventory.inv_category

Filas exactas: **2,689**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `ext_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `parent_id` | `uuid` | YES | — |
| `category_type_id` | `bigint` | YES | — |
| `category_type_code` | `character varying` | YES | — |

### Restricciones

- `fk_inv_category_parent`: `FOREIGN KEY (parent_id) REFERENCES inventory.inv_category(id) ON DELETE CASCADE`.
- `inv_category_inv_category_type_fk`: `FOREIGN KEY (category_type_id) REFERENCES inventory.inv_category_type(id) ON DELETE RESTRICT`.
- `inv_category_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_category_ext_code`: `UNIQUE (ext_code)`.

### Índices

- `CREATE UNIQUE INDEX inv_category_pkey ON inventory.inv_category USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_category_ext_code ON inventory.inv_category USING btree (ext_code)`.

## inventory.inv_category_type

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `bigint` | NO | — |
| `description` | `character varying(255)` | NO | — |
| `timestamp` | `timestamp without time zone` | YES | `CURRENT_TIMESTAMP` |

### Restricciones

- `inv_category_type_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX inv_category_type_pkey ON inventory.inv_category_type USING btree (id)`.

## inventory.inv_logistic_variable

Filas exactas: **26,209**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `product_id` | `uuid` | NO | — |
| `description` | `character varying` | NO | — |
| `parent_id` | `uuid` | YES | — |
| `logistic_variable_level_id` | `bigint` | NO | — |
| `ext_code` | `character varying` | NO | — |
| `height_in_mm` | `double precision` | YES | — |
| `width_in_mm` | `double precision` | YES | — |
| `depth_in_mm` | `double precision` | YES | — |
| `weight_in_gr` | `double precision` | YES | — |
| `units` | `double precision` | YES | — |
| `barcode` | `character varying` | YES | — |
| `active` | `boolean` | NO | — |
| `principal` | `boolean` | NO | — |
| `timestamp` | `timestamp without time zone` | NO | — |
| `uom_id` | `character varying` | YES | — |
| `purchase_factor` | `double precision` | YES | — |
| `sale_factor` | `double precision` | YES | — |
| `units_per_box` | `integer` | YES | — |
| `units_per_pallet` | `integer` | YES | — |
| `pallet_layers` | `integer` | YES | — |
| `boxes_per_layer` | `integer` | YES | — |
| `gross_weight` | `double precision` | YES | — |
| `net_weight` | `double precision` | YES | — |
| `volume` | `double precision` | YES | — |
| `refrigerated` | `boolean` | NO | `false` |
| `fragile` | `boolean` | NO | `false` |
| `stackable` | `boolean` | NO | `false` |
| `shelf_life_days` | `integer` | YES | — |

### Restricciones

- `fk_inv_logistic_variable_level`: `FOREIGN KEY (logistic_variable_level_id) REFERENCES inventory.inv_logistic_variable_level(id) ON DELETE RESTRICT`.
- `fk_inv_logistic_variable_parent`: `FOREIGN KEY (parent_id) REFERENCES inventory.inv_logistic_variable(id) ON DELETE CASCADE`.
- `fk_inv_logistic_variable_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `fk_logistic_variable_barcode`: `FOREIGN KEY (barcode) REFERENCES inventory.inv_barcode(barcode) ON DELETE CASCADE`.
- `inv_logistic_variable_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE INDEX idx_inv_logistic_variable_fragile ON inventory.inv_logistic_variable USING btree (fragile) WHERE (fragile = true)`.
- `CREATE INDEX idx_inv_logistic_variable_parent_id ON inventory.inv_logistic_variable USING btree (parent_id)`.
- `CREATE INDEX idx_inv_logistic_variable_product_id ON inventory.inv_logistic_variable USING btree (product_id)`.
- `CREATE INDEX idx_inv_logistic_variable_refrigerated ON inventory.inv_logistic_variable USING btree (refrigerated) WHERE (refrigerated = true)`.
- `CREATE UNIQUE INDEX inv_logistic_variable_pkey ON inventory.inv_logistic_variable USING btree (id)`.

## inventory.inv_logistic_variable_level

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `bigint` | NO | — |
| `name` | `character varying` | NO | — |
| `parent_id` | `bigint` | YES | — |
| `timestamp` | `timestamp without time zone` | NO | — |

### Restricciones

- `fk_inv_logistic_variable_level_parent`: `FOREIGN KEY (parent_id) REFERENCES inventory.inv_logistic_variable_level(id) ON DELETE CASCADE`.
- `inv_logistic_variable_level_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX inv_logistic_variable_level_pkey ON inventory.inv_logistic_variable_level USING btree (id)`.

## inventory.inv_manufacturer

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `address` | `character varying(255)` | YES | — |
| `city` | `character varying(255)` | YES | — |
| `country` | `character varying(255)` | YES | — |
| `ext_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `state` | `character varying(255)` | YES | — |
| `tax_identification` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `zip_code` | `character varying(255)` | YES | — |
| `manufacturer_status_id` | `uuid` | NO | — |

### Restricciones

- `fk_inv_manufacturer_status`: `FOREIGN KEY (manufacturer_status_id) REFERENCES inventory.inv_manufacturer_status(id) ON DELETE RESTRICT`.
- `inv_manufacturer_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_manufacturer_ext_code`: `UNIQUE (ext_code)`.

### Índices

- `CREATE UNIQUE INDEX inv_manufacturer_pkey ON inventory.inv_manufacturer USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_manufacturer_ext_code ON inventory.inv_manufacturer USING btree (ext_code)`.

## inventory.inv_product

Filas exactas: **18,272**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `ext_code` | `character varying(255)` | YES | — |
| `sku` | `character varying(255)` | YES | — |
| `description` | `character varying(255)` | YES | — |
| `category_id` | `uuid` | YES | — |
| `status_id` | `bigint` | YES | — |
| `manufacturer_id` | `uuid` | YES | — |
| `brand_id` | `uuid` | YES | — |
| `label_uom_id` | `character varying(255)` | YES | — |
| `label_value` | `double precision` | YES | — |
| `base_price` | `double precision` | YES | — |
| `currency_id` | `bigint` | YES | — |
| `sales_uom_id` | `character varying(255)` | YES | — |
| `image` | `character varying` | YES | — |
| `sale_allowed` | `boolean` | NO | `true` |
| `is_processed` | `boolean` | NO | `false` |
| `is_raw_material` | `boolean` | NO | `false` |
| `min_days_before_expiry` | `integer` | NO | `0` |
| `batch_control` | `boolean` | NO | `false` |
| `expiration_date_control` | `boolean` | NO | `false` |
| `timestamp` | `timestamp without time zone` | NO | — |
| `internal_taxes` | `double precision` | YES | — |
| `purchase_enabled` | `boolean` | YES | — |
| `recipe_id` | `uuid` | YES | — |
| `short_description` | `character varying(500)` | YES | — |
| `weight_variable` | `boolean` | NO | `false` |
| `own_brand` | `boolean` | NO | `false` |
| `discontinued` | `boolean` | NO | `false` |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |

### Restricciones

- `fk_inv_product_brand`: `FOREIGN KEY (brand_id) REFERENCES inventory.inv_brand(id) ON DELETE SET NULL`.
- `fk_inv_product_category`: `FOREIGN KEY (category_id) REFERENCES inventory.inv_category(id) ON DELETE SET NULL`.
- `fk_inv_product_currency`: `FOREIGN KEY (currency_id) REFERENCES inventory.inv_currency(id) ON DELETE SET NULL`.
- `fk_inv_product_label_uom`: `FOREIGN KEY (label_uom_id) REFERENCES inventory.inv_uom(id) ON DELETE RESTRICT`.
- `fk_inv_product_manufacturer`: `FOREIGN KEY (manufacturer_id) REFERENCES inventory.inv_manufacturer(id) ON DELETE SET NULL`.
- `fk_inv_product_recipe`: `FOREIGN KEY (recipe_id) REFERENCES inventory.inv_recipe(id) ON DELETE SET NULL`.
- `fk_inv_product_sales_uom`: `FOREIGN KEY (sales_uom_id) REFERENCES inventory.inv_uom(id) ON DELETE RESTRICT`.
- `fk_inv_product_status`: `FOREIGN KEY (status_id) REFERENCES inventory.inv_product_status(id) ON DELETE RESTRICT`.
- `inv_product_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_product_ext_code`: `UNIQUE (ext_code)`.
- `uk_inv_product_sku`: `UNIQUE (sku)`.

### Índices

- `CREATE INDEX idx_inv_product_discontinued ON inventory.inv_product USING btree (discontinued) WHERE (discontinued = true)`.
- `CREATE INDEX idx_inv_product_own_brand ON inventory.inv_product USING btree (own_brand) WHERE (own_brand = true)`.
- `CREATE INDEX idx_inv_product_valid_dates ON inventory.inv_product USING btree (valid_from, valid_to)`.
- `CREATE INDEX idx_inv_product_weight_variable ON inventory.inv_product USING btree (weight_variable) WHERE (weight_variable = true)`.
- `CREATE UNIQUE INDEX inv_product_pkey ON inventory.inv_product USING btree (id)`.
- `CREATE INDEX ix_product_brand ON inventory.inv_product USING btree (brand_id)`.
- `CREATE INDEX ix_product_category ON inventory.inv_product USING btree (category_id)`.
- `CREATE INDEX ix_product_sku_order ON inventory.inv_product USING btree (sku, id)`.
- `CREATE INDEX ix_product_status ON inventory.inv_product USING btree (status_id)`.
- `CREATE UNIQUE INDEX uk_inv_product_ext_code ON inventory.inv_product USING btree (ext_code)`.
- `CREATE UNIQUE INDEX uk_inv_product_sku ON inventory.inv_product USING btree (sku)`.

## inventory.inv_product_classification

Filas exactas: **0**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `product_id` | `uuid` | NO | — |
| `classification_type_id` | `uuid` | NO | — |
| `classification_value` | `character varying(255)` | NO | — |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |
| `active` | `boolean` | NO | `false` |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `fk_inv_product_classification_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `fk_inv_product_classification_type`: `FOREIGN KEY (classification_type_id) REFERENCES inventory.inv_product_classification_type(id) ON DELETE RESTRICT`.
- `pk_inv_product_classification`: `PRIMARY KEY (id)`.

### Índices

- `CREATE INDEX idx_inv_product_classification_active ON inventory.inv_product_classification USING btree (active)`.
- `CREATE INDEX idx_inv_product_classification_product_id ON inventory.inv_product_classification USING btree (product_id)`.
- `CREATE INDEX idx_inv_product_classification_type_id ON inventory.inv_product_classification USING btree (classification_type_id)`.
- `CREATE UNIQUE INDEX pk_inv_product_classification ON inventory.inv_product_classification USING btree (id)`.

## inventory.inv_product_classification_type

Filas exactas: **0**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `value` | `character varying(255)` | NO | — |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `pk_inv_product_classification_type`: `PRIMARY KEY (id)`.
- `uk_inv_product_classification_type_value`: `UNIQUE (value)`.

### Índices

- `CREATE UNIQUE INDEX pk_inv_product_classification_type ON inventory.inv_product_classification_type USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_product_classification_type_value ON inventory.inv_product_classification_type USING btree (value)`.

## inventory.inv_product_commercial_policy

Filas exactas: **0**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `product_id` | `uuid` | NO | — |
| `margin_target` | `double precision` | YES | — |
| `price_sensitivity` | `character varying(100)` | YES | — |
| `promotional_enabled` | `boolean` | NO | `false` |
| `seasonal` | `boolean` | NO | `false` |
| `competition_sensitive` | `boolean` | NO | `false` |
| `pricing_strategy` | `character varying(100)` | YES | — |
| `active` | `boolean` | NO | `true` |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `fk_inv_product_commercial_policy_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `pk_inv_product_commercial_policy`: `PRIMARY KEY (id)`.
- `uk_inv_product_commercial_policy_product`: `UNIQUE (product_id)`.

### Índices

- `CREATE INDEX idx_inv_product_commercial_policy_active ON inventory.inv_product_commercial_policy USING btree (active)`.
- `CREATE UNIQUE INDEX pk_inv_product_commercial_policy ON inventory.inv_product_commercial_policy USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_product_commercial_policy_product ON inventory.inv_product_commercial_policy USING btree (product_id)`.

## inventory.inv_product_site

Filas exactas: **1,013,500**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `product_id` | `uuid` | NO | — |
| `site_id` | `uuid` | NO | — |
| `expected_stock_days` | `double precision` | NO | — |
| `created_at` | `timestamp without time zone` | YES | — |
| `min_stock_units` | `double precision` | NO | `0` |
| `max_stock_units` | `double precision` | NO | `0` |
| `active` | `boolean` | NO | `true` |
| `active_for_sale` | `boolean` | NO | `true` |
| `active_for_purchase` | `boolean` | NO | `false` |
| `active_for_transfer` | `boolean` | NO | `false` |
| `active_on_assortment` | `boolean` | NO | `false` |
| `supply_type` | `character varying(100)` | YES | — |
| `supplying_site_id` | `uuid` | YES | — |
| `shelf_capacity` | `double precision` | YES | — |
| `gondola_capacity` | `double precision` | YES | — |
| `linear_facing` | `double precision` | YES | — |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |

### Restricciones

- `fk_inv_product_site_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `fk_inv_product_site_site`: `FOREIGN KEY (site_id) REFERENCES inventory.inv_site(id) ON DELETE CASCADE`.
- `fk_inv_product_site_supplying_site`: `FOREIGN KEY (supplying_site_id) REFERENCES inventory.inv_site(id) ON DELETE SET NULL`.
- `pk_inv_product_site`: `PRIMARY KEY (id)`.
- `uk_inv_product_site_product_site`: `UNIQUE (product_id, site_id)`.

### Índices

- `CREATE INDEX idx_inv_product_site_active ON inventory.inv_product_site USING btree (active)`.
- `CREATE INDEX idx_inv_product_site_product_id ON inventory.inv_product_site USING btree (product_id)`.
- `CREATE INDEX idx_inv_product_site_site_id ON inventory.inv_product_site USING btree (site_id)`.
- `CREATE INDEX idx_inv_product_site_supplying_site_id ON inventory.inv_product_site USING btree (supplying_site_id)`.
- `CREATE INDEX ix_product_site_assortment ON inventory.inv_product_site USING btree (product_id) WHERE active_on_assortment`.
- `CREATE INDEX ix_product_site_product ON inventory.inv_product_site USING btree (product_id)`.
- `CREATE INDEX ix_product_site_product_active_for_sale ON inventory.inv_product_site USING btree (product_id) WHERE (active AND active_for_sale)`.
- `CREATE INDEX ix_product_site_site ON inventory.inv_product_site USING btree (site_id)`.
- `CREATE UNIQUE INDEX pk_inv_product_site ON inventory.inv_product_site USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_product_site_product_site ON inventory.inv_product_site USING btree (product_id, site_id)`.

## inventory.inv_product_site_assortment

Filas exactas: **0**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `product_site_id` | `uuid` | NO | — |
| `assortment_role` | `character varying(100)` | YES | — |
| `mandatory` | `boolean` | NO | `false` |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `fk_inv_product_site_assortment_product_site`: `FOREIGN KEY (product_site_id) REFERENCES inventory.inv_product_site(id) ON DELETE CASCADE`.
- `pk_inv_product_site_assortment`: `PRIMARY KEY (id)`.

### Índices

- `CREATE INDEX idx_inv_product_site_assortment_product_site_id ON inventory.inv_product_site_assortment USING btree (product_site_id)`.
- `CREATE UNIQUE INDEX pk_inv_product_site_assortment ON inventory.inv_product_site_assortment USING btree (id)`.

## inventory.inv_product_site_replenishment

Filas exactas: **852**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `product_site_id` | `uuid` | NO | — |
| `replenishment_method` | `character varying(100)` | YES | — |
| `target_coverage_days` | `double precision` | YES | — |
| `safety_stock_days` | `double precision` | YES | — |
| `minimum_order_quantity` | `double precision` | YES | — |
| `order_multiple` | `double precision` | YES | — |
| `lead_time_days` | `double precision` | YES | — |
| `preparation_days` | `double precision` | YES | — |
| `transit_days` | `double precision` | YES | — |
| `replenishment_frequency` | `character varying(100)` | YES | — |
| `active` | `boolean` | NO | `true` |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `fk_inv_product_site_replenishment_product_site`: `FOREIGN KEY (product_site_id) REFERENCES inventory.inv_product_site(id) ON DELETE CASCADE`.
- `pk_inv_product_site_replenishment`: `PRIMARY KEY (id)`.
- `uk_inv_product_site_replenishment_product_site`: `UNIQUE (product_site_id)`.

### Índices

- `CREATE INDEX idx_inv_product_site_replenishment_active ON inventory.inv_product_site_replenishment USING btree (active)`.
- `CREATE INDEX idx_inv_product_site_replenishment_product_site_id ON inventory.inv_product_site_replenishment USING btree (product_site_id)`.
- `CREATE UNIQUE INDEX pk_inv_product_site_replenishment ON inventory.inv_product_site_replenishment USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_product_site_replenishment_product_site ON inventory.inv_product_site_replenishment USING btree (product_site_id)`.

## inventory.inv_product_supplier

Filas exactas: **21,969**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `active` | `boolean` | NO | — |
| `base_price` | `double precision` | NO | — |
| `supplier_product_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | NO | — |
| `product_id` | `uuid` | NO | — |
| `supplier_id` | `uuid` | NO | — |
| `primary_supplier` | `boolean` | NO | `false` |
| `active_for_purchase` | `boolean` | NO | `false` |
| `lead_time_days` | `double precision` | YES | — |
| `minimum_purchase_quantity` | `double precision` | YES | — |
| `purchase_multiple` | `double precision` | YES | — |
| `purchase_factor` | `double precision` | YES | — |
| `cost_reference` | `double precision` | YES | — |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |

### Restricciones

- `fk_inv_product_supplier_product`: `FOREIGN KEY (product_id) REFERENCES inventory.inv_product(id) ON DELETE CASCADE`.
- `fk_inv_product_supplier_supplier`: `FOREIGN KEY (supplier_id) REFERENCES inventory.inv_supplier(id) ON DELETE CASCADE`.
- `inv_product_supplier_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_product_supplier_product_supplier`: `UNIQUE (product_id, supplier_id)`.

### Índices

- `CREATE INDEX idx_inv_product_supplier_active_for_purchase ON inventory.inv_product_supplier USING btree (active_for_purchase) WHERE (active_for_purchase = true)`.
- `CREATE INDEX idx_inv_product_supplier_primary ON inventory.inv_product_supplier USING btree (primary_supplier) WHERE (primary_supplier = true)`.
- `CREATE INDEX idx_inv_product_supplier_supplier_product_code ON inventory.inv_product_supplier USING btree (supplier_product_code)`.
- `CREATE INDEX idx_inv_product_supplier_valid_dates ON inventory.inv_product_supplier USING btree (valid_from, valid_to)`.
- `CREATE INDEX idx_supplier ON inventory.inv_product_supplier USING btree (supplier_id)`.
- `CREATE UNIQUE INDEX inv_product_supplier_pkey ON inventory.inv_product_supplier USING btree (id)`.
- `CREATE INDEX ix_prod_supplier_product_primary ON inventory.inv_product_supplier USING btree (product_id) WHERE primary_supplier`.
- `CREATE INDEX ix_prod_supplier_supplier ON inventory.inv_product_supplier USING btree (supplier_id)`.
- `CREATE UNIQUE INDEX uk_inv_product_supplier_product_supplier ON inventory.inv_product_supplier USING btree (product_id, supplier_id)`.
- `CREATE UNIQUE INDEX ux_inv_product_supplier_product_supplier ON inventory.inv_product_supplier USING btree (product_id, supplier_id)`.

## inventory.inv_set_of_site

Filas exactas: **5**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `name` | `character varying(255)` | YES | — |
| `description` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | NO | — |
| `parent_id` | `uuid` | YES | — |

### Restricciones

- `inv_set_of_site_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE INDEX idx_inv_set_of_site_parent_id ON inventory.inv_set_of_site USING btree (parent_id)`.
- `CREATE UNIQUE INDEX inv_set_of_site_pkey ON inventory.inv_set_of_site USING btree (id)`.

## inventory.inv_set_of_site_line

Filas exactas: **171**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `site_id` | `uuid` | NO | — |
| `set_of_site_id` | `uuid` | NO | — |
| `address` | `text` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `name` | `character varying` | YES | — |

### Restricciones

- `fk6b083paj7ju00fluhntnvlp72`: `FOREIGN KEY (site_id) REFERENCES inventory.inv_site(id) ON DELETE CASCADE`.
- `fkrma721a7f3dm57pccobxnnida`: `FOREIGN KEY (set_of_site_id) REFERENCES inventory.inv_set_of_site(id) ON DELETE CASCADE`.
- `pk_inv_set_of_site_line`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX pk_inv_set_of_site_line ON inventory.inv_set_of_site_line USING btree (id)`.

## inventory.inv_site

Filas exactas: **188**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `company_id` | `uuid` | YES | — |
| `code` | `character varying(255)` | NO | — |
| `name` | `character varying(255)` | NO | — |
| `latitude` | `character varying(255)` | YES | — |
| `longitude` | `character varying(255)` | YES | — |
| `address` | `text` | YES | — |
| `type` | `character varying(100)` | NO | — |
| `timestamp` | `timestamp without time zone` | YES | — |

### Restricciones

- `pk_inv_site`: `PRIMARY KEY (id)`.
- `uq_inv_site_code`: `UNIQUE (code)`.

### Índices

- `CREATE UNIQUE INDEX pk_inv_site ON inventory.inv_site USING btree (id)`.
- `CREATE UNIQUE INDEX uq_inv_site_code ON inventory.inv_site USING btree (code)`.

## inventory.inv_supplier

Filas exactas: **15,933**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `ext_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `tax_identification` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `supplier_status_id` | `uuid` | NO | — |
| `accept_return` | `boolean` | YES | `false` |
| `address` | `character varying(255)` | YES | — |
| `city` | `character varying(255)` | YES | — |
| `country` | `character varying(255)` | YES | — |
| `state` | `character varying(255)` | YES | — |
| `zip_code` | `character varying(255)` | YES | — |
| `default_contact` | `character varying(255)` | YES | — |
| `email` | `character varying(255)` | YES | — |
| `website` | `character varying(500)` | YES | — |
| `supplier_level_code` | `character varying(100)` | YES | — |
| `supplier_origin_code` | `character varying(100)` | YES | — |
| `ext_supplier_type_code` | `character varying(100)` | YES | — |
| `is_active` | `boolean` | YES | `true` |
| `legacy_created_at` | `timestamp without time zone` | YES | — |
| `legacy_disabled_at` | `timestamp without time zone` | YES | — |
| `legacy_updated_at` | `timestamp without time zone` | YES | — |

### Restricciones

- `fk_inv_supplier_supplier_status`: `FOREIGN KEY (supplier_status_id) REFERENCES inventory.inv_supplier_status(id) ON DELETE RESTRICT`.
- `inv_supplier_pkey`: `PRIMARY KEY (id)`.
- `uk_inv_supplier_ext_code`: `UNIQUE (ext_code)`.

### Índices

- `CREATE UNIQUE INDEX inv_supplier_pkey ON inventory.inv_supplier USING btree (id)`.
- `CREATE UNIQUE INDEX uk_inv_supplier_ext_code ON inventory.inv_supplier USING btree (ext_code)`.

## inventory.inv_uom

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `character varying(255)` | NO | — |
| `name` | `character varying(255)` | YES | — |
| `timestamp` | `timestamp without time zone` | YES | — |
| `uom_type_id` | `bigint` | NO | — |

### Restricciones

- `fk_inv_uom_inv_uom_type`: `FOREIGN KEY (uom_type_id) REFERENCES inventory.inv_uom_type(id) ON DELETE RESTRICT`.
- `inv_uom_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX inv_uom_pkey ON inventory.inv_uom USING btree (id)`.

## supply_planning.spl_stock_movement

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | `gen_random_uuid()` |
| `ext_code` | `character varying(255)` | YES | — |
| `date_and_time` | `date` | YES | — |
| `site_id` | `uuid` | NO | — |
| `product_id` | `uuid` | NO | — |
| `stock_movement_type_id` | `bigint` | NO | — |
| `uom_id` | `character varying(255)` | NO | — |
| `quantity` | `double precision` | NO | — |
| `status` | `character varying(255)` | NO | — |
| `timestamp` | `timestamp without time zone` | NO | `now()` |
| `custom1` | `character varying(255)` | YES | — |
| `custom2` | `character varying(255)` | YES | — |
| `custom3` | `character varying(255)` | YES | — |
| `custom4` | `character varying(255)` | YES | — |

### Restricciones

- `fk_spl_stock_movement_product`: `FOREIGN KEY (product_id) REFERENCES supply_planning.spl_product(id)`.
- `fk_spl_stock_movement_site`: `FOREIGN KEY (site_id) REFERENCES supply_planning.spl_site(id)`.
- `fk_spl_stock_movement_type`: `FOREIGN KEY (stock_movement_type_id) REFERENCES supply_planning.spl_stock_movement_type(id)`.
- `fk_spl_stock_movement_uom`: `FOREIGN KEY (uom_id) REFERENCES supply_planning.spl_uom(id)`.
- `pk_spl_stock_movement`: `PRIMARY KEY (id)`.

### Índices

- `CREATE INDEX idx_stock_movement_sales_date ON supply_planning.spl_stock_movement USING btree ("timestamp") WHERE (stock_movement_type_id = 3)`.
- `CREATE UNIQUE INDEX pk_spl_stock_movement ON supply_planning.spl_stock_movement USING btree (id)`.

## supply_planning.spl_stock_movement_type

Contenido no contado en esta auditoría.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `bigint` | NO | — |
| `ext_code` | `character varying(255)` | YES | — |
| `name` | `character varying(255)` | YES | — |
| `description` | `character varying(255)` | YES | — |
| `impact` | `integer` | YES | — |
| `overrides_existing_stock` | `character varying(255)` | YES | — |
| `created_at` | `timestamp without time zone` | NO | `now()` |

### Restricciones

- `pk_spl_stock_movement_type`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX pk_spl_stock_movement_type ON supply_planning.spl_stock_movement_type USING btree (id)`.

## supply_planning.spl_stock_policy_import_row

Filas exactas: **627**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `policy_version_id` | `uuid` | NO | — |
| `site_code` | `integer` | NO | — |
| `family_code` | `integer` | NO | — |
| `category_code` | `integer` | NO | — |
| `purchase_classification_code` | `integer` | NO | — |
| `target_stock_days` | `numeric(10,4)` | NO | — |
| `overstock_days` | `numeric(10,4)` | NO | — |
| `rule_id` | `uuid` | YES | — |
| `mapping_status` | `text` | NO | — |
| `mapping_reason` | `text` | YES | — |

### Restricciones

- `spl_stock_policy_import_row_check`: `CHECK (((mapping_status = 'MAPPED'::text) = (rule_id IS NOT NULL)))`.
- `spl_stock_policy_import_row_mapping_status_check`: `CHECK ((mapping_status = ANY (ARRAY['MAPPED'::text, 'PENDING'::text, 'EXCLUDED_CLOSED'::text])))`.
- `spl_stock_policy_import_row_overstock_days_check`: `CHECK ((overstock_days >= (0)::numeric))`.
- `spl_stock_policy_import_row_pkey`: `PRIMARY KEY (policy_version_id, site_code, family_code, category_code, purchase_classification_code)`.
- `spl_stock_policy_import_row_policy_version_id_fkey`: `FOREIGN KEY (policy_version_id) REFERENCES supply_planning.spl_stock_policy_version(id)`.
- `spl_stock_policy_import_row_rule_id_fkey`: `FOREIGN KEY (rule_id) REFERENCES supply_planning.spl_stock_policy_rule(id)`.
- `spl_stock_policy_import_row_target_stock_days_check`: `CHECK ((target_stock_days >= (0)::numeric))`.

### Índices

- `CREATE UNIQUE INDEX spl_stock_policy_import_row_pkey ON supply_planning.spl_stock_policy_import_row USING btree (policy_version_id, site_code, family_code, category_code, purchase_classification_code)`.

## supply_planning.spl_stock_policy_rule

Filas exactas: **605**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `policy_version_id` | `uuid` | NO | — |
| `site_id` | `uuid` | YES | — |
| `supply_cluster_id` | `uuid` | YES | — |
| `family_category_id` | `uuid` | NO | — |
| `category_id` | `uuid` | YES | — |
| `purchase_classification_code` | `integer` | NO | — |
| `target_stock_days` | `numeric(10,4)` | NO | — |
| `overstock_days` | `numeric(10,4)` | NO | — |
| `priority` | `integer` | NO | `0` |
| `legacy_site_code` | `integer` | YES | — |
| `legacy_family_code` | `integer` | YES | — |
| `legacy_category_code` | `integer` | YES | — |

### Restricciones

- `spl_stock_policy_rule_category_id_fkey`: `FOREIGN KEY (category_id) REFERENCES supply_planning.spl_category(id)`.
- `spl_stock_policy_rule_check`: `CHECK (((((site_id IS NOT NULL))::integer + ((supply_cluster_id IS NOT NULL))::integer) = 1))`.
- `spl_stock_policy_rule_family_category_id_fkey`: `FOREIGN KEY (family_category_id) REFERENCES supply_planning.spl_category(id)`.
- `spl_stock_policy_rule_overstock_days_check`: `CHECK ((overstock_days >= (0)::numeric))`.
- `spl_stock_policy_rule_pkey`: `PRIMARY KEY (id)`.
- `spl_stock_policy_rule_policy_version_id_fkey`: `FOREIGN KEY (policy_version_id) REFERENCES supply_planning.spl_stock_policy_version(id)`.
- `spl_stock_policy_rule_purchase_classification_code_fkey`: `FOREIGN KEY (purchase_classification_code) REFERENCES supply_planning.spl_stock_purchase_classification(code)`.
- `spl_stock_policy_rule_site_id_fkey`: `FOREIGN KEY (site_id) REFERENCES supply_planning.spl_site(id)`.
- `spl_stock_policy_rule_supply_cluster_id_fkey`: `FOREIGN KEY (supply_cluster_id) REFERENCES supply_planning.spl_supply_cluster(id)`.
- `spl_stock_policy_rule_target_stock_days_check`: `CHECK ((target_stock_days >= (0)::numeric))`.

### Índices

- `CREATE UNIQUE INDEX spl_stock_policy_rule_cluster_key ON supply_planning.spl_stock_policy_rule USING btree (policy_version_id, supply_cluster_id, family_category_id, COALESCE(category_id, '00000000-0000-0000-0000-000000000000'::uuid), purchase_classification_code) WHERE (supply_cluster_id IS NOT NULL)`.
- `CREATE UNIQUE INDEX spl_stock_policy_rule_local_key ON supply_planning.spl_stock_policy_rule USING btree (policy_version_id, site_id, family_category_id, COALESCE(category_id, '00000000-0000-0000-0000-000000000000'::uuid), purchase_classification_code) WHERE (site_id IS NOT NULL)`.
- `CREATE UNIQUE INDEX spl_stock_policy_rule_pkey ON supply_planning.spl_stock_policy_rule USING btree (id)`.

### Comentarios de columnas

- `overstock_days`: Dias adicionales para necesidad opcional S; independiente del stock de seguridad.

## supply_planning.spl_stock_policy_version

Filas exactas: **1**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `status` | `text` | NO | `'DRAFT'::text` |
| `valid_from` | `date` | YES | — |
| `valid_to` | `date` | YES | — |
| `source_system` | `text` | NO | — |
| `source_checksum` | `text` | NO | — |
| `created_at` | `timestamp with time zone` | NO | `now()` |
| `created_by` | `text` | NO | — |
| `change_reason` | `text` | NO | — |

### Restricciones

- `spl_stock_policy_version_check`: `CHECK (((valid_to IS NULL) OR (valid_to > valid_from)))`.
- `spl_stock_policy_version_check1`: `CHECK (((status = 'DRAFT'::text) OR (valid_from IS NOT NULL)))`.
- `spl_stock_policy_version_pkey`: `PRIMARY KEY (id)`.
- `spl_stock_policy_version_source_checksum_key`: `UNIQUE (source_checksum)`.
- `spl_stock_policy_version_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'PUBLISHED'::text, 'RETIRED'::text])))`.

### Índices

- `CREATE UNIQUE INDEX spl_stock_policy_version_pkey ON supply_planning.spl_stock_policy_version USING btree (id)`.
- `CREATE UNIQUE INDEX spl_stock_policy_version_source_checksum_key ON supply_planning.spl_stock_policy_version USING btree (source_checksum)`.

## supply_planning.spl_stock_purchase_classification

Filas exactas: **4**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `code` | `integer` | NO | — |
| `name` | `text` | NO | — |

### Restricciones

- `spl_stock_purchase_classification_pkey`: `PRIMARY KEY (code)`.

### Índices

- `CREATE UNIQUE INDEX spl_stock_purchase_classification_pkey ON supply_planning.spl_stock_purchase_classification USING btree (code)`.

## supply_planning.spl_supply_cluster

Filas exactas: **14**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `timestamp` | `timestamp(6) with time zone` | NO | — |
| `name` | `character varying(255)` | NO | — |

### Restricciones

- `spl_supply_cluster_pkey`: `PRIMARY KEY (id)`.
- `uk35fwwqlqltqigjl8e0l48sobo`: `UNIQUE (name)`.

### Índices

- `CREATE UNIQUE INDEX spl_supply_cluster_pkey ON supply_planning.spl_supply_cluster USING btree (id)`.
- `CREATE UNIQUE INDEX uk35fwwqlqltqigjl8e0l48sobo ON supply_planning.spl_supply_cluster USING btree (name)`.

## supply_planning.spl_supply_site

Filas exactas: **100**.

| Columna | Tipo exacto | NULL | Default |
|---|---|---|---|
| `id` | `uuid` | NO | — |
| `timestamp` | `timestamp(6) with time zone` | NO | — |
| `supply_cluster_id` | `uuid` | NO | — |
| `site_id` | `uuid` | NO | — |

### Restricciones

- `fk8e4t94u8bokf6bxpg0yjthaan`: `FOREIGN KEY (supply_cluster_id) REFERENCES supply_planning.spl_supply_cluster(id)`.
- `fkqukb34y9ns7r9donltf0b0adx`: `FOREIGN KEY (site_id) REFERENCES supply_planning.spl_site(id)`.
- `spl_supply_site_pkey`: `PRIMARY KEY (id)`.

### Índices

- `CREATE UNIQUE INDEX spl_supply_site_pkey ON supply_planning.spl_supply_site USING btree (id)`.
