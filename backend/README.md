# Backend analítico PDD

Primera implementación de las entidades pesadas alojadas en
`diarco_data.datamart`:

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

Son identidades lógicas. Cuando se instale `connexa_platform_ms.pdd`, esos UUID
deben registrarse allí con sus filtros, parámetros, estado y aprobación.

## Instalación en el entorno FORECAST

Desde el virtualenv usado por el worker:

```bash
cd /srv/PDD/backend
python -m pip install -e .
```

Esto reutiliza el entorno, no el código monolítico de FORECAST.

## Primera carga

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

`prefect.yaml` declara tres deployments manuales en el pool `diarco-ms` y la
cola `pdd`. No se definió todavía un cron de producción: primero deben medirse
duración, bloqueos, fecha real de cierre y horario de disponibilidad.

```bash
prefect deploy --all
```

## Idempotencia y concurrencia

- Las particiones se crean por mes con `CREATE TABLE IF NOT EXISTS` y advisory
  locks transaccionales.
- Stock y venta diaria usan `ON CONFLICT ... DO UPDATE` solo si cambió el hash.
- PDVB y backtest son snapshots: una nueva corrida usa otro UUID y no modifica
  la corrida anterior.
- Cada job tiene un advisory lock para impedir dos escrituras simultáneas del
  mismo tipo.

## Validación sin carga

```bash
python tools/validate_sql.py
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
