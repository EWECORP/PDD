-- PostgreSQL 14+. Flyway administra la transaccion; no incluir BEGIN/COMMIT.
-- Conservar ambas columnas NULL significa todas las categorias.
ALTER TABLE supply_planning.spl_stock_policy_rule
    ALTER COLUMN family_category_id DROP NOT NULL;

ALTER TABLE supply_planning.spl_stock_policy_rule
    ADD CONSTRAINT ck_stock_policy_category_requires_family
    CHECK (category_id IS NULL OR family_category_id IS NOT NULL),
    ADD CONSTRAINT ck_stock_policy_nonzero_category_ids
    CHECK (
        (family_category_id IS NULL OR family_category_id <> '00000000-0000-0000-0000-000000000000'::uuid)
        AND (category_id IS NULL OR category_id <> '00000000-0000-0000-0000-000000000000'::uuid)
    ),
    ADD CONSTRAINT uq_stock_policy_rule_version_id UNIQUE (policy_version_id,id);

-- Recrear indices corrige la semantica NULL de PostgreSQL 14.
-- Un duplicado existente provoca rollback de la migracion; no se elimina informacion.
DROP INDEX supply_planning.spl_stock_policy_rule_local_key;
DROP INDEX supply_planning.spl_stock_policy_rule_cluster_key;

CREATE UNIQUE INDEX spl_stock_policy_rule_local_key
ON supply_planning.spl_stock_policy_rule (
    policy_version_id,site_id,
    COALESCE(family_category_id,'00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(category_id,'00000000-0000-0000-0000-000000000000'::uuid),
    purchase_classification_code
) WHERE site_id IS NOT NULL;

CREATE UNIQUE INDEX spl_stock_policy_rule_cluster_key
ON supply_planning.spl_stock_policy_rule (
    policy_version_id,supply_cluster_id,
    COALESCE(family_category_id,'00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(category_id,'00000000-0000-0000-0000-000000000000'::uuid),
    purchase_classification_code
) WHERE supply_cluster_id IS NOT NULL;

ALTER TABLE supply_planning.spl_stock_policy_import_row
    ADD CONSTRAINT fk_stock_policy_import_same_version
    FOREIGN KEY (policy_version_id,rule_id)
    REFERENCES supply_planning.spl_stock_policy_rule(policy_version_id,id);

ALTER TABLE supply_planning.spl_stock_policy_version
    ADD CONSTRAINT ck_stock_policy_validity_bounds
    CHECK (valid_to IS NULL OR (valid_from IS NOT NULL AND valid_to > valid_from));

CREATE INDEX spl_stock_policy_rule_category_idx
    ON supply_planning.spl_stock_policy_rule(family_category_id,category_id);
CREATE INDEX spl_stock_policy_import_rule_idx
    ON supply_planning.spl_stock_policy_import_row(rule_id);

COMMENT ON COLUMN supply_planning.spl_stock_policy_rule.family_category_id IS
'NULL junto con category_id NULL: todas las categorias. Familia sin rubro: todos los rubros de la familia. Clasificacion de compra sigue siendo obligatoria.';
COMMENT ON COLUMN supply_planning.spl_stock_policy_rule.category_id IS
'Rubro especifico; requiere familia. La aplicacion valida parent_id contra la familia seleccionada.';
COMMENT ON COLUMN supply_planning.spl_stock_policy_rule.priority IS
'Reservado para compatibilidad. Resolucion: LOCAL antes de GRUPO; dentro del ambito RUBRO antes de FAMILIA antes de GENERAL. No altera esta precedencia.';
