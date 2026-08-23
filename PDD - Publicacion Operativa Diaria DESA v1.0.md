# PDD — Publicación operativa diaria DESA v1.0

Fecha: **2026-08-23**  
Backend: **diarco-pdd-backend 0.18.0**  
Deployment: **`PDD_OPERATIONAL_PUBLISH_DESA_DAILY`**

## 1. Objetivo

Mantener actualizado `stock_management` en DESA sin volver a ejecutar sobre
`diarco_data` la preparación de features ni el cálculo PDVB que ya realizó el
orquestador completo de TEST.

El flujo es una materialización de destino. Lee la corrida analítica canónica y
escribe únicamente en `connexa_platform_diarco` mediante el worker `pdd-desa`.

## 2. Secuencia y barreras

1. valida que el entorno operativo sea exactamente `DESA`;
2. resuelve la fecha comercial y exige el contrato auditado de fuentes `READY`;
3. deriva el UUID PDVB determinístico de `DAILY_PIPELINE_V2`;
4. espera que esa corrida exista, cubra exactamente el scope y tenga todas sus
   filas marcadas como publicadas;
5. valida el snapshot de stock operativo;
6. publica PDVB en DESA;
7. publica `pdd_item_logistics_snapshot`;
8. calcula posiciones y necesidades D/S;
9. consolida `pdd_current_backlog_line`.

La espera de PDVB realiza hasta seis reintentos separados por diez minutos. No
elige automáticamente otra corrida ni una versión anterior. El parámetro
`source_calculation_run_uuid` existe sólo para recuperación manual y conserva
todos los controles de fecha, scope, modelo, CD y cobertura.

## 3. Idempotencia

Los UUID de las etapas son los mismos que produciría `DAILY_PIPELINE_V2` para
la fecha, scope, modelo, configuración y snapshot de stock. Repetir el flujo:

- reutiliza publicaciones completas compatibles;
- no duplica snapshots ni backlog;
- termina `SKIPPED/NO_NEW_CLOSED_DATE` si DESA ya tiene vigente esa fecha y
  `force=false`.

El deployment histórico `PDD_OPERATIONAL_DAILY_MASTER_DESA` queda manual para
contingencia. No debe recibir schedule porque ejecuta features y PDVB.

## 4. Schedule

El deployment nuevo corre todos los días a las **21:00 ART**:

```text
cron: 0 21 * * *
timezone: America/Argentina/Buenos_Aires
queue: pdd-desa
force: false
pipeline_revision: DAILY_PIPELINE_V2
```

TEST comienza a las 20:30. Si su publicación PDVB todavía no terminó, la
barrera de reintentos posterga DESA sin aceptar datos incompletos.

## 5. Despliegue

En `/srv/PDD/backend`, usando el entorno Python de FORECAST:

```bash
source /srv/FORECAST/venv/bin/activate
cd /srv/PDD/backend
python -m pip install -e .
python -m pip show diarco-pdd-backend

export PDD_ENV_PATH=/srv/PDD/backend/.env.desa
python tools/validate_operational.py
python -m pytest -q

export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deploy --all
systemctl restart prefect-worker-pdd-desa.service
systemctl status prefect-worker-pdd-desa.service --no-pager

export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment inspect \
  "PDD - Publicacion operativa diaria DESA/PDD_OPERATIONAL_PUBLISH_DESA_DAILY"
```

La inspección debe mostrar `work_queue_name='pdd-desa'`, el cron de las 21:00 y
el parámetro `force=false`.

## 6. Primera ejecución controlada

Usar la fecha ya calculada y publicada por TEST:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment run \
  "PDD - Publicacion operativa diaria DESA/PDD_OPERATIONAL_PUBLISH_DESA_DAILY" \
  --params '{
    "business_date": "AAAA-MM-DD",
    "scope_version_uuid": "UUID_SCOPE_VIGENTE",
    "model_version_uuid": "UUID_MODELO_VIGENTE",
    "configuration_version_uuid": "2f916828-c59d-4190-a795-29ac5cfc1a66",
    "created_by": "eduardo.ettlin",
    "pipeline_revision": "DAILY_PIPELINE_V2",
    "force": true
  }' \
  --watch
```

No informar `source_calculation_run_uuid` en la operación normal.

## 7. Controles posteriores

En DESA, comprobar las cuatro corridas vigentes:

```sql
SELECT calculation_run_uuid, run_type, business_date, formula_version,
       status, is_current, input_row_count, output_row_count,
       warning_count, error_count, started_at, finished_at
FROM stock_management.pdd_calculation_run
WHERE business_date = DATE 'AAAA-MM-DD'
  AND run_type IN ('PDVB', 'DATA_PREP', 'DAILY_DECAS', 'PUBLISH')
ORDER BY started_at;
```

Comprobar el backlog actual:

```sql
SELECT business_date, snapshot_version, freshness_status,
       count(*) AS lineas,
       count(DISTINCT codigo_articulo) AS articulos,
       count(DISTINCT sucursal) AS sucursales,
       sum(d_open_quantity) AS d,
       sum(e_open_quantity) AS e,
       sum(c_open_quantity) AS c,
       sum(a_open_quantity) AS a,
       sum(s_open_quantity) AS s,
       sum(total_open_quantity) AS total
FROM stock_management.pdd_current_backlog_line
GROUP BY business_date, snapshot_version, freshness_status
ORDER BY freshness_status;
```

Resultado esperado: todas las corridas `SUCCEEDED`, un único `PUBLISH`
vigente para el scope y ninguna sustitución de la última foto válida si una
barrera falla.
