# PDD: recuperación automática del scope en TEST y PROD

Fecha: 2026-10-28. Versión preparada: `0.20.6`.

## Diagnóstico verificado

- `PDD_SOURCE_DAILY_MASTER_PROD` terminó `Completed` los días 25, 26 y 27/10;
  el contrato más reciente en `audit.pdd_source_sync_run` está `READY`, sin
  bloqueos.
- `PDD_OPERATIONAL_DAILY_MASTER` (TEST, 21:45 ART) y
  `PDD_OPERATIONAL_DAILY_MASTER_PROD` (PROD, 21:15 ART) fallaron en sus tres
  últimas corridas con `SCOPE_CONTAINS_EXCLUDED_BRANCHES`.
- Ambos bindings activos apuntan al scope v6
  `c533e7e7-3363-4dc3-8127-24f48fe33522`, capturado el 23/9.
- El scope v6 conserva 17 pares de la sucursal 71 y 20 de la 78, actualmente
  excluidas. La sucursal 13 estaba excluida al capturarlo y ahora no figura
  en la fuente: hay también una reapertura que el scope antiguo omite.
- El diagnóstico de stock y OC para la fecha operativa 27/10 tiene **un solo**
  bloqueo: `SCOPE_CONTAINS_EXCLUDED_BRANCHES`.
- En una transacción revertida, el snapshot nuevo proyectó 2.430 artículos y
  44.886 pares frente a 2.524 y 46.680 del v6. La variación es inferior al
  límite automático del 10%. Cambiarían 968 pares agregados y 2.762 retirados
  (7,99% de membresía), también dentro del límite.
- **Bloqueo adicional descubierto:** los 43 pares del scope candidato para
  sucursal 13 (Pilar) no tienen stock; `src.base_stock_sucursal` tiene cero
  filas para esa sucursal. El scope candidato no debe activarse todavía.
- La última publicación diaria completa de backlog en PROD es del 18/10.
  En TEST hay publicaciones de prueba de 1–2 líneas en fechas posteriores;
  esas filas no prueban una corrida diaria completa.

## Comportamiento nuevo

En la ejecución normal sin parámetros explícitos, el flujo diario consulta el
contrato de fuentes y el binding activo. Si sólo hay drift de sucursales
excluidas, o una sucursal antes excluida reabre, serializa el trabajo mediante
un advisory lock, reutiliza un candidato válido o captura un scope nuevo,
materializa las ventanas de features, valida conteos, frescura de stock y OC,
registra aprobación automática con `approved_by=pdd.scope.auto` y activa un
binding nuevo para el ambiente que ejecuta. El siguiente ambiente reutiliza
el scope compartido. La publicación diaria continúa sólo después de la
activación. El scope histórico no se altera.

La renovación se detiene si hay otro bloqueo, si afecta a más de cinco
sucursales o si artículos, número de pares o membresía de pares varían más
del 10%. Los límites se
configuran mediante `PDD_AUTO_SCOPE_MAX_AFFECTED_BRANCHES` y
`PDD_AUTO_SCOPE_MAX_DELTA_PERCENT`. El interruptor de emergencia es
`PDD_AUTO_SCOPE_ENABLED=false`.

## Condición previa para ejecutar la recuperación

Resolver la contradicción de Pilar (sucursal 13) en la fuente: debe participar
en la distribución, pero falta por completo en `src.base_stock_sucursal`.
Corregir `SP_BASE_STOCK_EXTEND` y volver a cargar el snapshot hasta cubrir sus
43 pares elegibles. No imputar stock cero ni modificar el scope v6. La
renovación automática volverá a comprobar readiness antes del backfill y de
cualquier activación.

El procedimiento `SP_BASE_STOCK_EXTEND` filtra según
`repl.SUCURSALES_EXCLUIDAS`; el surtido y
la política PDD usan `dbo.SUCURSALES_EXCLUIDAS`. La réplica PostgreSQL de
`T060_STOCK` tiene 17.803 filas de Pilar y cubre los 43 pares, pero el snapshot
derivado tiene cero. El SQL corregido está en
`ETL_DIARCO/scripts/sql/sp_SP_BASE_STOCK_EXTEND.sql`: usa la misma política
`dbo` que el surtido.

Antes de aplicar el procedimiento en SQL Server `data-sync`, verificar allí:

```sql
SELECT 'dbo' AS origen, COUNT(*) AS incluye_pilar
FROM dbo.SUCURSALES_EXCLUIDAS WHERE C_SUCU_EMPR = 13
UNION ALL
SELECT 'repl', COUNT(*)
FROM repl.SUCURSALES_EXCLUIDAS WHERE C_SUCU_EMPR = 13;

SELECT COUNT(*) AS stock_base_pilar
FROM repl.T060_STOCK WHERE C_SUCU_EMPR = 13;

SELECT COALESCE(d.C_SUCU_EMPR, r.C_SUCU_EMPR) AS sucursal,
       CASE WHEN d.C_SUCU_EMPR IS NULL THEN 'SOLO_REPL'
            ELSE 'SOLO_DBO' END AS diferencia
FROM dbo.SUCURSALES_EXCLUIDAS AS d
FULL JOIN repl.SUCURSALES_EXCLUIDAS AS r
  ON r.C_SUCU_EMPR = d.C_SUCU_EMPR
WHERE d.C_SUCU_EMPR IS NULL OR r.C_SUCU_EMPR IS NULL
ORDER BY sucursal;

SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.SP_BASE_STOCK_EXTEND'))
  AS definicion_actual;
```

Confirmar que la definición activa usa `repl.SUCURSALES_EXCLUIDAS`, que
`dbo` no excluye Pilar y revisar todas las diferencias entre ambas listas.
Aplicar el SQL corregido en `data-sync` y comprobar el resultado de
`PDD_SOURCE_DAILY_MASTER_PROD`. Volver a comprobar el snapshot y el contrato
de fuentes antes de lanzar el flujo PDD de TEST.

Si el procedimiento se aplicó durante una corrida de fuentes, el paso
`branch_stock` se ejecuta **después** de la actualización de ventas. Cuando ese
paso todavía no empezó, la misma corrida puede tomar el procedimiento nuevo.
Esperar el estado `READY` y comprobar filas de Pilar; repetir la sincronización
únicamente si terminó con cero filas para la sucursal 13.

```sql
SELECT count(*) AS stock_rows_pilar
FROM src.base_stock_sucursal
WHERE codigo_sucursal = 13;

SELECT count(*) AS exclusion_rows_pilar
FROM src.sucursales_excluidas
WHERE c_sucu_empr::integer = 13;
```

El paquete puede instalarse en TEST para validar código, pero una corrida
completa del flujo diario continuará bloqueada hasta resolver esta fuente.
Desplegar en PROD después de confirmar la corrida completa de TEST.

## Despliegue en TEST

Copiar `pdd-backend-0.20.6.zip` y su `.sha256` a `/tmp` de TEST. Ejecutar:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.6.zip.sha256
test ! -e /srv/PDD/backend.next-0.20.6 || { echo 'La ruta next ya existe'; exit 1; }
sudo install -d -o pdd -g pdd -m 0755 /srv/PDD/backend.next-0.20.6
sudo -u pdd unzip -q /tmp/pdd-backend-0.20.6.zip -d /srv/PDD/backend.next-0.20.6
cd /srv/PDD/backend.next-0.20.6
sudo -u pdd env HOME=/var/lib/pdd PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PYTHONPATH=/srv/PDD/backend.next-0.20.6 \
  /srv/PDD/.venv/bin/python -m pytest -q -p no:cacheprovider
sudo -u pdd env HOME=/var/lib/pdd PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PYTHONPATH=/srv/PDD/backend.next-0.20.6 \
  /srv/PDD/.venv/bin/python tools/validate_sql.py
```

Tras validar, detener el worker, conservar el backend anterior y sustituirlo:

```bash
BACKUP="/srv/PDD/backend.prev-$(date +%Y%m%d-%H%M%S)"
sudo systemctl stop prefect-worker-pdd-test.service
sudo mv /srv/PDD/backend "$BACKUP"
sudo mv /srv/PDD/backend.next-0.20.6 /srv/PDD/backend
sudo -u pdd env HOME=/var/lib/pdd /srv/PDD/.venv/bin/python -m pip install -e /srv/PDD/backend
sudo systemctl start prefect-worker-pdd-test.service
sudo systemctl status prefect-worker-pdd-test.service --no-pager -l
```

Verificar la versión desde el servidor y lanzar manualmente
`PDD_OPERATIONAL_DAILY_MASTER` **sin parámetros**. Esperar `Completed` y el log
`Pipeline diario completado`. Verificar que el binding TEST tenga una revisión
nueva y que el backlog corresponda al cierre más reciente.

## Despliegue en PROD

Hacerlo después de la validación de TEST, antes de la próxima ejecución de
PROD. Copiar el mismo ZIP y SHA a `/tmp` de PROD. El worker usa
`/srv/FORECAST/venv` y `/etc/connexa/pdd-prod.env`:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.6.zip.sha256
test ! -e /srv/PDD/backend.next-0.20.6 || { echo 'La ruta next ya existe'; exit 1; }
install -d -m 0755 /srv/PDD/backend.next-0.20.6
unzip -q /tmp/pdd-backend-0.20.6.zip -d /srv/PDD/backend.next-0.20.6
cd /srv/PDD/backend.next-0.20.6
TEST_ENV=$(mktemp)
sed '/^PDD_OPERATIONAL_ALLOW_PRODUCTION=/d' /etc/connexa/pdd-prod.env > "$TEST_ENV"
env HOME=/root PDD_ENV_PATH="$TEST_ENV" \
  PDD_OPERATIONAL_TARGET_ENV=PROD PDD_OPERATIONAL_ALLOW_PRODUCTION=false \
  PYTHONPATH=/srv/PDD/backend.next-0.20.6 \
  /srv/FORECAST/venv/bin/python -m pytest -q -p no:cacheprovider
RESULT=$?
rm -f "$TEST_ENV"
test "$RESULT" -eq 0
env HOME=/root PDD_ENV_PATH=/etc/connexa/pdd-prod.env \
  PDD_OPERATIONAL_TARGET_ENV=PROD PYTHONPATH=/srv/PDD/backend.next-0.20.6 \
  /srv/FORECAST/venv/bin/python tools/validate_sql.py
```

```bash
BACKUP="/srv/PDD/backend.prev-$(date +%Y%m%d-%H%M%S)"
systemctl stop prefect-worker-pdd.service
mv /srv/PDD/backend "$BACKUP"
mv /srv/PDD/backend.next-0.20.6 /srv/PDD/backend
/srv/FORECAST/venv/bin/python -m pip install -e /srv/PDD/backend
systemctl start prefect-worker-pdd.service
systemctl status prefect-worker-pdd.service --no-pager -l
```

Lanzar una vez `PDD_OPERATIONAL_DAILY_MASTER_PROD` **sin parámetros** y esperar
`Completed`. La corrida debería reutilizar el scope aprobado por TEST y activar
su propio binding PROD. Verificar el backlog de PROD y observar las siguientes
ejecuciones programadas de ambos ambientes.

La corrida normal avanzará al último cierre común disponible; no reconstruye
automáticamente una publicación de backlog por cada fecha omitida desde el
18/10. Si se requieren esas fechas para auditoría, planificar un backfill
controlado por separado, con fechas explícitas y `force=true`.

## Comprobaciones SQL de solo lectura

En `diarco_data`:

```sql
SELECT environment, revision_no, scope_version_uuid, status, activated_at,
       activated_by, reason
FROM audit.pdd_runtime_binding
WHERE environment IN ('TEST','PROD')
  AND process_code='DAILY_MASTER' AND status='ACTIVE'
ORDER BY environment;

SELECT scope_version_uuid, version_no, status, article_count, pair_count,
       detail -> 'approval' AS approval
FROM datamart.dm_pdd_scope_version
ORDER BY version_no DESC LIMIT 2;
```

En cada base operativa (`connexa_platform_test` y `connexa_platform_ms`):

```sql
SELECT business_date, snapshot_version, freshness_status, count(*) AS lines
FROM stock_management.pdd_current_backlog_line
GROUP BY 1,2,3
ORDER BY business_date DESC, lines DESC
LIMIT 10;
```

Si hubiera que revertir el código, detener el worker, restaurar el directorio
`backend.prev-*` guardado para ese ambiente y reiniciarlo. No reactivar el
binding del scope v6: sigue conteniendo sucursales ahora excluidas.
