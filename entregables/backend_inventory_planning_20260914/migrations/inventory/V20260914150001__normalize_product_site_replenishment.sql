-- PostgreSQL 14+. Flyway transaccional, historial inventory.
-- Requiere tabla vacia; el reset de TEST es un paso separado y explicito.
SET LOCAL lock_timeout = '10s';
LOCK TABLE inventory.inv_product_site_replenishment IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM inventory.inv_product_site_replenishment) THEN
    RAISE EXCEPTION 'Replenishment debe estar vacia: no convertir safety_stock_days a overstock_days';
  END IF;
END $$;

ALTER TABLE inventory.inv_product_site_replenishment
  DROP COLUMN target_coverage_days,
  DROP COLUMN safety_stock_days,
  ADD COLUMN target_stock_days numeric(10,4) NOT NULL,
  ADD COLUMN overstock_days numeric(10,4) NOT NULL,
  ALTER COLUMN minimum_order_quantity TYPE numeric(18,4) USING minimum_order_quantity::numeric(18,4),
  ALTER COLUMN minimum_order_quantity SET NOT NULL,
  ALTER COLUMN order_multiple TYPE numeric(18,4) USING order_multiple::numeric(18,4),
  ALTER COLUMN preparation_days TYPE numeric(10,4) USING preparation_days::numeric(10,4),
  ALTER COLUMN preparation_days SET NOT NULL,
  ALTER COLUMN lead_time_days TYPE numeric(10,4) USING lead_time_days::numeric(10,4),
  ALTER COLUMN transit_days TYPE numeric(10,4) USING transit_days::numeric(10,4),
  ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'UTC',
  ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN updated_by text NOT NULL,
  ADD COLUMN row_version bigint NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_inv_replenishment_days CHECK (
    target_stock_days >= 0 AND target_stock_days < 'Infinity'::numeric
    AND overstock_days >= 0 AND overstock_days < 'Infinity'::numeric
    AND preparation_days >= 0 AND preparation_days < 'Infinity'::numeric),
  ADD CONSTRAINT ck_inv_replenishment_optional_days CHECK (
    (lead_time_days IS NULL OR (lead_time_days >= 0 AND lead_time_days < 'Infinity'::numeric))
    AND (transit_days IS NULL OR (transit_days >= 0 AND transit_days < 'Infinity'::numeric))),
  ADD CONSTRAINT ck_inv_replenishment_quantities CHECK (
    minimum_order_quantity >= 0 AND minimum_order_quantity < 'Infinity'::numeric
    AND (order_multiple IS NULL OR (order_multiple > 0 AND order_multiple < 'Infinity'::numeric))),
  ADD CONSTRAINT ck_inv_replenishment_revision CHECK (row_version > 0),
  ADD CONSTRAINT ck_inv_replenishment_actor CHECK (btrim(updated_by) <> '');

COMMENT ON TABLE inventory.inv_product_site_replenishment IS
  'Fuente unica actual de parametros por articulo/local para PDD y FORECAST; no consume reglas de grupo.';
COMMENT ON COLUMN inventory.inv_product_site_replenishment.target_stock_days IS
  'Dias objetivo de necesidad obligatoria. Obligatorio, finito, decimal no negativo; cero explicito valido.';
COMMENT ON COLUMN inventory.inv_product_site_replenishment.overstock_days IS
  'Dias adicionales para necesidad opcional. No representa stock de seguridad.';
COMMENT ON COLUMN inventory.inv_product_site_replenishment.minimum_order_quantity IS
  'Minimo por articulo/local en unidad base; cero explicito significa sin minimo. Independiente del minimo de proveedor.';
COMMENT ON COLUMN inventory.inv_product_site_replenishment.order_multiple IS
  'Multiplo por articulo/local en unidad base, si se configura. NULL no impone multiplo; no reemplaza factor de empaque.';
COMMENT ON COLUMN inventory.inv_product_site_replenishment.preparation_days IS
  'Dias de preparacion. Obligatorio, cero explicito valido; no es sinonimo de lead_time_days.';
COMMENT ON COLUMN inventory.inv_product_site.expected_stock_days IS
  'Campo legacy de otros consumidores. PDD/FORECAST usan inv_product_site_replenishment.target_stock_days sin fallback ni doble edicion.';

CREATE TABLE inventory.inv_planning_parameter_audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entity_name text NOT NULL,
  entity_key uuid NOT NULL,
  operation text NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
  actor text NOT NULL CHECK (btrim(actor) <> ''),
  changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  old_value jsonb,
  new_value jsonb
);
CREATE INDEX ix_inv_planning_audit_entity ON inventory.inv_planning_parameter_audit(entity_name,entity_key,id);

CREATE FUNCTION inventory.inv_planning_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actor text := nullif(btrim(current_setting('app.actor',true)), '');
BEGIN
  IF actor IS NULL THEN
    RAISE EXCEPTION 'Configurar app.actor en la transaccion de mantenimiento';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  IF TG_OP = 'UPDATE' THEN
    IF TG_TABLE_NAME = 'inv_product_site_replenishment' THEN
      IF NEW.id <> OLD.id OR NEW.product_site_id <> OLD.product_site_id THEN
        RAISE EXCEPTION 'No cambiar identidad/par; eliminar y crear otra configuracion';
      END IF;
    ELSE
      IF NEW.product_id <> OLD.product_id THEN RAISE EXCEPTION 'No cambiar producto de seleccion'; END IF;
    END IF;
    NEW.row_version := OLD.row_version + 1;
    NEW.created_at := OLD.created_at;
  ELSE
    NEW.row_version := 1;
    NEW.created_at := clock_timestamp();
  END IF;
  NEW.updated_at := clock_timestamp();
  NEW.updated_by := actor;
  RETURN NEW;
END $$;

CREATE FUNCTION inventory.inv_planning_audit_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE old_doc jsonb; new_doc jsonb; doc jsonb; key_value uuid;
BEGIN
  IF TG_OP <> 'INSERT' THEN old_doc := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN new_doc := to_jsonb(NEW); END IF;
  doc := coalesce(new_doc,old_doc);
  key_value := (CASE WHEN TG_TABLE_NAME='inv_product_site_replenishment'
    THEN doc->>'id' ELSE doc->>'product_id' END)::uuid;
  INSERT INTO inventory.inv_planning_parameter_audit(entity_name,entity_key,operation,actor,old_value,new_value)
  VALUES(TG_TABLE_NAME,key_value,TG_OP,current_setting('app.actor'),old_doc,new_doc);
  RETURN NULL;
END $$;

CREATE FUNCTION inventory.inv_planning_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Auditoria append-only'; END $$;
CREATE TRIGGER tr_inv_planning_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
  ON inventory.inv_planning_parameter_audit FOR EACH STATEMENT EXECUTE FUNCTION inventory.inv_planning_audit_immutable();
CREATE TRIGGER tr_inv_replenishment_stamp BEFORE INSERT OR UPDATE OR DELETE
  ON inventory.inv_product_site_replenishment FOR EACH ROW EXECUTE FUNCTION inventory.inv_planning_stamp();
CREATE TRIGGER tr_inv_replenishment_audit AFTER INSERT OR UPDATE OR DELETE
  ON inventory.inv_product_site_replenishment FOR EACH ROW EXECUTE FUNCTION inventory.inv_planning_audit_write();
