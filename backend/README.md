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

`prefect.yaml` declara cuatro deployments manuales en el pool `diarco-pdd` y la
cola `pdd`. No se definió todavía un cron de producción: primero deben medirse
duración, bloqueos, fecha real de cierre y horario de disponibilidad.

```bash
prefect deploy --all
```

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
