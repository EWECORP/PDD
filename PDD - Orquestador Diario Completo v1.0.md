# PDD — Orquestador diario completo v1.0

## Objetivo

El deployment `PDD_OPERATIONAL_DAILY_MASTER` concentra la actualización diaria
de PDD desde las fuentes de `diarco_data` hasta las entidades vigentes de
`connexa_platform_test.stock_management`.

Su principio de seguridad es *fail closed*: si una fuente no alcanza la fecha
requerida, el scope no está preparado o el diagnóstico de stock queda
`BLOCKED`, no publica una foto parcial nueva. Las fotos vigentes anteriores
permanecen disponibles para el frontend.

## Flujo de datos

```text
audit.pdd_source_sync_run (READY)
             │
             ▼
gate de cierre y stock ──BLOCKED──► termina sin publicar
             │ READY
             ▼
dm_pdd_stock_diario + dm_pdd_venta_diaria
             │
             ▼
dm_pdd_pdvb_estimate_detail
             │
             ▼
stock_management.pdd_pdvb_current
             │
             ▼
stock_management.pdd_item_logistics_snapshot
             │
             ▼
pdd_branch_stock_position + pdd_cd_stock_position
             │
             ▼
pdd_need_snapshot (D/S)
             │
             ▼
stock_management.pdd_current_backlog_line
```

## Etapas y condiciones

| Orden | Etapa | Salida principal | Condición de avance |
|---:|---|---|---|
| 1 | Validar sincronización | `audit.pdd_source_sync_run` | corrida de fuentes `READY` y cierre disponible |
| 2 | Resolver fecha | contexto de cierre | ventas crudas, enriquecidas y t710 llegan al corte |
| 3 | Readiness | diagnóstico `READY` | stock de sucursal y OC llegan a la fecha operativa; scope cubierto |
| 4 | Features | stock/venta canónicos | rango pendiente materializado |
| 5 | PDVB | detalle analítico y `pdd_pdvb_current` | corrida completa y publicable |
| 6 | Logística | `pdd_item_logistics_snapshot` | snapshot compatible con scope/fecha |
| 7 | DAILY_DECAS | posiciones y necesidades D/S | PDVB, logística y configuración coherentes |
| 8 | Backlog | `pdd_current_backlog_line` | DAILY_DECAS vigente y sin pipeline Valkimia activo |

El refresco de `src.mv_base_oc_pendientes` pertenece al orquestador de fuentes
de `ETL_DIARCO`. PDD consume el contrato auditado `audit.pdd_source_sync_run` y
no vuelve a refrescar ni sincronizar fuentes.

## Resolución automática de fecha

El corte analítico es el mínimo entre:

- `max(src.base_ventas_extendida.fecha)`;
- `max(datamart.dm_bve_ventas_enriquecidas.fecha)`;
- último día disponible inferido de `src.t710_estadis_stock`.

La fecha operativa es `corte + 1 día`. Además:

- `src.base_stock_sucursal.fecha_stock` debe alcanzar la fecha operativa;
- `mv_base_oc_pendientes.fecha_extraccion` debe quedar en esa fecha o una
  posterior después del refresh;
- la fecha no puede ser futura en `America/Argentina/Buenos_Aires`;
- si el scope no tiene historia canónica, se exige ejecutar antes
  `PDD_INITIAL_BACKFILL_MANUAL`.

Si hubo días sin ejecutar, el flujo comienza en el día posterior a la más
antigua de las últimas fechas canónicas de stock y venta y recupera el rango
hasta el corte. No estima sobre huecos silenciosos.

## Idempotencia y reanudación

La identidad de cada etapa se calcula mediante UUIDv5 con:

```text
pipeline_revision | etapa | business_date | scope | modelo | configuración
```

Por lo tanto:

- una repetición tras una falla reutiliza etapas ya confirmadas;
- no duplica PDVB, logística, DAILY_DECAS ni backlog;
- `force=true` omite solamente el control de «fecha ya publicada»;
- para recalcular la misma fecha con código o reglas nuevas se incrementa
  `pipeline_revision`.

## Despliegue inicial

```bash
cd /srv/PDD/backend
sudo -u pdd env HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  /srv/PDD/.venv/bin/python3 -m pytest -q
sudo -u pdd env HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PDD_OPERATIONAL_TARGET_ENV=TEST \
  /srv/PDD/.venv/bin/python3 tools/validate_sql.py
sudo -u pdd env HOME=/var/lib/pdd \
  PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PDD_OPERATIONAL_TARGET_ENV=TEST \
  /srv/PDD/.venv/bin/python3 tools/validate_operational.py

export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deploy --all
```

Comprobar el deployment:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment inspect \
  "PDD - Orquestador diario completo/PDD_OPERATIONAL_DAILY_MASTER"
```

## Ejecución controlada

En operación normal no se informan UUID ni fecha: el flujo resuelve el binding
`ACTIVE` y el último cierre común. `force=true` se reserva para reanudar o
repetir de forma controlada la misma fecha:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deployment run \
  "PDD - Orquestador diario completo/PDD_OPERATIONAL_DAILY_MASTER" \
  --param force=true \
  --watch
```

La primera validación integral de la versión 0.20.0 en TEST terminó
`Completed` para fecha de negocio `2026-09-23`, con stock al cierre de
`2026-09-22` y 13.773 líneas de backlog.

## Controles posteriores

En `diarco_data`:

```sql
SELECT max(fecha_extraccion) AS oc_as_of,
       count(*) AS filas,
       count(*) FILTER (WHERE pendientes > 0) AS positivas,
       count(*) FILTER (WHERE pendientes < 0) AS negativas_excluidas
FROM src.mv_base_oc_pendientes;

SELECT business_date, calculation_run_uuid, scope_version_uuid,
       model_version_uuid, count(*) AS estimaciones,
       count(*) FILTER (WHERE publication_batch_uuid IS NULL) AS sin_publicar
FROM datamart.dm_pdd_pdvb_estimate_detail
WHERE business_date = DATE '2026-08-16'
GROUP BY business_date, calculation_run_uuid,
         scope_version_uuid, model_version_uuid
ORDER BY max(created_at) DESC
LIMIT 5;
```

En `connexa_platform_test`:

```sql
SELECT calculation_run_uuid, run_type, scope_id, business_date,
       formula_version, status, is_current, input_row_count,
       output_row_count, warning_count, error_count, finished_at
FROM stock_management.pdd_calculation_run
WHERE created_by IN ('eduardo.ettlin', 'pdd.daily.orchestrator')
ORDER BY created_at DESC
LIMIT 12;

SELECT snapshot_version, business_date, freshness_status,
       count(*) AS lineas, sum(total_open_quantity) AS cantidad_total
FROM stock_management.pdd_current_backlog_line
GROUP BY snapshot_version, business_date, freshness_status
ORDER BY freshness_status;

SELECT s.source_code, s.physical_relation, s.as_of_ts,
       s.row_count, s.status, s.detail
FROM stock_management.pdd_source_snapshot AS s
INNER JOIN stock_management.pdd_calculation_run AS r
    ON r.calculation_run_id = s.calculation_run_id
WHERE r.run_type = 'DAILY_DECAS'
ORDER BY r.created_at DESC, s.source_code
LIMIT 20;
```

La corrida se acepta cuando Prefect termina `Completed`, las etapas destino
figuran `SUCCEEDED`, el backlog nuevo es `is_current=true`, la fuente
`OPEN_PURCHASE_ORDERS` aparece en los snapshots y no hay errores de integridad.

## Schedule diario

Desde la versión 0.20.0 el deployment ejecuta el único schedule activo
`pdd-operational-daily-2115-art` todos los días a las 21:15 en la zona
`America/Argentina/Buenos_Aires`. Sus parámetros normales son:

```text
business_date = null
force = false
pipeline_revision = valor ACTIVE de audit.pdd_runtime_binding
```

El horario está versionado en `prefect.yaml`. Se publica siempre con:

```bash
export PREFECT_API_URL=https://orquestador.connexa-cloud.com/api
prefect deploy --all
```

`PDD_ANALYTICAL_DAILY_PROD` no debe tener un schedule adicional mientras esté
activo el maestro. El maestro ya ejecuta `pdd_features_flow`, calcula PDVB y
continúa con publicación, logística, DAILY_DECAS y backlog. Mantener el
deployment analítico sin schedule permite reejecuciones manuales o diagnóstico;
programarlo duplicaría cálculo y escrituras sobre la misma fecha.
