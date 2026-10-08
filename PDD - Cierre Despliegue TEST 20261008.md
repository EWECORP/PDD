# PDD — cierre de despliegue TEST 0.20.2 (08/10/2026)

## Resultado

- Worker `pdd-test-127` y cola homónima en estado `ONLINE` / `READY` tras instalar `diarco-pdd-backend 0.20.2` en `/srv/PDD/backend`.
- Corrida Prefect [`ec22d75e-3143-4a80-8c20-ca9bd9af05fb`](https://orquestador.connexa-cloud.com/runs/flow-run/ec22d75e-3143-4a80-8c20-ca9bd9af05fb): `Completed` el 08/10/2026 a las 18:01 ART, para fecha de negocio `2026-10-07`.
- Publicación de backlog `144f6311-f181-5283-80d9-cedc15dc1424`: `SUCCEEDED`, `is_current=true`, 13.146 líneas. `pdd_current_backlog_line` contiene 13.146 filas para esa fecha.

## Regularizaciones durante la validación

1. El scope `c533e7e7-3363-4dc3-8127-24f48fe33522` ya estaba materializado como `DRAFT` en TEST, mientras su versión analítica estaba `APPROVED`. Se promovió la fila operativa existente, conservando 2.524 artículos, 46.680 pares y checksum, y copiando fecha y aprobador del registro analítico.
2. El usuario confirmó que siete importaciones Valkimia `PENDING` eran pruebas descartables. Se cancelaron en una transacción controlada las importaciones 5–11, sus siete planes y viajes, nueve paradas y 1.589 líneas. Los siete mensajes de salida sin intentos pasaron a `DEAD_LETTER` con motivo auditado. Script reproducible: `cancel_test_valkimia_20261008.py`.
3. Una ejecución sin fecha explícita intentó procesar `2026-10-08` antes de que existiera el contrato de fuentes `READY` para esa fecha. La corrida de cierre se lanzó con `business_date=2026-10-07`, que sí tenía contrato `READY`.

## Límite operativo vigente

El último contrato `audit.pdd_source_sync_run` observado durante este cierre era `READY` para `2026-10-07`. La corrida automática de `2026-10-08` debe esperar su propio contrato `READY`; este cierre no acredita todavía esa fecha. La conciliación real con Valkimia sigue pendiente antes de habilitar importaciones activas en un flujo normal.

Quedan cuatro mensajes `VALKIMIA_LEGACY` antiguos en `PENDING`, todos con cero
intentos: tres pertenecen a importaciones 2–4 ya canceladas anteriormente y uno
no tiene importación vinculada por `payload_reference`. No bloquean el backlog,
pero deben revisarse antes de activar el adaptador outbound para evitar envíos
de artefactos históricos.
