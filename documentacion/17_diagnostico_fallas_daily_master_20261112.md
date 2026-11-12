# Revisión de fallas PDD TEST y PROD — 12/11/2026

Diagnóstico realizado mediante consultas de lectura a la API de Prefect y contraste con el código local. Horarios expresados en Argentina (UTC-3). No se modificaron bases, permisos, deployments ni estados de corridas.

## Causa común confirmada

Las ejecuciones del 10 y 11/11 de ambos maestros terminan al inicio con:

```text
RuntimeError: La ultima sincronizacion completa de fuentes PDD no esta READY
```

La dependencia `PDD_SOURCE_DAILY_MASTER_PROD` falló ambos días con:

```text
psycopg2.errors.InsufficientPrivilege: must be owner of table base_productos_vigentes
```

El traceback de la corrida del 11/11 localiza el error en el worker Windows:

```text
E:\ETL\ETL_DIARCO\scripts\pdd\pdd_source_daily.py
  execute_refreshes -> capturar_base_stock
E:\ETL\ETL_DIARCO\scripts\push\obtener_base_stock.py
  asegurar_indices_base_stock -> cur.execute(ddl), línea 213
```

La función intenta crear índices sobre `src.base_stock_sucursal` y `src.base_productos_vigentes`. Para esta última declara `idx_bpv_sucu_art (c_sucu_empr, c_articulo)` e `idx_bpv_codcd_art (cod_cd, c_articulo)`. Los logs confirman el error de propiedad, pero no identifican cuál de esas dos sentencias falla ni el usuario efectivo o propietario actual. Esos datos deben verificarse en PostgreSQL antes de elegir una corrección. No hay evidencia que permita atribuirlo a un cambio específico de propietario o credenciales.

## Evidencia de Prefect

| Proceso | Inicio ART | Resultado | Corrida |
| --- | --- | --- | --- |
| Fuentes PROD | 11/11 18:30 | Failed, permisos de propietario; finalizó 20:06 | `01a1bd12-0194-790a-8949-0b58514b51c1` |
| Maestro PROD | 11/11 21:15 | Failed, fuentes no READY | `01a1bda8-cd87-74a0-a133-147edb02efd5` |
| Maestro TEST | 11/11 21:45 | Failed, fuentes no READY | `01a1bdc4-63be-7fbd-9b5b-6b4ed7108c18` |
| Fuentes PROD | 10/11 18:29 | Failed, mismo error de propietario | `01a1b7eb-75f2-7075-843b-c6a5bc5079c9` |
| Maestro PROD | 10/11 21:15 | Failed, fuentes no READY | `01a1b882-43fc-797f-ab05-4a02371a1fc8` |
| Maestro TEST | 10/11 21:44 | Failed, fuentes no READY | `01a1b89d-dbc9-7bba-be81-861d11364bc5` |

Última ejecución completa de PROD observada: 09/11 a las 21:15 ART, corrida `01a1b35c-9d26-7277-8ad8-f78bb82a2202`. Su log de cierre confirma fecha de negocio `2026-11-09`, fecha de stock `2026-11-08` y **11.224 líneas de backlog**.

## Bloqueo adicional histórico en TEST

Las corridas programadas del 07, 08 y 09/11 (ART) superaron la validación inicial y fallaron posteriormente con:

```text
RuntimeError: Hay importaciones Valkimia activas; falta habilitar su conciliacion en backlog
```

`backend/pdd_backend/jobs/backlog.py`, función `publish_current_backlog`, bloquea la publicación ante importaciones del CD de origen en estados `PENDING`, `ACCEPTED` o `PARTIAL`. Es un control explícito del código; el mensaje no demuestra que exista un interruptor de configuración para habilitar la conciliación.

Existe el script local `cancel_test_valkimia_20261110.py`, que contempla una limpieza protegida de cuatro importaciones de prueba. Su existencia no demuestra que se haya ejecutado. No se ejecutó durante esta revisión ni se comprobó el estado actual de esas importaciones. Por ello, el bloqueo histórico de TEST requiere una nueva consulta antes de concluir que sigue vigente.

## Orden de recuperación

1. En `diarco_data`, con la misma conexión del worker de fuentes, consultar `current_user`, `session_user`, propietarios e índices de ambas tablas. Revisar si los índices faltan o si el worker está usando un rol distinto del previsto.
2. Corregir la gestión de los índices con el propietario o un administrador. Evitar conceder privilegios amplios o cambiar propietarios sin comprobar primero el contrato de roles. Separar el DDL del proceso diario es una alternativa a evaluar, no una corrección aplicada.
3. Reejecutar la sincronización de fuentes y comprobar su estado final `READY` en `audit.pdd_source_sync_run`. No basta con que se haya cargado parcialmente stock.
4. Consultar las importaciones activas de TEST y resolverlas según su estado real. No cancelar automáticamente importaciones con actividad externa.
5. Reejecutar los maestros y comprobar `Completed`, resumen de DAILY_DECAS y backlog vigente. Reintentar sólo los maestros mientras fuentes siga sin READY reproducirá el bloqueo inicial.

Consultas de diagnóstico de solo lectura:

```sql
-- diarco_data, usando la identidad del worker de fuentes
SELECT current_database(), current_user, session_user;

SELECT n.nspname AS schema_name, c.relname,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'src'
  AND c.relname IN ('base_productos_vigentes', 'base_stock_sucursal');

SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'src'
  AND tablename IN ('base_productos_vigentes', 'base_stock_sucursal')
ORDER BY tablename, indexname;

-- connexa_platform_test
SELECT valkimia_import_id, valkimia_import_uuid, origin_cd, status,
       imported_at, last_polled_at
FROM stock_management.pdd_valkimia_import
WHERE origin_cd = 41 AND status IN ('PENDING', 'ACCEPTED', 'PARTIAL')
ORDER BY valkimia_import_id;
```

La revisión identifica la causa de las últimas fallas; la recuperación de los procesos sigue pendiente. No se verificó directamente el contenido actual de las bases operativas.
