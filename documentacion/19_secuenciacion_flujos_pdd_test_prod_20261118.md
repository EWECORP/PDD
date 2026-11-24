# Secuenciacion de flujos PDD: TEST y PROD

Revision de deployments Prefect del 18/11/2026, zona America/Argentina/Buenos_Aires.

| Proceso | Hora activa | Cola | Funcion |
| --- | --- | --- | --- |
| Retencion backtest TEST | 08:00 | pdd-test-127 | Depura detalle antiguo; independiente del diario |
| Conciliacion ventas semanal | Domingo 10:00 | dmz-diarco/default | Repara ventas historicas; revisar antes de sincronizacion dominical |
| Precheck Inventory TEST | 17:00 | pdd-test-127 | Alerta temprana, sin publicar deuda |
| Precheck Inventory PROD | 17:00 | pdd | Alerta temprana, sin publicar deuda |
| Sincronizacion de fuentes PDD | 18:30 | dmz-diarco/default | Publica contrato auditado READY/BLOCKED |
| Diario PROD | 21:00 | pdd | Calcula deuda y publica backlog PROD |
| Diario TEST | 22:15 | pdd-test-127 | Calcula deuda y publica backlog TEST |

Los dos prechecks simultaneos son admisibles: usan workers y destinos
operativos distintos y son principalmente lecturas. En las corridas recientes
duraron alrededor de un minuto. Ambos comparten la fuente `diarco_data`, asi
que un pequeño escalonamiento puede aliviar carga, pero no es una dependencia
funcional.

Los prechecks de las 17:00 suceden **antes** de la sincronizacion de las
18:30. Sirven para alertar temprano sobre Inventory, pero no certifican la
foto que usara el diario de esa noche. El diario ya valida el contrato de
fuentes y la cobertura Inventory antes de calcular. Mantener un control
posterior al READY de fuentes es recomendable si se requiere alerta antes del
diario, sin perder la alerta temprana.

La sincronizacion de fuentes tardo 98-106 minutos en las ultimas corridas
exitosas, con maximos recientes mayores. PROD tardo cerca de 63 minutos en
sus ultimas corridas completas. Por eso la separacion 21:00/22:15 deja un
margen habitual de unos 12 minutos tras PROD, pero **no garantiza** ausencia
de solapamiento. TEST y PROD usan colas distintas; el pool no tiene limite
global de concurrencia. Una demora de fuentes puede alcanzar tambien a PROD.

## Secuencia operativa requerida

1. La sincronizacion `PDD_SOURCE_DAILY_MASTER_PROD` finaliza con contrato
   `READY` para la fecha operativa y cierre previstos.
2. El control de Inventory de la foto nueva informa estado y brechas a
   operadores. El precheck anticipado de las 17:00 sigue siendo util.
3. PROD ejecuta el diario una sola vez para esa fecha. Si no hay contrato
   READY, el proceso espera/reintenta con plazo acotado o alerta sin calcular.
4. TEST inicia despues de que PROD llegue a estado terminal si se quiere
   evitar trabajo simultaneo en `diarco_data`; un fallo de PROD debe alertar
   y no debe borrar ni cancelar la corrida TEST.
5. Cada ambiente verifica su propio `DAILY_DECAS` y backlog vigentes antes de
   considerar completa la operacion.

El orden 1-4 no esta garantizado por cron. Para automatizarlo estrictamente
se necesita un orquestador/evento de finalizacion o un control compartido de
concurrencia y fecha. Mantener los cron actuales como horarios orientativos
hasta probar ese mecanismo. No usar el estado verde del precheck de las 17:00
como sustituto del contrato READY posterior.

## Riesgos de configuracion observados

- Los cron efectivos del 18/11 eran PROD 21:00 y TEST 22:15, mientras los YAML
  locales decian 21:15 y 21:45. Se alinearon `prefect.prod.yaml` y
  `prefect.yaml` con el estado efectivo, conservando los slugs de schedule
  existentes para evitar duplicados en un proximo deployment.
- Varias deployments manuales con nombre `*_TEST_MANUAL` aun figuran en la
  cola `pdd` de PROD en Prefect, aunque el YAML local de TEST dice
  `pdd-test-127`: `PDD_DAILY_DECAS_TEST_MANUAL`,
  `PDD_PUBLISH_BACKLOG_TEST_MANUAL`, `PDD_PUBLISH_ITEM_LOGISTICS_TEST_MANUAL`
  y `PDD_PUBLISH_PDVB_TEST_MANUAL`. No estan programadas. No lanzarlas hasta
  corregir la cola efectiva y comprobar las variables de ambiente.
- Los monitores semanales TEST/PROD tienen schedule inactivo; DESA permanece
  suspendido. No participan en la cadena diaria actual.

Esta revision actualiza archivos locales y documentacion. No modifica las
programaciones activas de Prefect ni el ZIP 0.20.12 ya instalado en TEST.
