# Limites y diagnostico del master diario PDD (25/11/2026)

## Incidente observado

La corrida PROD del 24/11, `01a2008d-fcec-7a83-902a-5697e56e73c4`, inicio a las
21:00 ART. Completo features, PDVB y publicacion logistica, pero la tarea
`PDD - Construir posiciones y necesidades D y S` inicio a las 22:39:56 y no
termino. La corrida fue cancelada el 25/11 a las 10:10:06, tras unas 13 h 10 m.
El proceso hijo salio con codigo -9. No se publicaron DAILY_DECAS ni backlog
PROD del 24/11. El master TEST de esa fecha completo entre 22:15 y 23:52;
ambos procesos coincidieron sobre `diarco_data`.

La sincronizacion de fuentes del 24/11 habia terminado a las 20:33. Una
consulta posterior de `pg_stat_activity` no mostro sesiones PDD ni bloqueadores
activos. No existe muestra historica de esperas de esa corrida, de modo que
**no esta demostrado** si la causa fue un lock, un plan SQL lento o presion de
CPU/IO. La tarea tampoco registraba avances internos. No atribuir la falla a
una de esas causas sin evidencia adicional.

## Controles incluidos en 0.20.14

1. El mismo codigo de master, usado por TEST y PROD, adquiere un advisory lock
   de sesion en `diarco_data` antes de ejecutar las tareas. Espera hasta 15 min
   y luego falla con `SOURCE_DAILY_MASTER_BUSY`. El lock se libera al terminar
   o al cerrarse la conexion. No mantiene una transaccion abierta. Esta barrera
   coordina masters que ejecuten **esta version**; no coordina el ETL de
   fuentes ni versiones anteriores.
2. Prefect marca timeout del flow a los 150 min. Como un timeout del flow puede
   no interrumpir una sentencia o tarea bloqueada, un temporizador del proceso
   hijo Linux envia SIGTERM a los 165 min y SIGKILL 30 s despues si persiste.
   El cierre del proceso libera sus conexiones y locks en PostgreSQL. Si el
   servidor de base no detecta inmediatamente una conexion rota, puede haber
   una demora hasta la deteccion de red; no es un `pg_terminate_backend`.
3. Todas las conexiones creadas por PDD aplican `statement_timeout=30min`,
   `lock_timeout=30s`, `idle_in_transaction_session_timeout=10min` y
   `connect_timeout=10s`. `transactional_connection` conserva sus limites
   locales. El nombre de aplicacion identifica fuente/destino y TEST/PROD.
4. DAILY_DECAS registra hitos de lectura de stock, OC, espera/adquisicion del
   lock, calculo, persistencia y commit para localizar la fase lenta.
5. `tools/inspect_db_contention.py` lee `pg_stat_activity` y
   `pg_blocking_pids` en fuente y destino. Devuelve JSON y codigo 2 si detecta
   sentencia PDD de 20 min, espera de lock en una consulta de al menos 30 s,
   transaccion PDD inactiva de 2 min o proceso ajeno bloqueado por PDD.
   `query_age_seconds` es antiguedad de consulta, no duracion exacta de espera.
   No termina sesiones. Para alerta automatica debe ejecutarse fuera del
   worker (por ejemplo, temporizador cada 5 min) y enviar el codigo 2 a la
   supervision. La cuenta necesita visibilidad global `pg_read_all_stats` o
   equivalente para diagnosticar otras aplicaciones con fiabilidad.

El cron local sigue PROD 21:00 y TEST 22:15 ART. Si PROD sigue ocupado a las
22:15, TEST esperara como maximo hasta 22:30 y terminara con aviso; **no se
reintentara solo**. Esta decision evita dos masters simultaneos. Para que TEST
termine cada noche incluso cuando PROD demora mas de 75 min, definir un
disparador posterior al estado terminal de PROD o un reintento programado que
respete el cierre de fuentes y la fecha operativa. No cambiar el cron de TEST
a despues de medianoche sin comprobar la resolucion de fecha de negocio.

## Instalacion y verificacion

Copiar `pdd-backend-0.20.14.zip` y `.zip.sha256` a `/tmp` del servidor. En
TEST, como root:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.14.zip.sha256
unzip -p pdd-backend-0.20.14.zip tools/deploy_backend.sh > pdd-deploy-0.20.14.sh
test -s pdd-deploy-0.20.14.sh
bash pdd-deploy-0.20.14.sh TEST 0.20.14 stage
bash pdd-deploy-0.20.14.sh TEST 0.20.14 promote
bash pdd-deploy-0.20.14.sh TEST 0.20.14 deploy
bash pdd-deploy-0.20.14.sh TEST 0.20.14 status
```

Comprobar una corrida completa de TEST y revisar los hitos DAILY_DECAS y el
backlog. En PROD ejecutar las mismas cuatro fases reemplazando `TEST` por
`PROD`, luego comprobar version y worker. El script conserva una copia
`backend.prev-...` para rollback. Antes de promover, comprobar que el worker
instalado tiene la version esperada y que no haya corrida activa: el script
detiene el servicio, pero una corrida de process worker ya lanzada puede seguir
viva independientemente.

Consulta puntual en cada servidor, con el runtime correspondiente:

```bash
# TEST
cd /srv/PDD/backend
sudo -u pdd env HOME=/var/lib/pdd PDD_ENV_PATH=/etc/connexa/pdd-test.env \
  PDD_OPERATIONAL_TARGET_ENV=TEST PYTHONPATH=/srv/PDD/backend \
  /srv/PDD/.venv/bin/python tools/inspect_db_contention.py

# PROD
cd /srv/PDD/backend
env HOME=/root PDD_ENV_PATH=/etc/connexa/pdd-prod.env \
  PDD_OPERATIONAL_TARGET_ENV=PROD PYTHONPATH=/srv/PDD/backend \
  /srv/FORECAST/venv/bin/python tools/inspect_db_contention.py
```

Si reaparece una demora, capturar en el momento: JSON del inspector, logs del
flow, tiempos por hito, `pg_stat_activity`, `pg_locks` y plan del SQL que
este ejecutandose. No cancelar un backend PostgreSQL sin identificar su
transaccion, bloqueo y consecuencias de rollback.

## Primer despliegue en TEST, 25/11/2026

El operador verifico el SHA256 del ZIP y ejecuto `stage`, `promote`, `deploy`
y `status` en `diarco-test`. `stage` paso toda la suite de pytest, validacion
SQL y contrato operativo (`diarco_data` a `connexa_platform_test`). La version
0.20.14 quedo promovida con copia anterior en
`/srv/PDD/backend.prev-20261125-112238`. El worker `pdd-test-127` inicio
correctamente. Los deployments de precheck y master conservaron sus IDs,
quedaron `READY`, activos, y el master conserva el cron 22:15 ART.

Consulta a Prefect a las 11:24 ART: no habia masters TEST ni PROD en estado
RUNNING/PENDING. La ultima corrida TEST habia completado el 24/11 a las
23:52 ART, antes de instalar 0.20.14. Por tanto el despliegue y la carga del
codigo estan comprobados, pero el limite de ejecucion y los hitos nuevos aun
no fueron ejercitados en una corrida operativa. Verificar la proxima corrida
TEST tras el cierre de fuentes. La coordinacion entre ambientes solo sera
efectiva cuando PROD tambien ejecute 0.20.14.

## Despliegue en PROD, 25/11/2026

El operador verifico SHA256 y ejecuto `stage`, `promote`, `deploy` y `status`
en `diarco-ms`. Pasaron pytest, validacion SQL y contrato operativo
(`diarco_data` a `connexa_platform_ms`). PROD paso de 0.20.10 a 0.20.14;
la copia anterior quedo en `/srv/PDD/backend.prev-20261125-112957`. El worker
`pdd-diarco-prod` reinicio y quedo activo. Precheck y master conservaron
sus IDs, estado `READY`, colas PROD y horarios 17:00/21:00 ART.

El inspector PROD de las 11:31 ART no encontro sesiones PDD ni bloqueos
visibles. Informo `full_stats_visibility=false` en `diarco_data` y `true` en
`connexa_platform_ms`: el diagnostico de competencia con otras aplicaciones
en la fuente requiere una cuenta con `pg_read_all_stats` o equivalente.
Consulta a Prefect a las 11:32 ART: ninguno de los dos masters tenia corridas
RUNNING/PENDING. Ahora ambos servidores tienen 0.20.14, pero todavia falta
comprobar una corrida completa posterior al despliegue en cada ambiente.

La deuda y el backlog PROD del 24/11 seguian pendientes tras la cancelacion
de la corrida anterior; instalar el backend no los recalcula. La recuperacion
de esa fecha necesita una corrida controlada y verificacion de sus resultados.
