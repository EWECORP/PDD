# Backend analítico PDD

Primera implementación de las entidades pesadas alojadas en
`diarco_data.datamart`:

- `dm_pdd_scope_version`;
- `dm_pdd_scope_article`;
- `dm_pdd_scope_pair`;
- `dm_pdd_stock_diario`;
- `dm_pdd_venta_diaria`;
- `dm_pdd_pdvb_estimate_detail`;
- `dm_pdd_pdvb_backtest_detail`.

## Decisión de ejecución

El backend comparte Python, dependencias, Prefect Server y worker con FORECAST,
pero es un paquete separado. Los flows llaman tareas Python nativas; no lanzan
scripts mediante `subprocess`.

Los cálculos masivos se ejecutan con SQL set-based en PostgreSQL. Python se
limita a configuración, transacciones, ventanas, particiones y orquestación.

## Configuración

Se buscan variables en este orden:

1. archivo indicado por `PDD_ENV_PATH`;
2. archivo indicado por `FORECAST_ENV_PATH`;
3. `../FORECAST/.env` en el workspace de desarrollo;
4. `/srv/FORECAST/forecast_core/.env` o `/srv/FORECAST/.env`.

Las variables `PG_*` deben apuntar a `diarco_data`. No se registran contraseñas
en logs.

También deben definirse:

```text
PDD_SCOPE_VERSION_UUID
PDD_MODEL_VERSION_UUID
```

Son identidades lógicas. Cuando se instale `connexa_platform_ms.stock_management`, esos UUID
deben registrarse allí con sus filtros, parámetros, estado y aprobación.

## Instalación en el entorno FORECAST

Desde el virtualenv usado por el worker:

```bash
cd /srv/PDD/backend
python -m pip install -e .
```

Esto reutiliza el entorno, no el código monolítico de FORECAST.

## Primera carga

Antes de calcular features se debe capturar una versión inmutable del scope.
El comando usa una transacción `REPEATABLE READ`, materializa artículos y pares
y guarda conteos y checksums en la misma confirmación:

La política de categorías no comerciales vive en
`pdd_backend/rules/scope_exclusions.json`. Actualmente excluye del PDVB el
rubro 13, subrubros de nivel 1 3818 y 3838 (`INSUMOS`). La captura valida los
códigos y nombres contra `src.m_1_categorias` y excluye los artículos asignados
en `src.m_3_articulos`. Para incorporar otra categoría se agrega una regla al
JSON y se emite una nueva versión de scope; nunca se modifica una versión ya
capturada.

La captura debe programarse después de confirmar la finalización de la
sincronización diaria de `src.base_productos_vigentes`. En el ambiente actual
esa fuente se actualiza al mediodía; el horario definitivo de captura deberá
quedar fuera de esa ventana y depender del cierre exitoso de la sincronización,
no solamente de una hora fija.

```bash
pdd-etl scope-snapshot \
  --scope-version-uuid UUID_NUEVO \
  --version-no 4 \
  --business-date 2026-08-12 \
  --captured-by identificador_corporativo \
  --supersedes-scope-version-uuid b710f4d6-1bd8-4c32-8b1d-a3425c252cb9
```

Stock, venta diaria y PDVB rechazan un UUID que no exista o cuya membresía no
coincida con los conteos sellados. Nunca vuelven a calcular el scope desde la
tabla viva durante una corrida.

La primera corrida carga únicamente las tres ventanas de evidencia usadas por
PDVB: reciente, anterior y estacional. No materializa innecesariamente todos
los días intermedios del año.

```bash
pdd-etl initial-backfill --business-date 2026-08-02
```

El día de negocio debe ser el posterior al último día cerrado común. El flow se
detiene si ventas, enriquecimiento o stock no alcanzan el corte solicitado.

Después del backfill:

```bash
pdd-etl daily --business-date 2026-08-03
```

Para un rango controlado de features:

```bash
pdd-etl features --start 2026-07-01 --end 2026-07-31
```

## Prefect

`prefect.yaml` declara cinco deployments manuales en el pool `diarco-pdd` y la
cola `pdd`. No se definió todavía un cron de producción: primero deben medirse
duración, bloqueos, fecha real de cierre y horario de disponibilidad.

```bash
prefect deploy --all
```

## Backtest rolling-origin

La versión 0.6.0 extiende el backtest reproducible que genera una estimación para
cada fecha de origen y usa solamente observaciones anteriores a esa fecha. Antes
de instalarla se debe aplicar, con `ON_ERROR_STOP`, la migración:

```text
PDD - Migracion Analitica Backtest Intermitente v2.5.sql
```

La v2.5 se aplica después de la v2.4 y conserva las observaciones ya generadas.
Las identifica como `POINT_DAILY`, completa sus campos compatibles y amplía las
restricciones de estimadores. No borra ni recalcula el piloto anterior.

```sql
SELECT count(*) FROM datamart.dm_pdd_pdvb_backtest_detail;
```

El proceso compara siete estimadores sobre las mismas features basales y de
disponibilidad:

- `PDVB_CANDIDATE`: modelo indicado por `PDD_MODEL_VERSION_UUID`;
- `MEAN_28`: media servible de la ventana reciente;
- `ALGO_01_GROWTH`: factores 0,8/0,1/0,2 sin normalizar; la suma 1,1 representa
  el crecimiento intencional usado en FORECAST;
- `ALGO_01_NORMALIZED`: los mismos factores normalizados por ventanas
  disponibles, para aislar estadísticamente el efecto del uplift.
- `OCCURRENCE_SIZE`: probabilidad ponderada de ocurrencia por tamaño medio de
  una venta positiva; separa explícitamente frecuencia y magnitud.
- `CROSTON_SBA`: Croston con corrección SBA y `alpha=0,10`, calculado con días
  servibles de las ventanas anterior y reciente.
- `HYBRID_EXPERIMENTAL`: usa Croston/SBA en regímenes intermitentes, lumpies o
  con evidencia escasa; conserva PDVB para los demás y ALGO_01 normalizado sólo
  como recuperación de bloqueados.

La segmentación usa ADI=1,32 y CV²=0,49 como umbrales configurables y genera
métricas adicionales por `DEMAND_REGIME`, `RUBRO` y `SUBRUBRO_1`. Es una capa
experimental: no modifica el cálculo ni la publicación de `PDVB_CANDIDATE`.

Primero conviene ejecutar un piloto corto. Con fuentes cerradas hasta
`2026-08-11`, un ejemplo evaluable a horizonte 1 es:

```bash
pdd-etl rolling-backtest \
  --origin-from 2026-08-04 \
  --origin-to 2026-08-10 \
  --horizon 1 \
  --mode POINT_DAILY \
  --scope-version-uuid 90dcd987-2ad6-4e4e-8d19-2ead45775d1f \
  --model-version-uuid a0a35b25-628d-43f1-b651-82c97207fc60
```

`POINT_DAILY` evalúa solamente el día `origen+h`, útil para comprobar la
estabilidad diaria. `CUMULATIVE` evalúa la necesidad total desde `origen+1`
hasta `origen+h`; si hay días no servibles, exige por defecto 70% de cobertura
y escala la demanda basal observada a la ventana completa. Para un piloto común
de siete orígenes, con fuentes cerradas hasta 2026-08-11:

```bash
for horizon in 7 14 28; do
  pdd-etl rolling-backtest \
    --origin-from 2026-07-08 \
    --origin-to 2026-07-14 \
    --horizon "$horizon" \
    --mode CUMULATIVE \
    --actual-min-coverage 0.70 \
    --scope-version-uuid 90dcd987-2ad6-4e4e-8d19-2ead45775d1f \
    --model-version-uuid a0a35b25-628d-43f1-b651-82c97207fc60
done
```

El mismo rango de orígenes permite comparar horizontes sin cambiar la cohorte y
el mayor final de evaluación es 2026-08-11. Cada horizonte genera una corrida
independiente. Tras validar volumen y tiempos, el piloto diario de 28 orígenes
puede ejecutarse con `--origin-from 2026-07-14 --origin-to 2026-08-10`.

El flow carga automáticamente la unión de las ventanas estacionales, recientes,
anteriores y los días reales a evaluar. El límite predeterminado es 120 fechas
de origen para impedir una carga masiva accidental.

Desde 0.6.0 cada conexión envía keepalives y cada sentencia tiene un límite
predeterminado de 30 minutos. El detalle experimental materializa un único
escaneo acotado de las ventanas históricas y otro de la ventana real, evitando
la multiplicación de lecturas que causó la corrida huérfana anterior. Cada
origen informa por separado la duración del cálculo PDVB y del detalle.

La versión 0.6.1 agrega `--sample-percent`. El muestreo es determinístico por
artículo: un artículo seleccionado conserva todas sus sucursales y la cohorte
es idéntica para cada origen y estimador. Se recomienda 25% para la última
calibración inicial; el valor predeterminado 100 conserva el comportamiento
exhaustivo.

La cabecera y el avance quedan en `dm_pdd_pdvb_backtest_run`; el detalle por
estimador en `dm_pdd_pdvb_backtest_detail`; y las métricas en
`dm_pdd_pdvb_backtest_metric`.

```sql
SELECT calculation_run_uuid, status, origin_from, origin_to,
       completed_origin_count, origin_count, detail_row_count,
       metric_row_count, error_message
FROM datamart.dm_pdd_pdvb_backtest_run
ORDER BY started_at DESC
LIMIT 5;

SELECT estimator_code, sample_code, metric_code, metric_value,
       sample_size, expected_count, prediction_count,
       eligible_actual_count, zero_actual_count
FROM datamart.dm_pdd_pdvb_backtest_metric
WHERE calculation_run_uuid = 'UUID_CORRIDA'
  AND evaluation_mode = 'CUMULATIVE'
  AND segment_type = 'ALL'
  AND segment_id = 'ALL'
ORDER BY sample_code, metric_code, estimator_code;
```

El conteo esperado del detalle se controla sin valores fijos:

```sql
SELECT
    r.calculation_run_uuid,
    r.status,
    r.evaluation_mode,
    r.forecast_horizon_days,
    r.detail_row_count,
    r.origin_count::bigint * s.pair_count
        * cardinality(r.estimator_codes) AS detalle_esperado,
    r.metric_row_count
FROM datamart.dm_pdd_pdvb_backtest_run AS r
INNER JOIN datamart.dm_pdd_scope_version AS s
    USING (scope_version_uuid)
WHERE r.calculation_run_uuid = 'UUID_CORRIDA';

SELECT
    count(*) FILTER (
        WHERE evaluation_window_start > evaluation_date
           OR actual_window_days <> evaluation_date - evaluation_window_start + 1
    ) AS ventanas_invalidas,
    count(*) FILTER (
        WHERE actual_eligible_days > actual_window_days
           OR actual_availability_coverage NOT BETWEEN 0 AND 1
    ) AS coberturas_invalidas,
    count(*) FILTER (WHERE predicted_horizon_units < 0) AS pronosticos_negativos,
    count(*) FILTER (
        WHERE status = 'VALID'
          AND (actual_basal_units IS NULL OR predicted_horizon_units IS NULL)
    ) AS validos_incompletos
FROM datamart.dm_pdd_pdvb_backtest_detail
WHERE calculation_run_uuid = 'UUID_CORRIDA';
```

`OWN_VALID` mide cada estimador sobre sus casos utilizables. `COMMON_VALID` es
la comparación rectora: todos los estimadores se evalúan sobre exactamente los
mismos pares y fechas. WAPE y BIAS no se emiten cuando la suma real es cero. El
BIAS se define como `100 × sum(real - pronóstico) / sum(real)`: positivo indica
subpronóstico y negativo, sobrepronóstico.

## Publicación operativa para el frontend

`stock_management` es compartido con otros módulos de CONNEXA. Todas las
entidades propias de este proyecto usan el prefijo `pdd_`; por ejemplo,
`stock_management.pdd_item_logistics_snapshot` y
`stock_management.pdd_pdvb_current`.

En una base operativa existente con nombres anteriores se aplica, con
`ON_ERROR_STOP`, la migración no destructiva
`PDD - Migracion Operativa Prefijo PDD v2.6.sql`. En una instalación nueva se
ejecutan primero los DDL Core y DECAS vigentes, que ya crean nombres `pdd_*`.

Para publicar en Test deben configurarse credenciales independientes de las de
`diarco_data`:

```text
PDD_OPERATIONAL_PG_HOST=186.158.182.223
PDD_OPERATIONAL_PG_PORT=5432
PDD_OPERATIONAL_PG_DB=connexa_platform_test
PDD_OPERATIONAL_PG_USER=...
PDD_OPERATIONAL_PG_PASSWORD=...
PDD_OPERATIONAL_ALLOW_PRODUCTION=false
```

Antes de publicar:

```bash
python tools/validate_operational.py
```

La primera publicación toma una corrida PDVB completa y validada. En una única
transacción de la base destino registra modelo y scope, carga staging, verifica
conteo y SHA-256, persiste la historia compacta, actualiza `pdd_pdvb_current` y
genera incidencias para los pares bloqueados. Al final marca el linaje en
`diarco_data` y puede repetirse sin duplicar datos:

```bash
pdd-etl publish-pdvb \
  --calculation-run-uuid 34aa9ca9-8ab1-40ad-ab62-2ba1cd25ba77 \
  --created-by eduardo.ettlin
```

El destino permitido por defecto es exclusivamente `connexa_platform_test`.
Publicar en `connexa_platform_ms` requiere configurar además
`PDD_OPERATIONAL_ALLOW_PRODUCTION=true`; no debe habilitarse durante el piloto.

## Idempotencia y concurrencia

- Las particiones se crean por mes con `CREATE TABLE IF NOT EXISTS` y advisory
  locks transaccionales.
- Stock y venta diaria usan `ON CONFLICT ... DO UPDATE` solo si cambió el hash.
- La membresía del scope se inserta una sola vez; un UUID no puede recapturarse.
- PDVB y backtest son snapshots: una nueva corrida usa otro UUID y no modifica
  la corrida anterior.
- Cada job tiene un advisory lock para impedir dos escrituras simultáneas del
  mismo tipo.

## Validación sin carga

```bash
python tools/validate_sql.py
python -c "from prefect.utilities.importtools import load_script_as_module; load_script_as_module('pdd_backend/flows/analytical.py'); print('OK carga Prefect')"
```

El validador usa `EXPLAIN` para los cuatro INSERT y crea particiones futuras
dentro de una transacción que finaliza con rollback.

## Observaciones de Fase 1

- `procesado_ok` de t710 se conserva como linaje, pero no filtra registros.
- Stock positivo habilita un cero de venta como día servible.
- Stock cero/negativo excluye el día sin venta.
- Venta positiva permite inferir disponibilidad aunque falte el snapshot.
- Una fecha sin ventas no se genera hasta superar el gate de cierre común.
- Promociones con enriquecimiento usan `venta_basal`/`venta_promocional`.
- Una promoción detectada solo por flags y sin enriquecimiento se excluye del
  PDVB para no convertirla en un cero basal artificial.
