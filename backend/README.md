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

La ruta se determina a nivel artículo–sucursal, sin inferirla por el número de
sucursal. El scope selecciona exclusivamente `cod_cd = '41CD'` y
`abastecimiento = 0`. Los modos 1 (proveedor), 2 (cross docking) y 3 (QX/CD82)
quedan fuera, incluyendo las DIARCO BARRIO y las DIARCO PUEBLO abastecidas por
el 82 aunque alguna tenga número menor a 300.

Las excepciones operativas adicionales se toman de
`src.sucursales_excluidas`. Esta fuente puede contener sucursales que ya estaban
fuera por su ruta al CD82; por eso la captura guarda en `pair_filter` solamente
las exclusiones que efectivamente intersectan el universo candidato de CD41 y
cuántos pares removieron. La exclusión queda congelada en esa versión: cuando
una sucursal cerrada reabre y deja de figurar en la fuente, vuelve a incorporarse
al capturar un scope nuevo; nunca se modifica retroactivamente uno anterior.

La captura debe programarse después de confirmar la finalización de la
sincronización diaria de `src.base_productos_vigentes`. En el ambiente actual
esa fuente se actualiza al mediodía; el horario definitivo de captura deberá
quedar fuera de esa ventana y depender del cierre exitoso de la sincronización,
no solamente de una hora fija.

```bash
pdd-etl scope-snapshot \
  --scope-version-uuid UUID_NUEVO \
  --version-no 5 \
  --business-date 2026-08-16 \
  --captured-by identificador_corporativo \
  --supersedes-scope-version-uuid 90dcd987-2ad6-4e4e-8d19-2ead45775d1f
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

`prefect.yaml` declara deployments manuales en el pool `diarco-pdd` y la cola
`pdd`. No se definió todavía un cron de producción: primero deben medirse
duración, bloqueos, fecha real de cierre y horario de disponibilidad.

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deploy --all
```

La misma exportación debe ejecutarse en cada terminal antes de cualquier
`prefect deployment inspect`, `prefect deployment run`, `prefect flow-run` o
comando equivalente contra el orquestador de CONNEXA.

### Orquestador diario completo

Desde la versión 0.13.0 el deployment `PDD_OPERATIONAL_DAILY_MASTER` ejecuta
la cadena diaria completa:

1. refresca `src.mv_base_oc_pendientes` bajo un advisory lock;
2. determina el último cierre común de ventas crudas, ventas enriquecidas y
   stock LEGACY;
3. valida stock operativo, scope y frescura de OC;
4. recupera los días de features no materializados;
5. calcula y publica PDVB;
6. publica los atributos logísticos;
7. calcula posiciones y necesidades D/S;
8. consolida y publica el backlog vigente.

La vista se refresca con `REFRESH MATERIALIZED VIEW` no concurrente porque no
se ha certificado un índice único compatible con `CONCURRENTLY`. El worker PDD
tiene límite uno y el job agrega un lock transaccional, por lo que dos corridas
no pueden refrescarla simultáneamente.

Sin `business_date`, el flujo usa como fecha operativa el día posterior al
cierre común. Si esa fecha ya tiene backlog vigente para el mismo scope,
termina correctamente como `SKIPPED/NO_NEW_CLOSED_DATE`. `force=true` permite
reanudar o repetir de forma controlada la misma fecha.

Los UUID de PDVB, logística, DAILY_DECAS y backlog se derivan de fecha, scope,
modelo, configuración y `pipeline_revision`. Una repetición de la misma
revisión reutiliza resultados compatibles sin duplicarlos. Cuando cambie la
lógica de una etapa y se necesite recalcular una fecha ya procesada, se debe
incrementar la revisión, por ejemplo a `DAILY_PIPELINE_V2`.

Primera prueba completa del piloto existente:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deploy --all

export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment run \
  "PDD - Orquestador diario completo/PDD_OPERATIONAL_DAILY_MASTER" \
  --params '{
    "business_date": "2026-08-16",
    "scope_version_uuid": "f157e436-1094-431b-ae2a-8f477d780c3e",
    "model_version_uuid": "a0a35b25-628d-43f1-b651-82c97207fc60",
    "configuration_version_uuid": "2f916828-c59d-4190-a795-29ac5cfc1a66",
    "created_by": "eduardo.ettlin",
    "pipeline_revision": "DAILY_PIPELINE_V1",
    "force": true
  }' \
  --watch
```

Después de validar esa corrida, la operación normal no informa fecha ni usa
`force`; el flujo la resuelve a partir de las fuentes:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment run \
  "PDD - Orquestador diario completo/PDD_OPERATIONAL_DAILY_MASTER" \
  --watch
```

Desde la versión 0.13.1 el deployment tiene activo el schedule
`pdd-operational-daily-2030-art`: todos los días a las 20:30 de
`America/Argentina/Buenos_Aires`, con `business_date=null` y `force=false`.
Si todavía no existe un nuevo cierre común, termina de forma idempotente como
`SKIPPED/NO_NEW_CLOSED_DATE`; si una fuente necesaria está atrasada o es
inconsistente, falla antes de desplazar las publicaciones vigentes.

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

### Primer bloque de insumos operativos

Antes de calcular necesidades se publican los atributos logísticos congelados
del artículo. La carga toma todos los artículos de la versión de scope (también
los que todavía no tienen un par ruteado), usa la fila del CD 41 de
`src.base_productos_vigentes` y registra una corrida `DATA_PREP`, su
`pdd_source_snapshot` y el detalle en `pdd_item_logistics_snapshot`.

Mapeo inicial:

- `base_unit`: `KG` cuando `m_vende_por_peso = 1`; en otro caso `UNIT`;
- `units_per_package`: `q_factor_compra` positivo;
- `packages_per_pallet`: `full_capacity_pallet` positivo;
- `unit_weight_kg`: `q_peso_unit_art` positivo;
- `unit_volume_m3`: nulo porque la fuente actual no lo provee.

La fecha `2026-08-16` es la primera fecha operativa posterior al cierre de
ventas confirmado hasta `2026-08-15`:

```bash
pdd-etl publish-item-logistics \
  --business-date 2026-08-16 \
  --scope-version-uuid f157e436-1094-431b-ae2a-8f477d780c3e \
  --created-by eduardo.ettlin
```

`--calculation-run-uuid` es opcional. Si se informa, una repetición idéntica es
idempotente; si se omite, el proceso genera y devuelve el UUID.

Antes de materializar `pdd_branch_stock_position` y
`pdd_cd_stock_position`, ejecutar el diagnóstico contra la misma fecha cerrada:

```bash
pdd-etl stock-readiness \
  --expected-through 2026-08-15 \
  --scope-version-uuid f157e436-1094-431b-ae2a-8f477d780c3e
```

El resultado solo será `READY` si la fuente de stock alcanza esa fecha, cubre
el scope sin duplicados, stock físico nulo ni entradas negativas y la vista
materializada canónica de OC también está actualizada. Desde la versión
`0.12.0`, `src.mv_base_oc_pendientes` reemplaza —no se suma— al campo LEGACY
`base_stock_sucursal.pedido_pendiente`.

La vista ya expresa `pendientes` en la unidad operativa: unidades base para
artículos comunes y peso para los vendidos por peso. El proceso conserva solo
filas con `pendientes > 0` y las agrega por artículo–destino. Los valores
negativos se excluyen como anomalías de sobrecumplimiento y quedan contados en
el diagnóstico y en `pdd_source_snapshot.detail`. Las OC con destino sucursal
alimentan `pdd_branch_stock_position.direct_po_inbound`; las destinadas al CD
41 alimentan `pdd_cd_stock_position.open_po_on_time`. Como la vista no contiene
fecha comprometida, todavía no es posible separar `open_po_on_time` de
`open_po_overdue`.

`transito_pendiente` continúa mapeando el tránsito desde CD.
`transfer_pendiente` queda deliberadamente sin mapear: el proceso LEGACY lo
trata como entrada futura y el campo operativo
`confirmed_transfer_pending` es sustractivo.

### Corrida DAILY_DECAS piloto

La versión `0.12.0` construye en una única transacción las posiciones de stock
de sucursal, las necesidades automáticas D/S y la posición informativa del CD:

```bash
pdd-etl daily-decas \
  --business-date 2026-08-16 \
  --scope-version-uuid f157e436-1094-431b-ae2a-8f477d780c3e \
  --pdvb-calculation-run-uuid 8ee3dcae-eca6-4eb7-8440-c477e2e9aa1a \
  --logistics-calculation-run-uuid UUID_CORRIDA_LOGISTICA \
  --configuration-version-uuid 2f916828-c59d-4190-a795-29ac5cfc1a66 \
  --calculation-run-uuid UUID_NUEVA_CORRIDA_DIARIA \
  --created-by eduardo.ettlin
```

La configuración `PDD_DAILY_DECAS_TEST_PILOT` se persiste como `DRAFT`. Usa
`dias_preparacion`, `q_dias_stock` y `q_dias_sobre_stock` de
`src.base_stock_sucursal`. Cuando `dias_preparacion` falta o no es positivo,
aplica un fallback explícito de 15 días y marca la posición `WARN`.

Las ventas especiales comprometidas y las transferencias confirmadas se
mantienen transitoriamente en cero hasta ratificar su fuente y semántica. Las
órdenes de compra pendientes se informan provisionalmente como on-time; las
filas afectadas conservan la alerta `PO_DUE_CLASSIFICATION_PENDING`.

Las fórmulas piloto son:

```text
D = max(Stock Máximo - Stock Neto, 0)
S = max((Stock Máximo + Sobre Stock) - max(Stock Neto, 0), 0) - D
```

Ambas cantidades se redondean hacia arriba al factor de compra. Este contrato
es apto para Test y para habilitar el desarrollo frontend; requiere
ratificación funcional antes de promoverse a Producción.

### Publicación del backlog DECAS vigente

La versión `0.10.0` consolida los saldos positivos D/E/C/A/S en
`stock_management.pdd_current_backlog_line` y conserva su trazabilidad en
`stock_management.pdd_backlog_source_allocation`. D/S provienen de una corrida
`DAILY_DECAS` vigente; E/C/A se incorporan solamente cuando existen necesidades
dirigidas `ACTIVE` y líneas con saldo abierto. El publicador no crea E/C/A ni
transforma decisiones comerciales en demanda automática.

```bash
pdd-etl publish-backlog \
  --daily-calculation-run-uuid UUID_CORRIDA_DAILY_DECAS \
  --calculation-run-uuid UUID_NUEVA_PUBLICACION \
  --created-by eduardo.ettlin
```

La tabla es una proyección vigente, no un segundo maestro: conserva el
`backlog_line_uuid` del mismo grano CD–sucursal–artículo–proveedor e incrementa
`row_version` en cada nueva foto. Las líneas que dejan de tener saldo se retiran
de la proyección. La publicación completa ocurre en una sola transacción; una
falla no desplaza la foto anterior.

La atribución inicial se versiona como `DECAS_ATTRIBUTION_V1` y ordena E vencida,
E vigente, C, D, A y S; dentro de cada nivel usa fecha objetivo, antigüedad e ID.
Los factores logísticos incompletos no ocultan el backlog: publican la línea con
`freshness_status = 'INCOMPLETE'` y una alerta explícita.

Hasta implementar la conciliación de eventos Valkimia, el proceso exige que no
existan importaciones `PENDING`, `ACCEPTED` o `PARTIAL`. Esta barrera evita
publicar un saldo que ignore pipeline activo.

Controles posteriores:

```sql
SELECT r.calculation_run_uuid,r.business_date,r.status,r.is_current,
       r.input_row_count,r.output_row_count,r.warning_count,r.summary
FROM stock_management.pdd_calculation_run r
WHERE r.run_type='PUBLISH' AND r.scope_id='41:BACKLOG'
ORDER BY r.created_at DESC
LIMIT 5;

SELECT snapshot_version,business_date,freshness_status,count(*) AS lineas,
       sum(d_open_quantity) AS d,sum(e_open_quantity) AS e,
       sum(c_open_quantity) AS c,sum(a_open_quantity) AS a,
       sum(s_open_quantity) AS s,sum(total_open_quantity) AS total
FROM stock_management.pdd_current_backlog_line
GROUP BY snapshot_version,business_date,freshness_status
ORDER BY freshness_status;

SELECT a.source_type,count(*) AS fuentes,
       sum(a.contributed_quantity-a.prepared_allocated_quantity) AS saldo_atribuido
FROM stock_management.pdd_backlog_source_allocation a
GROUP BY a.source_type
ORDER BY a.source_type;
```

El deployment manual es `PDD_PUBLISH_BACKLOG_TEST_MANUAL`.

Desde 0.8.0 el diagnóstico cruza además `src.sucursales_excluidas`. Si un scope
anterior todavía contiene una sucursal hoy excluida, informa
`SCOPE_CONTAINS_EXCLUDED_BRANCHES`, `excluded_branch_pairs` y la lista de
sucursales; los faltantes restantes se informan por separado en
`unexplained_missing_pairs`. La corrección es capturar una versión nueva del
scope, no imputar stock cero ni alterar la versión histórica.

Controles posteriores a la publicación logística:

```sql
SELECT r.calculation_run_uuid, r.business_date, r.status, r.is_current,
       r.input_row_count, r.output_row_count, r.warning_count,
       r.input_checksum, r.output_checksum
FROM stock_management.pdd_calculation_run AS r
WHERE r.run_type = 'DATA_PREP'
ORDER BY r.created_at DESC
LIMIT 5;

SELECT l.quality_status, count(*) AS registros
FROM stock_management.pdd_item_logistics_snapshot AS l
JOIN stock_management.pdd_calculation_run AS r
  ON r.calculation_run_id = l.calculation_run_id
WHERE r.calculation_run_uuid = 'UUID_CORRIDA'
GROUP BY l.quality_status
ORDER BY l.quality_status;

SELECT s.source_code, s.physical_relation, s.as_of_ts, s.row_count,
       s.status, s.checksum
FROM stock_management.pdd_source_snapshot AS s
JOIN stock_management.pdd_calculation_run AS r
  ON r.calculation_run_id = s.calculation_run_id
WHERE r.calculation_run_uuid = 'UUID_CORRIDA';
```

Los despliegues manuales equivalentes son
`PDD_PUBLISH_ITEM_LOGISTICS_TEST_MANUAL` y `PDD_STOCK_READINESS_MANUAL`.

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

## Contrato HTTP para frontend

Desde la versión 0.14.0 este paquete no expone una API productiva. Python y
Prefect quedan limitados al ETL, cálculo y publicación de entidades PDD.

El contrato de las 15 operaciones se mantiene en
`contracts/pdd-frontend-openapi-v1.yaml`, con base pública
`/connexa/api/v1/pdd`. Debe implementarlo el microservicio Java Stock
Management que consume la librería `connexa-platform-lib-model-stock-management`.

```bash
python tools/validate_frontend_contract.py
python tools/run_frontend_mock.py --port 4010
```

El mock sirve solo para desarrollo frontend y pruebas de contrato; no accede a
PostgreSQL, no sustituye el backend Java y no debe desplegarse como servicio.
Ver `../PDD - Especificacion Implementacion API Java Stock Management v1.0.md`.

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
