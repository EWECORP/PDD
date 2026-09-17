-- PostgreSQL 14+. Incorporar al historial Flyway de inventory.
-- Flyway administra la transaccion. No ejecutar contra estructuras ya migradas.
-- El usuario confirmo que las asignaciones existentes son pruebas descartables.
-- Fuera de TEST solo admite la tabla de asignaciones vacia.
SET LOCAL lock_timeout = '10s';
LOCK TABLE inventory.inv_product_classification_type IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE inventory.inv_product_classification IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM inventory.inv_product_classification)
       AND current_database() <> 'connexa_platform_test' THEN
        RAISE EXCEPTION 'Hay clasificaciones existentes fuera de TEST; requiere migracion de datos especifica';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint
        WHERE contype='f' AND confrelid='inventory.inv_product_classification'::regclass) THEN
        RAISE EXCEPTION 'Existen referencias a asignaciones: revisar antes de eliminar pruebas';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_trigger
        WHERE tgrelid='inventory.inv_product_classification'::regclass AND NOT tgisinternal) THEN
        RAISE EXCEPTION 'Existen triggers de aplicacion no contemplados: revisar efectos del borrado';
    END IF;
END $$;

-- Sin CASCADE. Conserva productos y tipos existentes, incluidos Compra y Venta.
DELETE FROM inventory.inv_product_classification;

CREATE TABLE inventory.inv_product_classification_value (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    classification_type_id uuid NOT NULL
        REFERENCES inventory.inv_product_classification_type(id) ON DELETE RESTRICT,
    code varchar(50) NOT NULL,
    description varchar(255) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_inv_classification_value_code UNIQUE(classification_type_id,code),
    CONSTRAINT uq_inv_classification_value_type UNIQUE(id,classification_type_id),
    CONSTRAINT ck_inv_classification_value_code CHECK(code=btrim(code) AND code<>''),
    CONSTRAINT ck_inv_classification_value_description CHECK(btrim(description)<>'')
);

ALTER TABLE inventory.inv_product_classification
    DROP COLUMN classification_value,
    ADD COLUMN classification_value_id uuid NOT NULL,
    ALTER COLUMN active SET DEFAULT true,
    ALTER COLUMN valid_from SET DEFAULT CURRENT_DATE,
    ALTER COLUMN valid_from SET NOT NULL,
    ADD CONSTRAINT fk_inv_classification_value_same_type
        FOREIGN KEY(classification_value_id,classification_type_id)
        REFERENCES inventory.inv_product_classification_value(id,classification_type_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT ck_inv_classification_validity
        CHECK(isfinite(valid_from) AND
            (valid_to IS NULL OR (isfinite(valid_to) AND valid_to>valid_from)));

CREATE INDEX ix_inv_classification_value_assignment
    ON inventory.inv_product_classification(classification_value_id,classification_type_id);
CREATE INDEX ix_inv_classification_product_type_validity
    ON inventory.inv_product_classification(product_id,classification_type_id,valid_from,valid_to)
    WHERE active;

-- Catalogo DIARCO; no asigna clases a productos ni convierte faltantes en 100.
INSERT INTO inventory.inv_product_classification_type(value)
VALUES ('Clasificación Compra') ON CONFLICT(value) DO NOTHING;

INSERT INTO inventory.inv_product_classification_value(classification_type_id,code,description)
SELECT t.id,v.code,v.description
FROM inventory.inv_product_classification_type t
CROSS JOIN (VALUES
    ('1','Sensibles'),
    ('2','Resto Top'),
    ('3','Variedad Extra'),
    ('4','A Remover'),
    ('5','Sin Venta'),
    ('6','Sensibles PM'),
    ('100','Sin Clasificar')
) AS v(code,description)
WHERE t.value='Clasificación Compra';

COMMENT ON TABLE inventory.inv_product_classification_value IS
    'Opciones permitidas por tipo de clasificacion. Codigo estable separado de descripcion; no es asignacion a producto.';
COMMENT ON COLUMN inventory.inv_product_classification.classification_type_id IS
    'Tipo conservado para consultas; FK compuesta garantiza que coincide con el tipo del valor seleccionado.';
COMMENT ON COLUMN inventory.inv_product_classification.classification_value_id IS
    'Valor de catalogo asignado al producto. Reemplaza texto libre classification_value.';
COMMENT ON COLUMN inventory.inv_product_classification.valid_to IS
    'Fin exclusivo de vigencia [valid_from,valid_to); NULL indica sin fin.';
COMMENT ON COLUMN inventory.inv_product_classification_value.active IS
    'Disponible para nuevas asignaciones. Desactivarlo no borra ni invalida retroactivamente la historia; servicio valida al asignar.';
