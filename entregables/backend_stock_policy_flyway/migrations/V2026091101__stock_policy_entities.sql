-- Integrar con el siguiente numero disponible en el historial Flyway del backend.
-- Compatible con el borrador creado manualmente en TEST. No carga datos legacy.
-- TEST: políticas de stock. La tabla dummy se conserva como antecedente.
-- No publica versiones ni cambia el lector de PDD.
CREATE TABLE IF NOT EXISTS supply_planning.spl_stock_policy_version (
 id uuid PRIMARY KEY,
 status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
 valid_from date,
 valid_to date,
 source_system text NOT NULL,
 source_checksum text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 created_by text NOT NULL,
 change_reason text NOT NULL,
 CHECK (valid_to IS NULL OR valid_to > valid_from),
 CHECK (status = 'DRAFT' OR valid_from IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS supply_planning.spl_stock_purchase_classification (
 code integer PRIMARY KEY,
 name text NOT NULL
);

CREATE TABLE IF NOT EXISTS supply_planning.spl_stock_policy_rule (
 id uuid PRIMARY KEY,
 policy_version_id uuid NOT NULL REFERENCES supply_planning.spl_stock_policy_version(id),
 site_id uuid REFERENCES supply_planning.spl_site(id),
 supply_cluster_id uuid REFERENCES supply_planning.spl_supply_cluster(id),
 family_category_id uuid NOT NULL REFERENCES supply_planning.spl_category(id),
 category_id uuid REFERENCES supply_planning.spl_category(id),
 purchase_classification_code integer NOT NULL REFERENCES supply_planning.spl_stock_purchase_classification(code),
 target_stock_days numeric(10,4) NOT NULL CHECK (target_stock_days >= 0),
 overstock_days numeric(10,4) NOT NULL CHECK (overstock_days >= 0),
 priority integer NOT NULL DEFAULT 0,
 legacy_site_code integer,
 legacy_family_code integer,
 legacy_category_code integer,
 CHECK ((site_id IS NOT NULL)::integer + (supply_cluster_id IS NOT NULL)::integer = 1)
);
CREATE UNIQUE INDEX IF NOT EXISTS spl_stock_policy_rule_local_key
 ON supply_planning.spl_stock_policy_rule
 (policy_version_id,site_id,family_category_id,COALESCE(category_id,'00000000-0000-0000-0000-000000000000'::uuid),purchase_classification_code)
 WHERE site_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS spl_stock_policy_rule_cluster_key
 ON supply_planning.spl_stock_policy_rule
 (policy_version_id,supply_cluster_id,family_category_id,COALESCE(category_id,'00000000-0000-0000-0000-000000000000'::uuid),purchase_classification_code)
 WHERE supply_cluster_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS supply_planning.spl_stock_policy_import_row (
 policy_version_id uuid NOT NULL REFERENCES supply_planning.spl_stock_policy_version(id),
 site_code integer NOT NULL,
 family_code integer NOT NULL,
 category_code integer NOT NULL,
 purchase_classification_code integer NOT NULL,
 target_stock_days numeric(10,4) NOT NULL CHECK (target_stock_days >= 0),
 overstock_days numeric(10,4) NOT NULL CHECK (overstock_days >= 0),
 rule_id uuid REFERENCES supply_planning.spl_stock_policy_rule(id),
 mapping_status text NOT NULL CHECK (mapping_status IN ('MAPPED','PENDING','EXCLUDED_CLOSED')),
 mapping_reason text,
 PRIMARY KEY (policy_version_id,site_code,family_code,category_code,purchase_classification_code),
 CHECK ((mapping_status='MAPPED') = (rule_id IS NOT NULL))
);
COMMENT ON TABLE supply_planning.spl_stock_policy_rule IS
 'Politica de cobertura: local o grupo, familia, rubro opcional y clasificacion. Rubro NULL aplica a toda la familia. Sustituye conceptualmente las reglas dummy de spl_supply_cluster_category.';
COMMENT ON COLUMN supply_planning.spl_stock_policy_rule.overstock_days IS
 'Dias adicionales para necesidad opcional S; independiente del stock de seguridad.';
