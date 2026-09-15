-- MANUAL, SOLO TEST. No incluir este archivo en las locations de Flyway.
-- Datos de esta tabla confirmados como prueba por el usuario. No regenera valores.
BEGIN;
SET LOCAL lock_timeout = '10s';
DO $$
BEGIN
  IF current_database() <> 'connexa_platform_test' THEN
    RAISE EXCEPTION 'Reset autorizado solo en connexa_platform_test';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
      WHERE table_schema='inventory' AND table_name='inv_product_site_replenishment'
      AND column_name='safety_stock_days') THEN
    RAISE EXCEPTION 'Reset solo sobre estructura anterior a la nivelacion';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE contype='f'
      AND confrelid='inventory.inv_product_site_replenishment'::regclass) THEN
    RAISE EXCEPTION 'Existen FK entrantes: revisar antes de borrar datos de prueba';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_trigger WHERE NOT tgisinternal
      AND tgrelid='inventory.inv_product_site_replenishment'::regclass) THEN
    RAISE EXCEPTION 'Existen triggers nuevos: revisar sus efectos antes del reset';
  END IF;
END $$;
LOCK TABLE inventory.inv_product_site_replenishment IN ACCESS EXCLUSIVE MODE;
DELETE FROM inventory.inv_product_site_replenishment;
COMMIT;
