# Continuidad del backlog ante necesidades dirigidas sin contexto

## Decisión operativa

Desde el backend 0.20.11, una línea activa E/C/A que no tenga un par utilizable
en la corrida diaria de DAILY_DECAS no detiene la publicación del backlog. La
deuda D y las demás necesidades válidas se publican. La línea E/C/A afectada
queda abierta para corrección y no aparece en el backlog hasta que su par
vuelva a estar habilitado. El sistema no cancela registros de compradores.

Cada publicación registra el número de líneas omitidas, sus unidades, motivo
y listado completo en `stock_management.pdd_calculation_run.summary` bajo
`excluded_directed_lines`. Incrementa `warning_count` y emite el evento Prefect
`pdd.backlog.directed_lines_excluded`. El log de la tarea muestra una muestra
de hasta 20 líneas. Para recibir avisos fuera de Prefect hay que configurar
una Automation sobre ese evento.

Los motivos son `OUT_OF_SCOPE`, `DAILY_DECAS_BLOCKED` y
`PAIR_CONTEXT_MISSING`. Corregir el artículo/sucursal o la política Inventory
en el sistema fuente; después repetir el flujo diario. La siguiente corrida
incorporará automáticamente las líneas todavía abiertas si el contexto es
válido. El evento no autoriza excluir ni cancelar la necesidad en origen.

Este cambio cubre las necesidades E/C/A sin contexto. Las importaciones
Valkimia activas siguen bloqueadas hasta implementar su conciliación, porque
el backlog no puede descontar de forma fiable lo ya preparado.

## Consulta de auditoría

```sql
SELECT calculation_run_uuid, business_date, warning_count,
       summary->>'excluded_directed_count' AS lineas_omitidas,
       summary->>'excluded_directed_open_quantity' AS unidades_omitidas,
       summary->'excluded_directed_lines' AS detalle
FROM stock_management.pdd_calculation_run
WHERE run_type = 'PUBLISH' AND scope_id = '41:BACKLOG'
ORDER BY started_at DESC
LIMIT 10;
```

## Despliegue

El paquete es `pdd-backend-0.20.11.zip` con su archivo `.sha256`. Hay que
copiar **ambos archivos** a `/tmp` de cada servidor. `diarco-test` es TEST;
`diarco-ms` es PROD. Confirmar el servidor antes de ejecutar fases:

```bash
cd /tmp
hostname -f
ls -l pdd-backend-0.20.11.zip pdd-backend-0.20.11.zip.sha256
sha256sum -c pdd-backend-0.20.11.zip.sha256
unzip -p pdd-backend-0.20.11.zip tools/deploy_backend.sh > pdd-deploy-0.20.11.sh
test -s pdd-deploy-0.20.11.sh && bash -n pdd-deploy-0.20.11.sh
sudo bash /tmp/pdd-deploy-0.20.11.sh TEST 0.20.11 stage
sudo bash /tmp/pdd-deploy-0.20.11.sh TEST 0.20.11 promote
sudo bash /tmp/pdd-deploy-0.20.11.sh TEST 0.20.11 deploy
sudo bash /tmp/pdd-deploy-0.20.11.sh TEST 0.20.11 status
```

Ejecutar `PDD_OPERATIONAL_DAILY_MASTER` y comprobar su estado `Completed`, la
fecha de DAILY_DECAS y del backlog, los conteos de deuda y el resumen de
líneas omitidas. Probar con una línea E/C/A de prueba fuera de scope en TEST:
debe continuar con advertencia y la línea debe permanecer abierta. Sólo
después de esa comprobación, repetir los comandos en PROD cambiando `TEST`
por `PROD`; usar el mismo ZIP y SHA. No activar un segundo deployment diario.
