# Especificación de Requerimiento de Software

Sistema: Planificación de la Distribución sobre Connexa  
Version: 1.0  
Fecha: 2026-06-10  
Estado: Borrador listo para refinamiento técnico  
Destino: Equipo de desarrollo, integraciones, datos, QA y operación

---

## 1. Propósito

Este documento define los requerimientos de software para construir en Connexa el nuevo sistema de Planificación de la Distribución, cuyo objetivo es centralizar la planificación, publicación, trazabilidad y replanificación de transferencias CD -> sucursal.

El sistema debe reemplazar el esquema actual de múltiples orígenes de transferencia por un modelo gobernado en Connexa, donde:

- Connexa es la fuente de verdad de necesidades, planes, backlog, ejecuciones y estados.
- Valkimia es el ejecutor logístico y proveedor del stock neto disponible.
- SGM deja de publicar transferencias directamente a Valkimia en el modelo objetivo y pasa a informar necesidades hacia Connexa.

La especificación está orientada a que desarrollo pueda iniciar análisis técnico, descomposición de historias, diseño de servicios, modelo de datos, integraciones y plan de pruebas.

---

## 2. Alcance

### 2.1 Alcance incluido

El sistema debe cubrir:

- Registro y consolidación de necesidades de transferencia.
- Gestión de backlog pendiente.
- Planificación de transferencias según stock neto disponible.
- Priorización y asignación de stock por SKU-sucursal.
- Publicación idempotente de transferencias hacia Valkimia.
- Seguimiento de ejecución logístico por cabecera y línea.
- Replanificación automática de pendientes y rechazos.
- Reconciliación de ejecuciones externas durante la convivencia con SGM.
- Auditoria completa de eventos y cambios de estado.
- Tableros operativos y KPIs básicos.
- Parametrización de reglas de planificación por familia/CD.

### 2.2 Fuera de alcance inicial

Queda fuera de la primera version:

- Optimización avanzada de rutas.
- Cubicaje completo por camión.
- Costeo logístico.
- Re-optimización intradía compleja basada en múltiples CDs.
- Motor predictivo de demanda nuevo.
- Sustitución de artículos.
- Confirmación contable/fiscal de transferencias.

Estos puntos podrán incorporarse como evolución posterior una vez estabilizado el ciclo Need -> Plan -> Execution -> Backlog.

---

## 3. Glosario

| Termino | Definición |
| --- | --- |
| Need | Necesidad consolidada de transferencia para CD, sucursal, SKU y bucket. |
| Backlog | Cantidad pendiente de satisfacer: `qty_need - qty_fulfilled`. |
| Plan | Corrida de planificación generada por Connexa. |
| PlanLine | Decisión de planificación para una línea SKU-sucursal. |
| Execution | Transferencia publicada a Valkimia o absorbida para seguimiento. |
| ExecutionLine | Línea logística por SKU dentro de una ejecución. |
| ExternalExecution | Transferencia detectada en Valkimia que no fue publicada por Connexa. |
| SND | Stock Neto Disponible informado por Valkimia. |
| ACO | Reserva/acopio logístico en Valkimia. |
| Bucket | Ventana funcional de consolidación de necesidades, por ejemplo, día o AM/PM. |
| Idempotencia | Capacidad de reenviar una solicitud sin crear duplicados. |

---

## 4. Actores y sistemas involucrados

| Actor/Sistema | Responsabilidad |
| --- | --- |
| Connexa | Orquestador único de planificación, backlog, publicación y trazabilidad. |
| Valkimia | Ejecutor logístico; informa stock neto, estados y cantidades ejecutadas. |
| SGM | Origen transitorio de necesidades; no publicador en modelo objetivo. |
| Operación CD | Ejecuta procesos físicos de acopio, picking y despacho. |
| Sucursal | Recibe mercadería y confirma recepción cuando aplique. |
| IT Integraciones | Opera conectores, errores, reintentos y monitoreo técnico. |
| Planificación/Abastecimiento | Configura reglas, revisa backlog y prioridades. |

---

## 5. Vista general de solución

El sistema se organiza en cinco capacidades principales:

1. Ingesta y consolidación de necesidades.
2. Planificación factible basada en stock neto.
3. Publicación idempotente a Valkimia.
4. Seguimiento de ejecución y actualización de saldos.
5. Replanificación y control de backlog.

Flujo objetivo:

```text
Orígenes de necesidad
  -> Connexa Need / Backlog
  -> Planificador Connexa
  -> Consulta SND Valkimia
  -> PlanLine
  -> Publicación idempotente
  -> Execution / ExecutionLine
  -> Tracking Valkimia
  -> Cierre o replanificación
```

Regla arquitectónica principal:

> Ninguna necesidad, plan o ejecución debe desaparecer físicamente por falta de stock o error operativo. Todo debe quedar trazado por estado y evento.

---

## 6. Requerimientos funcionales

### RF-01. Gestión de necesidades

El sistema debe permitir crear necesidades de transferencia desde Connexa, SGM, cargas manuales o ajustes operativos.

Criterios:

- Cada necesidad debe identificarse por `cd_id`, `sucursal_id`, `sku_id` y `need_bucket_date`.
- Si ingresa una necesidad con la misma clave funcional, el sistema debe consolidarla.
- La consolidación debe registrar cada origen en `transfer.need_source`.
- La necesidad debe iniciar en estado `NEED_OPEN` o `NEED_CONSOLIDATED`.
- La necesidad no debe eliminarse físicamente.

### RF-02. Consolidación de necesidades

El sistema debe soportar dos modos de merge:

- Incremental: suma `qty_incoming` a `qty_need`.
- Recalculado: reemplaza o toma máximo según regla del origen.

Criterios:

- Forecast recalculado debe poder operar con modo reemplazo/máximo.
- Eventos operativos, SGM o manuales deben poder operar con modo incremental.
- Toda consolidación debe generar evento `NeedMerged`.

### RF-03. Estados de Need

El sistema debe administrar estados de Need mediante catalogo.

Estados mínimos:

- `NEED_OPEN`
- `NEED_CONSOLIDATED`
- `NEED_PARTIALLY_PLANNED`
- `NEED_FULLY_PLANNED`
- `NEED_PARTIALLY_EXECUTING`
- `NEED_FULLY_EXECUTING`
- `NEED_PARTIALLY_FULFILLED`
- `NEED_FULFILLED`
- `NEED_CANCELLED`
- `NEED_EXPIRED`

Criterios:

- Todo cambio de estado debe registrarse en `transfer.event_log`.
- No debe permitirse `NEED_FULFILLED` si `qty_fulfilled < qty_need`.

### RF-04. Backlog operativo

El sistema debe calcular backlog por necesidad.

Formula:

```text
backlog_qty = qty_need - qty_fulfilled
```

Criterios:

- Una Need con `backlog_qty > 0` debe estar disponible para planificación salvo hold, expiración, cancelación o ventana futura.
- El sistema debe registrar `next_replan_at`, `replan_attempts_total` y `current_retry_streak`.
- Una línea rechazada por stock debe volver al backlog.

### RF-05. Hold operativo

El sistema debe permitir poner una Need en espera manual.

Criterios:

- Debe registrar `hold_reason_code` y `hold_reason_detail`.
- Mientras tenga hold activo, no debe ser elegible para planificación.
- La liberación del hold debe generar evento.

### RF-06. Consulta de stock neto disponible

El sistema debe consultar a Valkimia el stock neto disponible por CD y lista de SKU antes de planificar.

Criterios:

- Debe invocar la interfaz V-01 `POST /v1/stock/net-available` o mecanismo equivalente.
- Debe enviar `cd_id`, `sku_ids`, `as_of_ts` opcional e `include_components`.
- Debe soportar batch máximo sugerido de 2.000 SKU.
- Debe persistir `stock_net_available`, `stock_snapshot_ts` y `stock_version` en las PlanLines.
- No debe planificar líneas con SND menor o igual a cero.

### RF-07. Validación de stock neto

El sistema debe validar la consistencia básica del SND.

Criterios:

- Si Valkimia devuelve stock neto negativo, Connexa debe tratarlo como cero y generar alerta/evento.
- Si un SKU se informa en `missing_skus`, no debe planificarse.
- Si `include_components=true`, debe poder auditar componentes de stock cuando estén disponibles.

### RF-08. Corrida de planificación

El sistema debe crear una corrida `transfer.plan` por CD y ventana de ejecución.

Criterios:

- El plan debe registrar `cd_id`, `plan_run_ts`, `plan_status`, `allocation_strategy_code`, `planner_mode` y usuario/proceso creador.
- Si no hay Needs elegibles, debe cerrar el plan con estado `NO_WORK`.
- Si hay Needs pero sin stock o bloqueadas, debe cerrar con estado equivalente a `NO_STOCK_OR_BLOCKED`.

### RF-09. Selección de necesidades elegibles

El planificador debe seleccionar Needs que cumplan:

- `qty_need > qty_fulfilled`.
- Sin hold activo.
- `next_replan_at` nulo o menor/igual a la fecha actual.
- Estado no final.
- No cancelada ni expirada.

Criterios:

- La selección debe poder filtrarse por CD, familia y bucket.
- Debe respetar bloqueo por ejecución externa activa.

### RF-10. Calculo de prioridad

El sistema debe calcular `priority_score` para ordenar asignaciones.

Componentes sugeridos:

- `manual_priority`.
- `sla_urgency`.
- `break_risk`.
- `sales_rate_norm`.
- `promo_boost`.
- `backlog_age_norm`.
- `retry_penalty`.

Criterios:

- Los pesos deben ser configurables por familia en `transfer.cfg_family_rule`.
- Si faltan datos tienda, ventas o promo, el calculo debe operar en modo degradado.
- Si falta SND, la planificación no debe continuar para esos SKU.

### RF-11. Estrategias de asignación

El sistema debe soportar al menos:

- `PRIORITY`.
- `FIFO`.
- `FAIR_SHARE`.

Criterios:

- La estrategia por defecto debe ser configurable por familia.
- `FAIR_SHARE` debe activarse cuando exista bajo stock y múltiples sucursales demandando el mismo SKU, según parámetros.
- La cantidad planificada no puede superar el backlog de la Need.
- La suma de cantidades planificadas para un SKU no puede superar el SND disponible en la corrida.

### RF-12. Creación de PlanLine

El sistema debe crear `transfer.plan_line` para cada decisión de asignación.

Criterios:

- Debe vincular `plan_id` y `need_id`.
- Debe registrar `qty_backlog_at_plan`, `qty_planned`, snapshot de SND, estrategia y score.
- Debe usar estado inicial `PLAN_PLANNED` cuando tenga cantidad a publicar.
- Debe registrar motivo cuando no sea planificable por stock o regla.

### RF-13. Anti-duplicacion pre-publicacion

Antes de publicar a Valkimia, el sistema debe verificar ejecuciones activas.

Criterios:

- Debe invocar V-02 `GET /v1/transfers/active` o mecanismo equivalente.
- Debe construir una clave `cd_id + sucursal_id + sku_id`.
- Si existe ejecución activa para la misma clave, no debe publicar una nueva línea.
- Debe marcar la Need con `blocked_by_external_execution = true`.
- Debe crear o actualizar `ExternalExecution` cuando corresponda.

Estados activos normalizados:

- `ACCEPTED`
- `RESERVED_ACO`
- `PICKING`
- `PACKED`
- `SHIPPED`

### RF-14. Publicación idempotente

El sistema debe publicar transferencias a Valkimia mediante clave idempotente.

Criterios:

- Debe generar `connexa_execution_id` UUID por cabecera.
- Debe generar `connexa_line_id` UUID por línea.
- Debe agrupar líneas por `cd_id` y `sucursal_id`.
- Debe invocar V-03 `POST /v1/transfers` o mecanismo equivalente.
- Si se reintenta el mismo `connexa_execution_id`, no debe crear duplicados.

### RF-15. Manejo de aceptación total

Cuando Valkimia acepte una publicación completa, Connexa debe:

- Crear o actualizar `transfer.execution`.
- Persistir `valkimia_transfer_id`.
- Crear `transfer.execution_line`.
- Persistir `valkimia_line_id`.
- Actualizar estado a `EXEC_ACCEPTED`.
- Incrementar `qty_published` o `qty_accepted` según corresponda.
- Registrar evento.

### RF-16. Manejo de aceptación parcial

Cuando Valkimia acepte algunas líneas y rechace otras, Connexa debe:

- Mantener la ejecución creada.
- Actualizar líneas aceptadas como `EXEC_ACCEPTED`.
- Actualizar líneas rechazadas como `EXEC_REJECTED_STOCK` o `EXEC_REJECTED_RULE`.
- Reincorporar líneas rechazadas al backlog.
- Registrar `reject_reason_code`.

### RF-17. Manejo de rechazo total

Cuando Valkimia rechace la transferencia completa por stock o regla, Connexa debe:

- Registrar la ejecución y su respuesta.
- No perder las Needs asociadas.
- Revertir o no incrementar cantidades publicadas.
- Calcular `next_replan_at` con backoff cuando sea Reintentable.
- Registrar evento de rechazo.

### RF-18. Seguimiento de ejecución

El sistema debe consultar estados de Valkimia por transferencia.

Criterios:

- Debe invocar V-04 `GET /v1/transfers/{valkimia_transfer_id}` o mecanismo equivalente.
- Debe actualizar estado de cabecera y líneas.
- Debe actualizar cantidades `qty_prepared`, `qty_shipped`, `qty_delivered`.
- Debe registrar eventos de cambio.
- Debe ser tolerante a respuestas sin lista de eventos, usando `status` y `last_update_ts`.

### RF-19. Consulta incremental de eventos

Si Valkimia lo permite, el sistema debe soportar V-05 para eventos incrementales.

Criterios:

- Debe de duplicar por `event_id`.
- Debe persistir `next_since_ts` o cursor equivalente.
- Debe poder convivir con polling.

### RF-20. Replanificación automática

El sistema debe replanificar Needs pendientes según eventos y tiempo.

Disparadores:

- Job programado por CD/familia.
- Rechazo de ejecución.
- Liberación o actualización de stock, si existe evento.
- Vencimiento de `next_replan_at`.

Criterios:

- Debe aplicar backoff exponencial.
- Debe respetar máximos configurables por familia.
- Debe resetear `current_retry_streak` cuando una línea sea aceptada o cumplida, según regla configurada.

### RF-21. Reconciliación de ejecuciones externas

Durante la transición, el sistema debe registrar transferencias existentes no creadas por Connexa.

Criterios:

- Debe crear `transfer.external_execution` y `transfer.external_execution_line`.
- Debe vincularlas a Needs mediante `transfer.need_external_link` cuando exista match.
- Debe operar inicialmente en modo conservador: bloquear duplicación sin descontar backlog hasta despacho/entrega.
- Debe medir hits de duplicación.

### RF-22. Cancelación y expiración

El sistema debe permitir cancelar o expirar Needs y ejecuciones según reglas operativas.

Criterios:

- Cancelar Need debe impedir nuevas planificaciones.
- Expirar Need debe impedir nuevas planificaciones salvo reapertura autorizada.
- Si ya existe ejecución publicada, la cancelación debe respetar capacidades reales de Valkimia.
- Toda cancelación o expiración debe registrar motivo y evento.

### RF-23. Auditoria universal

El sistema debe registrar toda transición relevante en `transfer.event_log`.

Criterios:

- Debe registrar entidad, id, evento, estado anterior, estado nuevo, sistema origen, timestamp y payload.
- La tabla debe ser append-only a nivel funcional.
- Debe permitir trazabilidad desde Need hasta ExecutionLine.

### RF-24. Parametrización

El sistema debe administrar parámetros sin cambios de código.

Parámetros mínimos:

- Modo de bucket.
- Estrategia de asignación.
- Pesos de prioridad.
- Ventanas SLA.
- Backoff base y máximo.
- Umbral de bajo stock.
- Unidad mínima de transferencia.
- Estados activos Valkimia.
- Mapping de estados externos.

### RF-25. Tablero operativo mínimo

El sistema debe exponer datos para tablero operativo.

KPIs mínimos:

- Backlog total por CD, familia y sucursal.
- Backlog aging p95.
- Publicaciones exitosas.
- Rechazos por stock.
- Transferencias por estado.
- Ejecuciones activas.
- Duplicaciones evitadas.
- Ejecuciones colgadas.
- Fill rate de transferencias.

---

## 7. Requerimientos de datos

### RD-01. Esquema PostgreSQL

El sistema debe usar un esquema dedicado `transfer` en PostgreSQL o esquema equivalente definido por arquitectura.

Tablas mínimas:

- `transfer.need`
- `transfer.need_source`
- `transfer.plan`
- `transfer.plan_line`
- `transfer.execution`
- `transfer.execution_line`
- `transfer.external_execution`
- `transfer.external_execution_line`
- `transfer.need_external_link`
- `transfer.event_log`
- `transfer.cfg_family_rule`
- `transfer.cfg_status_mapping`

### RD-02. Catálogos

El sistema debe contar con catálogos de:

- Estados de Need.
- Estados de PlanLine.
- Estados de Execution.
- Origen de Need.
- Estrategias de asignación.

### RD-03. Identificadores

El sistema debe usar UUID para claves técnicas internas.

Criterios:

- `connexa_execution_id` debe ser único.
- `connexa_line_id` debe ser único.
- `valkimia_transfer_id` debe ser único cuando exista.
- `valkimia_line_id` debe ser único cuando exista.

### RD-04. Cantidades

Las cantidades deben persistirse con precisión decimal.

Criterios:

- Usar tipo equivalente a `numeric(18,4)`.
- No permitir cantidades negativas.
- Validar `qty_planned <= qty_backlog_at_plan`.
- Validar consistencia de saldos de Need.

### RD-05. Vistas operativas

El sistema debe proveer al menos:

- Vista de backlog abierto.
- Vista de ejecuciones activas.
- Vista o consulta de planificaciones recientes.
- Vista o consulta de errores/rechazos.

---

## 8. Interfaces externas

### IF-01. V-01 Stock neto disponible

Endpoint lógico:

```text
POST /v1/stock/net-available
```

Request mínimo:

- `request_id`
- `cd_id`
- `as_of_ts`
- `sku_ids`
- `include_components`

Response mínimo:

- `cd_id`
- `calculated_at_ts`
- `stock_version`
- `items[].sku_id`
- `items[].stock_net_available`
- `items[].uom`
- `items[].components`
- `missing_skus`

### IF-02. V-02 Ejecuciones activas

Endpoint lógico:

```text
GET /v1/transfers/active
```

Request mínimo:

- `cd_id`
- `since_ts`
- `status_in`
- `include_lines`

Response minimo:

- `valkimia_transfer_id`
- `cd_id`
- `sucursal_id`
- `status`
- `created_at_ts`
- `last_update_ts`
- `lines`

### IF-03. V-03 Publicación de transferencia

Endpoint lógico:

```text
POST /v1/transfers
```

Request minimo:

- `connexa_execution_id`
- `plan_id`
- `cd_id`
- `sucursal_id`
- `priority`
- `created_at_ts`
- `requested_ship_window`
- `lines[].connexa_line_id`
- `lines[].sku_id`
- `lines[].uom`
- `lines[].qty_requested`

Response minimo:

- `connexa_execution_id`
- `valkimia_transfer_id`
- `accepted`
- `status`
- `received_at_ts`
- `reason_code`
- `lines[].connexa_line_id`
- `lines[].valkimia_line_id`
- `lines[].sku_id`
- `lines[].status`
- `lines[].reason_code`

### IF-04. V-04 Tracking por transferencia

Endpoint lógico:

```text
GET /v1/transfers/{valkimia_transfer_id}
```

Response minimo:

- `valkimia_transfer_id`
- `cd_id`
- `sucursal_id`
- `status`
- `created_at_ts`
- `last_update_ts`
- `lines`
- `events` opcional

### IF-05. V-05 Eventos incrementales

Endpoint lógico opcional:

```text
GET /v1/transfers/events
```

Uso:

- Reducir polling.
- Deduplicar por `event_id`.
- Avanzar por `next_since_ts`.

---

## 9. Requerimientos no funcionales

### RNF-01. Trazabilidad

El sistema debe permitir reconstruir el ciclo completo de una línea desde Need hasta entrega o cancelación.

### RNF-02. Idempotencia

Toda publicación a Valkimia debe ser idempotente por `connexa_execution_id`.

### RNF-03. Performance

El sistema debe soportar planificación batch por CD.

Objetivos iniciales:

- Stock neto: batches de hasta 2.000 SKU por request.
- Publicación: hasta 2.000 líneas por request, recomendado operativo menor a 500.
- Consultas de backlog con índices por CD, SKU, sucursal, estado y `next_replan_at`.

### RNF-04. Disponibilidad operativa

Fallas temporales de Valkimia no deben perder datos.

Criterios:

- Las publicaciones fallidas por error técnico deben quedar Reintentable.
- Los rechazos por stock deben tratarse como negocio, no como error técnico.

### RNF-05. Seguridad

El sistema debe controlar acceso por rol.

Roles mínimos:

- Administrador.
- Planificador.
- Operador CD.
- Consulta/auditoria.
- Soporte IT.

### RNF-06. Observabilidad

El sistema debe generar métricas y logs técnicos.

Métricas mínimas:

- Latencia por interfaz.
- Tasa de error por interfaz.
- Reintentos ejecutados.
- Publicaciones exitosas/fallidas.
- Rechazos por stock.
- Backlog aging.

### RNF-07. Configurabilidad

Reglas de score, backoff, estados activos y familias deben modificarse por datos/configuración, no por código.

### RNF-08. Reprocesabilidad

El sistema debe permitir reprocesar:

- Respuestas de publicación.
- Eventos de tracking.
- Reconciliaciones externas.
- Corridas de planificación fallidas, sin duplicar ejecuciones.

---

## 10. Políticas de errores, timeouts y reintentos

### PE-01. Timeouts sugeridos

| Interfaz | Timeout sugerido |
| --- | --- |
| V-01 Stock neto batch | 10 a 20 segundos |
| V-03 Publicación | 10 segundos |
| V-04 Tracking | 5 segundos |

### PE-02. Reintentos

Connexa debe reintentar solo ante:

- `503 DEPENDENCY_UNAVAILABLE`
- `429 RATE_LIMIT`
- `500 INTERNAL_ERROR`, máximo 2 reintentos
- Timeout técnico

Connexa no debe reintentar automáticamente ante:

- `400 INVALID_REQUEST`
- `422 UNPROCESSABLE_RULE`
- `REJECTED_STOCK`

### PE-03. Rate limits sugeridos

| Interfaz | Limite sugerido |
| --- | --- |
| Stock neto | 60 req/min por CD |
| Ejecuciones activas | 30 req/min por CD |
| Publicación | 30 req/min por CD |

---

## 11. Reglas de negocio principales

### RN-01. Fuente única de planificación

Connexa debe ser el único sistema que decide y publica transferencias en el modelo final.

### RN-02. No borrado funcional

Ninguna Need, PlanLine o ExecutionLine debe eliminarse por falta de stock. Debe cambiar de estado.

### RN-03. Stock factible antes de publicar

Connexa no debe publicar una línea si no existe stock neto positivo para el SKU en la corrida.

### RN-04. Anti-duplicacion

No se debe publicar una transferencia para CD-sucursal-SKU si existe una ejecución activa en Valkimia para la misma clave.

### RN-05. Rechazo por stock

Un rechazo `REJECTED_STOCK` debe devolver la cantidad al backlog y programar replanificación.

### RN-06. Idempotencia obligatoria

Si se reenvía el mismo `connexa_execution_id`, Valkimia debe devolver la misma transferencia y estado.

### RN-07. Auditoria obligatoria

Todo cambio de estado debe generar evento auditable.

### RN-08. Modo degradado

El planificador puede operar sin datos de ventas, stock tienda o promociones, pero no debe operar sin stock neto disponible.

---

## 12. Casos de uso principales

### CU-01. Crear o consolidar Need

1. Llega una necesidad desde Connexa, SGM o manual.
2. El sistema busca Need existente por clave funcional.
3. Si existe, consolida cantidad y registra fuente.
4. Si no existe, crea Need.
5. Registra evento.

Resultado esperado:

- Existe una única Need por CD-sucursal-SKU-bucket.

### CU-02. Ejecutar planificación por CD

1. Scheduler dispara planificador.
2. Se seleccionan Needs elegibles.
3. Se consulta SND a Valkimia.
4. Se calcula prioridad.
5. Se asigna stock.
6. Se crean PlanLines.
7. Se cierra plan o se avanza a publicación.

Resultado esperado:

- Hay plan trazable y no se planifica mas que el stock disponible.

### CU-03. Publicar transferencia

1. Connexa agrupa PlanLines por sucursal.
2. Verifica ejecuciones activas.
3. Genera `connexa_execution_id`.
4. Publica a Valkimia.
5. Registra respuesta.

Resultado esperado:

- Existe Execution con IDs internos y externos cuando Valkimia responde.

### CU-04. Procesar rechazo por stock

1. Valkimia responde `REJECTED_STOCK`.
2. Connexa marca línea rechazada.
3. La cantidad queda pendiente en backlog.
4. Se calcula `next_replan_at`.
5. Se registra evento.

Resultado esperado:

- La necesidad no se pierde y será replanificada.

### CU-05. Actualizar tracking

1. Job consulta estado en Valkimia.
2. Connexa compara estado y cantidades.
3. Actualiza Execution y ExecutionLine.
4. Ajusta saldos de Need.
5. Registra evento.

Resultado esperado:

- Connexa refleja estado logístico real.

### CU-06. Reconciliar ejecución externa

1. Connexa consulta ejecuciones activas en Valkimia.
2. Detecta transferencia no creada por Connexa.
3. Crea ExternalExecution.
4. La vincula a Need si corresponde.
5. Bloquea publicación duplicada.

Resultado esperado:

- No se duplica una transferencia existente.

---

## 13. Criterios de aceptación del MVP

El MVP se considera aceptable cuando:

- Se puede crear y consolidar Need por clave funcional.
- Se puede consultar stock neto desde Valkimia o mock equivalente.
- Se puede generar una corrida de planificación por CD.
- El planificador respeta stock neto y backlog.
- Se puede publicar a Valkimia con `connexa_execution_id`.
- Se puede procesar aceptación total, parcial y rechazo total.
- Se puede consultar tracking de transferencia.
- Rechazos por stock vuelven al backlog.
- Existe auditoria en `event_log`.
- Existe vista de backlog abierto.
- Existe anti-duplicacion contra ejecuciones activas.
- Existen pruebas para idempotencia de publicación.

---

## 14. Plan de pruebas minimo

### PT-01. Unitarias

- Merge de Need.
- Calculo de backlog.
- Calculo de priority score.
- Backoff de replanificación.
- Selección de Needs elegibles.
- Mapeo de estados Valkimia -> Connexa.

### PT-02. Integración Valkimia

Escenarios mínimos:

- SND con stock positivo.
- SND con cero.
- SKU faltante en `missing_skus`.
- Publicación aceptada.
- Publicación parcial.
- Rechazo total por stock.
- Reenvió idempotente.
- Tracking hasta `DELIVERED`.
- Error técnico con retry.

### PT-03. Datos

- Unicidad de Need.
- Unicidad de `connexa_execution_id`.
- Constraints de cantidades no negativas.
- Event log generado en transiciones.

### PT-04. UAT operativa

- Backlog visible por CD/sucursal/SKU.
- Duplicación evitada por ejecución activa.
- Replanificación luego de rechazo.
- Línea entregada actualiza saldo de Need.

---

## 15. Fases sugeridas para desarrollo

### Fase D1. Base de datos y dominio

Entregables:

- Esquema `transfer`.
- Catálogos.
- Tablas principales.
- Event log.
- Vistas de backlog y ejecuciones activas.

### Fase D2. Ingesta y consolidación de Need

Entregables:

- Servicio `merge_need`.
- Registro de `need_source`.
- Eventos de creación y merge.
- APIs o jobs de carga desde Connexa/SGM.

### Fase D3. Planificador MVP

Entregables:

- Selector de backlog elegible.
- Adaptador SND Valkimia.
- Calculo de prioridad.
- Generación de Plan y PlanLine.
- Modo simulación y modo real.

### Fase D4. Publicación y ejecución

Entregables:

- Adaptador V-03.
- Idempotencia.
- Registro de Execution y ExecutionLine.
- Manejo de aceptación, parcialidad y rechazo.

### Fase D5. Tracking y replanificación

Entregables:

- Adaptador V-04.
- Actualización de estados y cantidades.
- Requeue de rechazadas.
- Backoff.
- Job de replanificación.

### Fase D6. Reconciliación y tableros

Entregables:

- Adaptador V-02.
- ExternalExecution.
- Bloqueo anti-duplicación.
- KPIs operativos.
- Alertas básicas.

---

## 16. Dependencias y decisiones pendientes

Antes de cerrar el diseño técnico final deben confirmarse:

- Estados reales de Valkimia y mapping definitivo.
- Disponibilidad real de V-01, V-02, V-03 y V-04 o mecanismos equivalentes.
- Si V-05 de eventos incrementales estará disponible.
- Fuente maestra de stock tienda, stock minimo, ventas y promociones.
- Definición final de bucket por familia.
- Unidad mínima de transferencia por SKU.
- Fecha y mecanismo de corte de SGM como publicador.
- Política final de absorción externa conservadora o agresiva.
- Tecnología de implementación del planificador y scheduler.

---

## 17. Anexos de referencia

Documentos fuente:

- `PDD - Vision Requerimiento y Plan Connexa v1.0.md`
- `PDD - 10) Especificación de Interfaces Valkimia v1.0.md`
- `PDD - 11) Modelo ER físico preliminar (PostgreSQL).md`

Modelo físico recomendado:

- Usar esquema `transfer`.
- Usar UUID como PK técnica.
- Usar `numeric(18,4)` para cantidades.
- Usar catálogos para estados.
- Mantener `event_log` append-only.
- Mantener `external_execution` desde el inicio para controlar convivencia con SGM.

---

## 18. Resultado esperado

Al implementar esta especificación, Connexa quedara preparada para gobernar el ciclo completo de transferencias, desde la necesidad inicial hasta la entrega o replanificación. El equipo de desarrollo podrá avanzar con un dominio claro, contratos de integración definidos, modelo de datos preliminar, reglas de negocio trazables y criterios de aceptación verificables.


