# PDD - Última calibración inicial y publicación en Test

Fecha: 2026-08-14  
Backend: `diarco-pdd-backend 0.6.1`

## Objetivo

Realizar una última comparación controlada de los siete estimadores y cerrar la
calibración inicial. La publicación del PDVB v3 en Test se mantiene desacoplada
de esa decisión para que el equipo frontend pueda trabajar con entidades reales
desde ahora. Una mejora futura emitirá otra versión de modelo y reemplazará la
proyección vigente sin cambiar el contrato de tablas.

## 1. Instalación y contrato operativo

```bash
cd /srv/PDD/backend
source /srv/FORECAST/venv/bin/activate
export PDD_ENV_PATH=/srv/PDD/backend/.env
python -m pip install -e .
python tools/validate_sql.py
```

Primero inspeccionar `connexa_platform_test`:

```sql
SELECT
    to_regclass('stock_management.item_logistics_snapshot') AS nombre_anterior,
    to_regclass('stock_management.pdd_item_logistics_snapshot') AS nombre_pdd;
```

- Si las tablas PDD todavía no existen, ejecutar los DDL Core y DECAS vigentes,
  luego v2.4 y v2.5; esos archivos ya crean/referencian nombres `pdd_*`.
- Si existen con nombres sin prefijo, aplicar v2.6. Esta conserva filas, claves
  y relaciones.
- No volver a ejecutar v2.4/v2.5 si ya figuran exitosas en el historial de
  migraciones.

Comando de v2.6, cuando corresponda, siempre con `ON_ERROR_STOP`:

```bash
psql -v ON_ERROR_STOP=1 \
  -h 186.158.182.223 -d connexa_platform_test \
  -f "/srv/PDD/PDD - Migracion Operativa Prefijo PDD v2.6.sql"
```

La migración renombra una instalación previa; no copia ni elimina filas. En una
instalación nueva actúa como control idempotente una vez creados los DDL base.

Variables adicionales en `/srv/PDD/backend/.env`:

```text
PDD_DB_STATEMENT_TIMEOUT_MS=1800000
PDD_DB_KEEPALIVES_IDLE_SECONDS=60
PDD_DB_KEEPALIVES_INTERVAL_SECONDS=30
PDD_DB_KEEPALIVES_COUNT=5

PDD_OPERATIONAL_PG_HOST=186.158.182.223
PDD_OPERATIONAL_PG_PORT=5432
PDD_OPERATIONAL_PG_DB=connexa_platform_test
PDD_OPERATIONAL_PG_USER=...
PDD_OPERATIONAL_PG_PASSWORD=...
PDD_OPERATIONAL_ALLOW_PRODUCTION=false
```

Desplegar nuevamente los flows:

```bash
prefect deploy --all
systemctl restart prefect-worker-pdd.service
python tools/validate_operational.py
```

## 2. Corrida final de calibración

Se evalúa un horizonte acumulado de siete días sobre siete orígenes. Es una
sola corrida estadística y compara la misma cohorte entre estimadores. La
muestra determinística selecciona aproximadamente 25% de los artículos y todas
sus sucursales mediante un hash estable; los siete estimadores ven exactamente
los mismos casos en todos los orígenes:

```bash
pdd-etl rolling-backtest \
  --origin-from 2026-07-08 \
  --origin-to 2026-07-14 \
  --horizon 7 \
  --mode CUMULATIVE \
  --actual-min-coverage 0.70 \
  --sample-percent 25 \
  --scope-version-uuid 90dcd987-2ad6-4e4e-8d19-2ead45775d1f \
  --model-version-uuid a0a35b25-628d-43f1-b651-82c97207fc60
```

El detalle de cada origen tiene un límite de 30 minutos. El log debe mostrar
por separado `pdvb=...s` y `detalle=...s`. Si se supera el límite, PostgreSQL
cancela la sentencia y la corrida queda `FAILED`; no queda una consulta huérfana
indefinida ni detalle parcial confirmado.

## 3. Controles y decisión

```sql
SELECT calculation_run_uuid, status, evaluation_mode,
       completed_origin_count, origin_count,
       estimate_row_count, detail_row_count, metric_row_count,
       completed_at - started_at AS duracion, error_message
FROM datamart.dm_pdd_pdvb_backtest_run
ORDER BY started_at DESC
LIMIT 1;

SELECT estimator_code,
       max(metric_value) FILTER (WHERE metric_code = 'MAE') AS mae,
       max(metric_value) FILTER (WHERE metric_code = 'WAPE') AS wape_pct,
       max(metric_value) FILTER (WHERE metric_code = 'BIAS') AS bias_pct,
       max(metric_value) FILTER (WHERE metric_code = 'RMSE') AS rmse,
       max(sample_size) AS muestra,
       max(prediction_count) AS predicciones,
       max(expected_count) AS esperadas
FROM datamart.dm_pdd_pdvb_backtest_metric
WHERE calculation_run_uuid = 'UUID_CORRIDA_FINAL'
  AND evaluation_mode = 'CUMULATIVE'
  AND sample_code = 'COMMON_VALID'
  AND segment_type = 'ALL'
  AND segment_id = 'ALL'
GROUP BY estimator_code
ORDER BY wape_pct, mae;

-- Las fechas de las ventanas pertenecen a la estimacion PDVB. El detalle de
-- backtest conserva su linaje mediante forecast_calculation_run_uuid.
-- DISTINCT evita contar siete veces la misma estimacion por los estimadores
-- comparados en el backtest.
WITH forecast_runs AS (
    SELECT DISTINCT
        forecast_calculation_run_uuid,
        forecast_origin_date
    FROM datamart.dm_pdd_pdvb_backtest_detail
    WHERE calculation_run_uuid = 'UUID_CORRIDA_FINAL'
),
estimaciones_controladas AS (
    SELECT
        f.forecast_origin_date,
        e.lookback_end,
        e.recent_end,
        e.previous_end,
        e.seasonal_end
    FROM forecast_runs AS f
    INNER JOIN datamart.dm_pdd_pdvb_estimate_detail AS e
        ON e.calculation_run_uuid = f.forecast_calculation_run_uuid
       AND e.business_date = f.forecast_origin_date
)
SELECT
    count(*) AS estimaciones_controladas,
    count(*) FILTER (
        WHERE lookback_end >= forecast_origin_date
    ) AS fuga_lookback,
    count(*) FILTER (
        WHERE recent_end >= forecast_origin_date
    ) AS fuga_reciente,
    count(*) FILTER (
        WHERE previous_end >= forecast_origin_date
    ) AS fuga_anterior,
    count(*) FILTER (
        WHERE seasonal_end >= forecast_origin_date
    ) AS fuga_estacional
FROM estimaciones_controladas;
```

Criterio inicial de decisión:

- comparar primero `COMMON_VALID`, nunca muestras diferentes;
- exigir cero fugas temporales y corrida completa;
- priorizar menor WAPE y MAE;
- usar BIAS como restricción: se prefiere `abs(BIAS) <= 10%`;
- si la mejora de WAPE frente a PDVB es menor a 2%, conservar PDVB v3 por
  estabilidad;
- revisar que la mejora general no deteriore en más de 5% relativo los segmentos
  `INTERMITTENT` y `LUMPY`;
- no promover automáticamente un benchmark. Si gana, se documentará luego como
  modelo v4 con UUID y manifiesto nuevos.

Con esta evaluación se cierra la calibración inicial. No se agregan más
estimadores en esta etapa.

### Resultado de la calibración inicial

Corrida final: `0df43340-288d-4071-8083-47d1cfd88c3f`.

- estado `COMPLETED`, con 7 de 7 orígenes y una duración de 9 minutos 8 segundos;
- 361.102 estimaciones, 613.088 observaciones de detalle y 8.476 métricas;
- 361.102 estimaciones controladas sin fuga en `lookback`, ventana reciente,
  anterior ni estacional;
- en `COMMON_VALID/ALL`, `MEAN_28` redujo WAPE de 86,93% a 84,03% y
  MAE de 9,99 a 9,65; su BIAS fue 0,18%;
- en `INTERMITTENT`, `MEAN_28` redujo WAPE de 101,56% a 94,73%;
- en `LUMPY`, `MEAN_28` redujo WAPE de 97,09% a 94,63%;
- `MEAN_28` queda seleccionado como candidato para un modelo v4, pero no
  reemplaza silenciosamente al modelo v3 ni modifica esta publicación;
- el aumento de RMSE de `MEAN_28`, especialmente en `LUMPY`, queda registrado
  como riesgo de errores extremos para monitorear en una calibración posterior.

La calibración inicial queda cerrada. La siguiente actividad es publicar en
Test el snapshot PDVB v3 ya validado para liberar el contrato de datos al
frontend.

## 4. Publicación para liberar al frontend

El snapshot PDVB v3 validado del 2026-08-12 puede publicarse aunque el modelo
siga en estado `DRAFT`, porque el destino es Test y la corrida queda identificada
como `TEST_PILOT`:

```bash
pdd-etl publish-pdvb \
  --calculation-run-uuid 34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77 \
  --created-by eduardo.ettlin
```

Controles en `connexa_platform_test`:

```sql
SELECT calculation_run_uuid, business_date, status, is_current,
       output_row_count, warning_count, finished_at
FROM stock_management.pdd_calculation_run
WHERE calculation_run_uuid = '34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77';

SELECT status, count(*) AS registros
FROM stock_management.pdd_pdvb_estimate
WHERE calculation_run_id = (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE calculation_run_uuid = '34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77'
)
GROUP BY status
ORDER BY status;

SELECT count(*) AS pdvb_vigentes,
       count(DISTINCT codigo_articulo) AS articulos,
       count(DISTINCT sucursal) AS sucursales,
       min(business_date) AS fecha_min,
       max(business_date) AS fecha_max
FROM stock_management.pdd_pdvb_current
WHERE origin_cd = 41;

SELECT severity, issue_code, count(*) AS incidencias
FROM stock_management.pdd_pdvb_quality_issue
WHERE calculation_run_id = (
    SELECT calculation_run_id
    FROM stock_management.pdd_calculation_run
    WHERE calculation_run_uuid = '34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77'
)
GROUP BY severity, issue_code;
```

Resultados esperados para ese snapshot: 51.586 estimaciones históricas, 43.675
filas vigentes no bloqueadas y 7.911 incidencias `PDVB_INSUFFICIENT_DATA`.
Los controles deben calcularse igualmente desde las tablas y no depender de
esos valores como constantes de aplicación.

### Resultado de la primera publicación en Test

Publicación completada el 2026-08-14:

- flow run Prefect: `5e59ed6d-d461-4bc3-b3d4-edd19acc3a27`;
- corrida PDVB: `34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77`;
- lote: `42183719-db6f-4aaa-9750-bdfa97b3f2b4`;
- estado de corrida `SUCCEEDED`, vigente y sin errores;
- estado del lote `PUBLISHED`, con 51.586 filas esperadas, preparadas y
  publicadas;
- checksum de origen y staging coincidente;
- historia: 29.328 `OK`, 10.928 `WARN`, 3.419 `ZERO_VALID` y 7.911
  `BLOCKED`;
- snapshot vigente: 43.675 filas utilizables;
- calidad: 7.911 incidencias `WARN/PDVB_INSUFFICIENT_DATA`.

El contrato PDVB en `connexa_platform_test.stock_management.pdd_*` queda
validado y disponible para integración con el frontend.
