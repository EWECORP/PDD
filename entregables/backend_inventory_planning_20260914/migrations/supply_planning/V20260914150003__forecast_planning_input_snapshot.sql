-- Historial Flyway supply_planning, despues de las dos migraciones inventory.
-- Aditiva: no modifica resultados historicos, ventanas enteras ni forcast/forecast legacy.
CREATE TABLE supply_planning.spl_forecast_planning_input (
  result_id uuid PRIMARY KEY REFERENCES supply_planning.spl_supply_forecast_execution_execute_result(id) ON DELETE RESTRICT,
  replenishment_id uuid NOT NULL,
  replenishment_row_version bigint NOT NULL CHECK(replenishment_row_version > 0),
  target_stock_days numeric(10,4) NOT NULL,
  overstock_days numeric(10,4) NOT NULL,
  preparation_days numeric(10,4) NOT NULL,
  logistic_variable_id uuid NOT NULL,
  logistics_selection_row_version bigint NOT NULL CHECK(logistics_selection_row_version > 0),
  supplying_site_id uuid,
  supplying_site_code text,
  captured_at timestamptz NOT NULL,
  input_snapshot jsonb NOT NULL CHECK(jsonb_typeof(input_snapshot)='object'),
  CONSTRAINT ck_spl_forecast_planning_days CHECK (
    target_stock_days >= 0 AND target_stock_days < 'Infinity'::numeric
    AND overstock_days >= 0 AND overstock_days < 'Infinity'::numeric
    AND preparation_days >= 0 AND preparation_days < 'Infinity'::numeric)
);
COMMENT ON TABLE supply_planning.spl_forecast_planning_input IS
  'Entrada congelada por resultado del nuevo publicador. UUID inventory son referencias historicas sin FK; snapshot conserva todos los valores efectivos y su procedencia. No reconstruir desde el maestro actual.';
CREATE FUNCTION supply_planning.spl_forecast_planning_input_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Entrada forecast inmutable: crear nuevo resultado para otra revision'; END $$;
CREATE TRIGGER tr_spl_forecast_planning_input_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
  ON supply_planning.spl_forecast_planning_input FOR EACH STATEMENT
  EXECUTE FUNCTION supply_planning.spl_forecast_planning_input_immutable();
