# PDD: control anticipado de Inventory y continuidad parcial

Fecha: 29/10/2026. Alcance: TEST y PROD; DESA permanece suspendido.

## Situación observada

El scope activo v7 (`38af3a1d-4d9f-42a3-9ab1-b6ae224b3551`) tiene 44.886
pares. La lectura de `inventory.inv_planning_parameters_v` mostró:

| Ambiente | Sin fila de reposición | Fila inactiva | Estado con límite 0,5% / 100 |
|---|---:|---:|---|
| TEST | 100 | 735 | Bloqueado: 835 > 100 |
| PROD | 99 | 0 | Puede continuar omitiendo 99 |

Todos esos pares tienen producto, sucursal y `inv_product_site`. La vista excluye
las filas de `inventory.inv_product_site_replenishment` con `active=false`. No
debe confundirse `inv_product_site.active` o `active_for_purchase` con el estado
de la política: son decisiones distintas. Los 735 pares inactivos de TEST tienen
ambos estados del vínculo habilitados; su desactivación requiere revisión de
auditoría y del responsable de Inventory.

La fuente viva del 29/10 difiere del scope v7 en +2 y -8 pares. El preflight
también inspecciona esa membresía candidata, sin capturar ni activar un scope.
Sobre los 44.880 pares candidatos, TEST muestra 837 faltantes (100 inexistentes,
737 inactivos) y PROD 99 inexistentes. Las 735 políticas inactivas del scope
activo TEST fueron actualizadas por procesos ETL de septiembre; `updated_by`
indica el último escritor, no prueba quién las desactivó. Consultar la auditoría
antes de decidir una reactivación masiva.
El mantenimiento diario ahora detecta altas/bajas ordinarias además de cambios
de sucursales, y conserva los controles de churn, stock, backfill y activación.

## Comportamiento del nuevo proceso

`PDD_INVENTORY_COVERAGE_PRECHECK` en TEST y
`PDD_INVENTORY_COVERAGE_PRECHECK_PROD` en PROD se programan a las **17:00 ART**.
Comparan el scope activo y la membresía viva que se capturaría en una renovación
con las políticas de Inventory. Publican todos los pares incompletos en los
logs, intentan crear un artefacto de Prefect con un resumen y emiten un evento
`pdd.inventory.coverage.warning_continue` o `pdd.inventory.coverage.blocked`.
Un cambio de membresía emite además `pdd.inventory.coverage.scope_changed`.
El preflight sólo lee tablas persistentes; usa tablas temporales en la fuente y
termina con `ROLLBACK`.
En 0.20.9 el servidor Prefect respondió HTTP 500 al crear el artefacto y
ocultó el bloqueo real de 837 pares. Desde 0.20.10, un error del artefacto o
del evento queda como advertencia; el estado final refleja la cobertura de
Inventory. Los logs enumeran todos los pares en lotes de 50, aun cuando el
artefacto no esté disponible.

El orquestador diario repite el control sobre el scope efectivo antes de preparar
features y PDVB. Puede continuar únicamente si los pares incompletos no superan
**simultáneamente 0,5% del scope y 100 pares**. Las variables
`PDD_INVENTORY_MAX_EXCLUDED_PERCENT` y `PDD_INVENTORY_MAX_EXCLUDED_PAIRS` permiten
reducir esos límites, incluido cero; el código rechaza valores mayores. El
límite efectivo es `min(100, floor(scope_pairs * 0,5 / 100))` por defecto.

Los pares sin parámetro activo o con días inválidos quedan fuera de las
posiciones y necesidades automáticas de `DAILY_DECAS`, y por ello fuera del
backlog automático. La corrida guarda cada artículo/sucursal y motivo en
`stock_management.pdd_calculation_run.summary.excluded_inventory_pairs` y en
el detalle de su snapshot `INVENTORY_PLANNING_PARAMETERS`. El checksum de
Inventory forma parte del identificador de la etapa diaria: una corrección de
política permite una corrida nueva para la misma fecha. Las políticas válidas
con `product_site.active=false` o `active_for_purchase=false` conservan el
comportamiento previo: posición `BLOCKED`, necesidad nula y sin backlog.

Una necesidad dirigida E/C/A activa sobre un par incompleto bloquea la
continuación, incluso dentro del límite numérico. El preflight la detecta para
la fecha corriente y la corrida diaria vuelve a verificarla antes de escribir.

## Decisión operativa

1. Abrir el artefacto del preflight a partir de las 17:00 y revisar conteos,
   motivos y pares. Un estado `BLOCKED` produce corrida roja. Un estado
   `WARNING_CONTINUE` produce advertencia y evento, pero la corrida termina
   correctamente.
2. **Esperar:** poner ambos límites en cero para exigir cobertura total antes de
   la planificación, o detener temporalmente la programación diaria.
3. **Corregir:** conciliar altas faltantes en
   `inventory.inv_product_site_replenishment` desde la captura validada de SGM.
   El cargador `cargas_inventory/load_environment.py` inserta faltantes pero no
   reactiva políticas existentes ni sobrescribe valores administrados.
   Investigar `inventory.inv_planning_parameter_audit`, `updated_by` y
   `updated_at` antes de reactivar las 735 de TEST.
4. **Continuar con exclusión acotada:** si no hay necesidad dirigida y el total
   cae bajo el límite, ejecutar el flujo diario. Revisar después el resumen de
   `DAILY_DECAS` y resolver los pares para la siguiente planificación.
5. **Excluir del scope por decisión de negocio:** cambiar la elegibilidad en la
   fuente maestra y renovar el scope bajo sus controles. No eliminar a mano
   filas de `dm_pdd_scope_pair` ni imputar días de stock en PDD.

Configurar en Prefect una Automation que notifique a los operadores por los
eventos `pdd.inventory.coverage.blocked`,
`pdd.inventory.coverage.warning_continue` y
`pdd.inventory.coverage.scope_changed`. El código emite los eventos, pero
la entrega de correo/Slack depende de esa Automation y del canal configurado.

## Validación y despliegue

En TEST, instalar el backend y desplegar `prefect.yaml`; ejecutar primero el
preflight manualmente. Con la membresía candidata observada debe informar 837
faltantes y fallar por superar el
límite. Corregir Inventory hasta quedar por debajo de 100 y ejecutar de nuevo;
después probar `PDD_OPERATIONAL_DAILY_MASTER` y comprobar la lista de exclusiones
en el resumen de `DAILY_DECAS` y el backlog. En PROD, repetir el preflight con
el paquete ya validado en TEST antes de activar la programación del nuevo
deployment. Con los datos observados, PROD informa 99 faltantes y ningún par
con necesidad dirigida activa; sólo después de verificar ese resultado se debe
probar el flujo diario.

El artefacto de despliegue `pdd-backend-0.20.10.zip` se entrega con SHA256 en
`pdd-backend-0.20.10.zip.sha256`. Conserva la funcionalidad 0.20.7 y agrega
el script reutilizable. El ZIP incluye
`tools/deploy_backend.sh`, reutilizable para releases posteriores:
`stage` comprueba SHA256, versión y rutas del ZIP, ejecuta pytest,
`validate_sql.py` y `validate_operational.py`; `promote` conserva el backend
anterior y recupera el servicio si falla la promoción; `deploy` actualiza sólo
el preflight y el orquestador diario del ambiente indicado; `status` verifica
versión y worker. Cada paso es explícito y no ejecuta corridas de negocio.

### TEST

Copiar ZIP y SHA a `/tmp` del servidor TEST. Ejecutar fuera de una corrida
activa del worker:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.10.zip.sha256
unzip -p pdd-backend-0.20.10.zip tools/deploy_backend.sh \
  > /tmp/pdd-deploy-0.20.10.sh
sudo bash /tmp/pdd-deploy-0.20.10.sh TEST 0.20.10 stage
sudo bash /tmp/pdd-deploy-0.20.10.sh TEST 0.20.10 promote
sudo bash /tmp/pdd-deploy-0.20.10.sh TEST 0.20.10 deploy
sudo bash /tmp/pdd-deploy-0.20.10.sh TEST 0.20.10 status
```

La suite omite las pruebas de `cargas_inventory` si ese proyecto no está
instalado en `/srv/PDD`; esa ausencia no bloquea el despliegue. No eliminar
`/srv/PDD/backend.prev-*`; el nombre del
backup aparece en `PROMOTED_OK`. Inspeccionar en Prefect el nuevo deployment
`PDD_INVENTORY_COVERAGE_PRECHECK` y lanzarlo manualmente sin parámetros. Con
los datos observados, debe registrar 837 faltantes y terminar en `Failed` por
superar el límite: ese resultado valida el control. Regularizar Inventory y
repetir hasta `READY` o `WARNING_CONTINUE`; luego probar
`PDD_OPERATIONAL_DAILY_MASTER` y comprobar el backlog.

### PROD

Promover sólo después de que TEST complete el flujo diario. Copiar el mismo
ZIP y SHA a `/tmp` de PROD y ejecutar como root:

```bash
cd /tmp
sha256sum -c pdd-backend-0.20.10.zip.sha256
unzip -p pdd-backend-0.20.10.zip tools/deploy_backend.sh \
  > /tmp/pdd-deploy-0.20.10.sh
bash /tmp/pdd-deploy-0.20.10.sh PROD 0.20.10 stage
bash /tmp/pdd-deploy-0.20.10.sh PROD 0.20.10 promote
bash /tmp/pdd-deploy-0.20.10.sh PROD 0.20.10 deploy
bash /tmp/pdd-deploy-0.20.10.sh PROD 0.20.10 status
```

El script respeta el runtime real de PROD: `/srv/FORECAST/venv`,
`/etc/connexa/pdd-prod.env`, usuario root y
`prefect-worker-pdd.service`. Durante pytest usa una copia temporal de la
configuración sin permiso de escritura a PROD y la elimina al salir. Los dos
validadores posteriores usan la configuración productiva y terminan con
`ROLLBACK`. Ejecutar manualmente `PDD_INVENTORY_COVERAGE_PRECHECK_PROD` y
revisar artefacto/resultado antes de probar
`PDD_OPERATIONAL_DAILY_MASTER_PROD`. Con la foto observada hay 99 faltantes,
ninguna necesidad dirigida afectada y estado `WARNING_CONTINUE`; volver a
comprobarlo en el momento del despliegue. El SHA se genera con fin de línea
Unix, compatible con `sha256sum -c`.

La verificación de las 17:00 es una alerta anticipada: si SGM o Inventory
cambian luego, la corrida diaria usa su propia lectura actual. Una política de
Inventory puede corregirse y provocar una nueva versión de DAILY_DECAS/BACKLOG
para la misma fecha mediante `force=true`; la publicación vigente anterior se
mantiene hasta que la nueva termine correctamente.
