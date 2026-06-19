# Especificacion de Requerimiento de Software

Sistema: Planificacion de la Distribucion sobre Connexa  
Version: 1.0  
Fecha: 2026-06-10  
Estado: Borrador listo para refinamiento tecnico  
Destino: Equipo de desarrollo, integraciones, datos, QA y operacion

---

## 1. Proposito

Este documento define los requerimientos de software para construir en Connexa el nuevo sistema de Planificacion de la Distribucion, cuyo objetivo es centralizar la planificacion, publicacion, trazabilidad y replanificacion de transferencias CD -> sucursal.

El sistema debe reemplazar el esquema actual de multiples origenes de transferencia por un modelo gobernado en Connexa, donde:

- Connexa es la fuente de verdad de necesidades, planes, backlog, ejecuciones y estados.
- Valkimia es el ejecutor logistico y proveedor del stock neto disponible.
- SGM deja de publicar transferencias directamente a Valkimia en el modelo objetivo y pasa a informar necesidades hacia Connexa.

La especificacion esta orientada a que desarrollo pueda iniciar analisis tecnico, descomposicion de historias, diseno de servicios, modelo de datos, integraciones y plan de pruebas.

---

## 2. Alcance

### 2.1 Alcance incluido

El sistema debe cubrir:

- Registro y consolidacion de necesidades de transferencia.
- Gestion de backlog pendiente.
- Planificacion de transferencias segun stock neto disponible.
- Priorizacion y asignacion de stock por SKU-sucursal.
- Publicacion idempotente de transferencias hacia Valkimia.
- Seguimiento de ejecucion logistico por cabecera y linea.
- Replanificacion automatica de pendientes y rechazos.
- Reconciliacion de ejecuciones externas durante la convivencia con SGM.
- Auditoria completa de eventos y cambios de estado.
- Tableros operativos y KPIs basicos.
- Parametrizacion de reglas de planificacion por familia/CD.

### 2.2 Fuera de alcance inicial

Queda fuera de la primera version:

- Optimizacion avanzada de rutas.
- Cubicaje completo por camion.
- Costeo logistico.
- Reoptimizacion intradia compleja basada en multiples CDs.
- Motor predictivo de demanda nuevo.
- Sustitucion de articulos.
- Confirmacion contable/fiscal de transferencias.

Estos puntos podran incorporarse como evolucion posterior una vez estabilizado el ciclo Need -> Plan -> Execution -> Backlog.

---

## 3. Glosario

| Termino | Definicion |
| --- | --- |
| Need | Necesidad consolidada de transferencia para CD, sucursal, SKU y bucket. |
| Backlog | Cantidad pendiente de satisfacer: `qty_need - qty_fulfilled`. |
| Plan | Corrida de planificacion generada por Connexa. |
| PlanLine | Decision de planificacion para una linea SKU-sucursal. |
| Execution | Transferencia publicada a Valkimia o absorbida para seguimiento. |
| ExecutionLine | Linea logistica por SKU dentro de una ejecucion. |
| ExternalExecution | Transferencia detectada en Valkimia que no fue publicada por Connexa. |
| SND | Stock Neto Disponible informado por Valkimia. |
| ACO | Reserva/acopio logistico en Valkimia. |
| Bucket | Ventana funcional de consolidacion de necesidades, por ejemplo dia o AM/PM. |
| Idempotencia | Capacidad de reenviar una solicitud sin crear duplicados. |

---

## 4. Actores y sistemas involucrados

| Actor/Sistema | Responsabilidad |
| --- | --- |
| Connexa | Orquestador unico de planificacion, backlog, publicacion y trazabilidad. |
| Valkimia | Ejecutor logistico; informa stock neto, estados y cantidades ejecutadas. |
| SGM | Origen transitorio de necesidades; no publicador en modelo objetivo. |
| Operacion CD | Ejecuta procesos fisicos de acopio, picking y despacho. |
| Sucursal | Recibe mercaderia y confirma recepcion cuando aplique. |
| IT Integraciones | Opera conectores, errores, reintentos y monitoreo tecnico. |
| Planificacion/Abastecimiento | Configura reglas, revisa backlog y prioridades. |

---

## 5. Vista general de solucion

El sistema se organiza en cinco capacidades principales:

1. Ingesta y consolidacion de necesidades.
2. Planificacion factible basada en stock neto.
3. Publicacion idempotente a Valkimia.
4. Seguimiento de ejecucion y actualizacion de saldos.
5. Replanificacion y control de backlog.

Flujo objetivo:

```text
Origenes de necesidad
  -> Connexa Need / Backlog
  -> Planificador Connexa
  -> Consulta SND Valkimia
  -> PlanLine
  -> Publicacion idempotente
  -> Execution / ExecutionLine
  -> Tracking Valkimia
  -> Cierre o replanificacion
```

Regla arquitectonica principal:

> Ninguna necesidad, plan o ejecucion debe desaparecer fisicamente por falta de stock o error operativo. Todo debe quedar trazado por estado y evento.

---

## 6. Requerimientos funcionales

### RF-01. Gestion de necesidades

El sistema debe permitir crear necesidades de transferencia desde Connexa, SGM, cargas manuales o ajustes operativos.

Criterios:

- Cada necesidad debe identificarse por `cd_id`, `sucursal_id`, `sku_id` y `need_bucket_date`.
- Si ingresa una necesidad con la misma clave funcional, el sistema debe consolidarla.
- La consolidacion debe registrar cada origen en `transfer.need_source`.
- La necesidad debe iniciar en estado `NEED_OPEN` o `NEED_CONSOLIDATED`.
- La necesidad no debe eliminarse fisicamente.

### RF-02. Consolidacion de necesidades

El sistema debe soportar dos modos de merge:

- Incremental: suma `qty_incoming` a `qty_need`.
- Recalculado: reemplaza o toma maximo segun regla del origen.

Criterios:

- Forecast recalculado debe poder operar con modo reemplazo/maximo.
- Eventos operativos, SGM o manuales deben poder operar con modo incremental.
- Toda consolidacion debe generar evento `NeedMerged`.

### RF-03. Estados de Need

El sistema debe administrar estados de Need mediante catalogo.

Estados minimos:

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

- Una Need con `backlog_qty > 0` debe estar disponible para planificacion salvo hold, expiracion, cancelacion o ventana futura.
- El sistema debe registrar `next_replan_at`, `replan_attempts_total` y `current_retry_streak`.
- Una linea rechazada por stock debe volver al backlog.

### RF-05. Hold operativo

El sistema debe permitir poner una Need en espera manual.

Criterios:

- Debe registrar `hold_reason_code` y `hold_reason_detail`.
- Mientras tenga hold activo, no debe ser elegible para planificacion.
- La liberacion del hold debe generar evento.

### RF-06. Consulta de stock neto disponible

El sistema debe consultar a Valkimia el stock neto disponible por CD y lista de SKU antes de planificar.

Criterios:

- Debe invocar la interfaz V-01 `POST /v1/stock/net-available` o mecanismo equivalente.
- Debe enviar `cd_id`, `sku_ids`, `as_of_ts` opcional e `include_components`.
- Debe soportar batch maximo sugerido de 2.000 SKU.
- Debe persistir `stock_net_available`, `stock_snapshot_ts` y `stock_version` en las PlanLines.
- No debe planificar lineas con SND menor o igual a cero.

### RF-07. Validacion de stock neto

El sistema debe validar la consistencia basica del SND.

Criterios:

- Si Valkimia devuelve stock neto negativo, Connexa debe tratarlo como cero y generar alerta/evento.
- Si un SKU se informa en `missing_skus`, no debe planificarse.
- Si `include_components=true`, debe poder auditar componentes de stock cuando esten disponibles.

### RF-08. Corrida de planificacion

El sistema debe crear una corrida `transfer.plan` por CD y ventana de ejecucion.

Criterios:

- El plan debe registrar `cd_id`, `plan_run_ts`, `plan_status`, `allocation_strategy_code`, `planner_mode` y usuario/proceso creador.
- Si no hay Needs elegibles, debe cerrar el plan con estado `NO_WORK`.
- Si hay Needs pero sin stock o bloqueadas, debe cerrar con estado equivalente a `NO_STOCK_OR_BLOCKED`.

### RF-09. Seleccion de necesidades elegibles

El planificador debe seleccionar Needs que cumplan:

- `qty_need > qty_fulfilled`.
- Sin hold activo.
- `next_replan_at` nulo o menor/igual a la fecha actual.
- Estado no final.
- No cancelada ni expirada.

Criterios:

- La seleccion debe poder filtrarse por CD, familia y bucket.
- Debe respetar bloqueo por ejecucion externa activa.

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
- Si falta SND, la planificacion no debe continuar para esos SKU.

### RF-11. Estrategias de asignacion

El sistema debe soportar al menos:

- `PRIORITY`.
- `FIFO`.
- `FAIR_SHARE`.

Criterios:

- La estrategia por defecto debe ser configurable por familia.
- `FAIR_SHARE` debe activarse cuando exista bajo stock y multiples sucursales demandando el mismo SKU, segun parametros.
- La cantidad planificada no puede superar el backlog de la Need.
- La suma de cantidades planificadas para un SKU no puede superar el SND disponible en la corrida.

### RF-12. Creacion de PlanLine

El sistema debe crear `transfer.plan_line` para cada decision de asignacion.

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
- Si existe ejecucion activa para la misma clave, no debe publicar una nueva linea.
- Debe marcar la Need con `blocked_by_external_execution = true`.
- Debe crear o actualizar `ExternalExecution` cuando corresponda.

Estados activos normalizados:

- `ACCEPTED`
- `RESERVED_ACO`
- `PICKING`
- `PACKED`
- `SHIPPED`

### RF-14. Publicacion idempotente

El sistema debe publicar transferencias a Valkimia mediante clave idempotente.

Criterios:

- Debe generar `connexa_execution_id` UUID por cabecera.
- Debe generar `connexa_line_id` UUID por linea.
- Debe agrupar lineas por `cd_id` y `sucursal_id`.
- Debe invocar V-03 `POST /v1/transfers` o mecanismo equivalente.
- Si se reintenta el mismo `connexa_execution_id`, no debe crear duplicados.

### RF-15. Manejo de aceptacion total

Cuando Valkimia acepte una publicacion completa, Connexa debe:

- Crear o actualizar `transfer.execution`.
- Persistir `valkimia_transfer_id`.
- Crear `transfer.execution_line`.
- Persistir `valkimia_line_id`.
- Actualizar estado a `EXEC_ACCEPTED`.
- Incrementar `qty_published` o `qty_accepted` segun corresponda.
- Registrar evento.

### RF-16. Manejo de aceptacion parcial

Cuando Valkimia acepte algunas lineas y rechace otras, Connexa debe:

- Mantener la ejecucion creada.
- Actualizar lineas aceptadas como `EXEC_ACCEPTED`.
- Actualizar lineas rechazadas como `EXEC_REJECTED_STOCK` o `EXEC_REJECTED_RULE`.
- Reincorporar lineas rechazadas al backlog.
- Registrar `reject_reason_code`.

### RF-17. Manejo de rechazo total

Cuando Valkimia rechace la transferencia completa por stock o regla, Connexa debe:

- Registrar la ejecucion y su respuesta.
- No perder las Needs asociadas.
- Revertir o no incrementar cantidades publicadas.
- Calcular `next_replan_at` con backoff cuando sea reintentable.
- Registrar evento de rechazo.

### RF-18. Seguimiento de ejecucion

El sistema debe consultar estados de Valkimia por transferencia.

Criterios:

- Debe invocar V-04 `GET /v1/transfers/{valkimia_transfer_id}` o mecanismo equivalente.
- Debe actualizar estado de cabecera y lineas.
- Debe actualizar cantidades `qty_prepared`, `qty_shipped`, `qty_delivered`.
- Debe registrar eventos de cambio.
- Debe ser tolerante a respuestas sin lista de eventos, usando `status` y `last_update_ts`.

### RF-19. Consulta incremental de eventos

Si Valkimia lo permite, el sistema debe soportar V-05 para eventos incrementales.

Criterios:

- Debe deduplicar por `event_id`.
- Debe persistir `next_since_ts` o cursor equivalente.
- Debe poder convivir con polling.

### RF-20. Replanificacion automatica

El sistema debe replanificar Needs pendientes segun eventos y tiempo.

Disparadores:

- Job programado por CD/familia.
- Rechazo de ejecucion.
- Liberacion o actualizacion de stock, si existe evento.
- Vencimiento de `next_replan_at`.

Criterios:

- Debe aplicar backoff exponencial.
- Debe respetar maximos configurables por familia.
- Debe resetear `current_retry_streak` cuando una linea sea aceptada o cumplida, segun regla configurada.

### RF-21. Reconciliacion de ejecuciones externas

Durante la transicion, el sistema debe registrar transferencias existentes no creadas por Connexa.

Criterios:

- Debe crear `transfer.external_execution` y `transfer.external_execution_line`.
- Debe vincularlas a Needs mediante `transfer.need_external_link` cuando exista match.
- Debe operar inicialmente en modo conservador: bloquear duplicacion sin descontar backlog hasta despacho/entrega.
- Debe medir hits de deduplicacion.

### RF-22. Cancelacion y expiracion

El sistema debe permitir cancelar o expirar Needs y ejecuciones segun reglas operativas.

Criterios:

- Cancelar Need debe impedir nuevas planificaciones.
- Expirar Need debe impedir nuevas planificaciones salvo reapertura autorizada.
- Si ya existe ejecucion publicada, la cancelacion debe respetar capacidades reales de Valkimia.
- Toda cancelacion o expiracion debe registrar motivo y evento.

### RF-23. Auditoria universal

El sistema debe registrar toda transicion relevante en `transfer.event_log`.

Criterios:

- Debe registrar entidad, id, evento, estado anterior, estado nuevo, sistema origen, timestamp y payload.
- La tabla debe ser append-only a nivel funcional.
- Debe permitir trazabilidad desde Need hasta ExecutionLine.

### RF-24. Parametrizacion

El sistema debe administrar parametros sin cambios de codigo.

Parametros minimos:

- Modo de bucket.
- Estrategia de asignacion.
- Pesos de prioridad.
- Ventanas SLA.
- Backoff base y maximo.
- Umbral de bajo stock.
- Unidad minima de transferencia.
- Estados activos Valkimia.
- Mapping de estados externos.

### RF-25. Tablero operativo minimo

El sistema debe exponer datos para tablero operativo.

KPIs minimos:

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

Tablas minimas:

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

### RD-02. Catalogos

El sistema debe contar con catalogos de:

- Estados de Need.
- Estados de PlanLine.
- Estados de Execution.
- Origen de Need.
- Estrategias de asignacion.

### RD-03. Identificadores

El sistema debe usar UUID para claves tecnicas internas.

Criterios:

- `connexa_execution_id` debe ser unico.
- `connexa_line_id` debe ser unico.
- `valkimia_transfer_id` debe ser unico cuando exista.
- `valkimia_line_id` debe ser unico cuando exista.

### RD-04. Cantidades

Las cantidades deben persistirse con precision decimal.

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

Endpoint logico:

```text
POST /v1/stock/net-available
```

Request minimo:

- `request_id`
- `cd_id`
- `as_of_ts`
- `sku_ids`
- `include_components`

Response minimo:

- `cd_id`
- `calculated_at_ts`
- `stock_version`
- `items[].sku_id`
- `items[].stock_net_available`
- `items[].uom`
- `items[].components`
- `missing_skus`

### IF-02. V-02 Ejecuciones activas

Endpoint logico:

```text
GET /v1/transfers/active
```

Request minimo:

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

### IF-03. V-03 Publicacion de transferencia

Endpoint logico:

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

Endpoint logico:

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

Endpoint logico opcional:

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

El sistema debe permitir reconstruir el ciclo completo de una linea desde Need hasta entrega o cancelacion.

### RNF-02. Idempotencia

Toda publicacion a Valkimia debe ser idempotente por `connexa_execution_id`.

### RNF-03. Performance

El sistema debe soportar planificacion batch por CD.

Objetivos iniciales:

- Stock neto: batches de hasta 2.000 SKU por request.
- Publicacion: hasta 2.000 lineas por request, recomendado operativo menor a 500.
- Consultas de backlog con indices por CD, SKU, sucursal, estado y `next_replan_at`.

### RNF-04. Disponibilidad operativa

Fallas temporales de Valkimia no deben perder datos.

Criterios:

- Las publicaciones fallidas por error tecnico deben quedar reintentables.
- Los rechazos por stock deben tratarse como negocio, no como error tecnico.

### RNF-05. Seguridad

El sistema debe controlar acceso por rol.

Roles minimos:

- Administrador.
- Planificador.
- Operador CD.
- Consulta/auditoria.
- Soporte IT.

### RNF-06. Observabilidad

El sistema debe generar metricas y logs tecnicos.

Metricas minimas:

- Latencia por interfaz.
- Tasa de error por interfaz.
- Reintentos ejecutados.
- Publicaciones exitosas/fallidas.
- Rechazos por stock.
- Backlog aging.

### RNF-07. Configurabilidad

Reglas de score, backoff, estados activos y familias deben modificarse por datos/configuracion, no por codigo.

### RNF-08. Reprocesabilidad

El sistema debe permitir reprocesar:

- Respuestas de publicacion.
- Eventos de tracking.
- Reconciliaciones externas.
- Corridas de planificacion fallidas, sin duplicar ejecuciones.

---

## 10. Politicas de errores, timeouts y reintentos

### PE-01. Timeouts sugeridos

| Interfaz | Timeout sugerido |
| --- | --- |
| V-01 Stock neto batch | 10 a 20 segundos |
| V-03 Publicacion | 10 segundos |
| V-04 Tracking | 5 segundos |

### PE-02. Reintentos

Connexa debe reintentar solo ante:

- `503 DEPENDENCY_UNAVAILABLE`
- `429 RATE_LIMIT`
- `500 INTERNAL_ERROR`, maximo 2 reintentos
- Timeout tecnico

Connexa no debe reintentar automaticamente ante:

- `400 INVALID_REQUEST`
- `422 UNPROCESSABLE_RULE`
- `REJECTED_STOCK`

### PE-03. Rate limits sugeridos

| Interfaz | Limite sugerido |
| --- | --- |
| Stock neto | 60 req/min por CD |
| Ejecuciones activas | 30 req/min por CD |
| Publicacion | 30 req/min por CD |

---

## 11. Reglas de negocio principales

### RN-01. Fuente unica de planificacion

Connexa debe ser el unico sistema que decide y publica transferencias en el modelo final.

### RN-02. No borrado funcional

Ninguna Need, PlanLine o ExecutionLine debe eliminarse por falta de stock. Debe cambiar de estado.

### RN-03. Stock factible antes de publicar

Connexa no debe publicar una linea si no existe stock neto positivo para el SKU en la corrida.

### RN-04. Anti-duplicacion

No se debe publicar una transferencia para CD-sucursal-SKU si existe una ejecucion activa en Valkimia para la misma clave.

### RN-05. Rechazo por stock

Un rechazo `REJECTED_STOCK` debe devolver la cantidad al backlog y programar replanificacion.

### RN-06. Idempotencia obligatoria

Si se reenvia el mismo `connexa_execution_id`, Valkimia debe devolver la misma transferencia y estado.

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

- Existe una unica Need por CD-sucursal-SKU-bucket.

### CU-02. Ejecutar planificacion por CD

1. Scheduler dispara planificador.
2. Se seleccionan Needs elegibles.
3. Se consulta SND a Valkimia.
4. Se calcula prioridad.
5. Se asigna stock.
6. Se crean PlanLines.
7. Se cierra plan o se avanza a publicacion.

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
2. Connexa marca linea rechazada.
3. La cantidad queda pendiente en backlog.
4. Se calcula `next_replan_at`.
5. Se registra evento.

Resultado esperado:

- La necesidad no se pierde y sera replanificada.

### CU-05. Actualizar tracking

1. Job consulta estado en Valkimia.
2. Connexa compara estado y cantidades.
3. Actualiza Execution y ExecutionLine.
4. Ajusta saldos de Need.
5. Registra evento.

Resultado esperado:

- Connexa refleja estado logistico real.

### CU-06. Reconciliar ejecucion externa

1. Connexa consulta ejecuciones activas en Valkimia.
2. Detecta transferencia no creada por Connexa.
3. Crea ExternalExecution.
4. La vincula a Need si corresponde.
5. Bloquea publicacion duplicada.

Resultado esperado:

- No se duplica una transferencia existente.

---

## 13. Criterios de aceptacion del MVP

El MVP se considera aceptable cuando:

- Se puede crear y consolidar Need por clave funcional.
- Se puede consultar stock neto desde Valkimia o mock equivalente.
- Se puede generar una corrida de planificacion por CD.
- El planificador respeta stock neto y backlog.
- Se puede publicar a Valkimia con `connexa_execution_id`.
- Se puede procesar aceptacion total, parcial y rechazo total.
- Se puede consultar tracking de transferencia.
- Rechazos por stock vuelven al backlog.
- Existe auditoria en `event_log`.
- Existe vista de backlog abierto.
- Existe anti-duplicacion contra ejecuciones activas.
- Existen pruebas para idempotencia de publicacion.

---

## 14. Plan de pruebas minimo

### PT-01. Unitarias

- Merge de Need.
- Calculo de backlog.
- Calculo de priority score.
- Backoff de replanificacion.
- Seleccion de Needs elegibles.
- Mapeo de estados Valkimia -> Connexa.

### PT-02. Integracion Valkimia

Escenarios minimos:

- SND con stock positivo.
- SND con cero.
- SKU faltante en `missing_skus`.
- Publicacion aceptada.
- Publicacion parcial.
- Rechazo total por stock.
- Reenvio idempotente.
- Tracking hasta `DELIVERED`.
- Error tecnico con retry.

### PT-03. Datos

- Unicidad de Need.
- Unicidad de `connexa_execution_id`.
- Constraints de cantidades no negativas.
- Event log generado en transiciones.

### PT-04. UAT operativa

- Backlog visible por CD/sucursal/SKU.
- Duplicacion evitada por ejecucion activa.
- Replanificacion luego de rechazo.
- Linea entregada actualiza saldo de Need.

---

## 15. Fases sugeridas para desarrollo

### Fase D1. Base de datos y dominio

Entregables:

- Esquema `transfer`.
- Catalogos.
- Tablas principales.
- Event log.
- Vistas de backlog y ejecuciones activas.

### Fase D2. Ingesta y consolidacion de Need

Entregables:

- Servicio `merge_need`.
- Registro de `need_source`.
- Eventos de creacion y merge.
- APIs o jobs de carga desde Connexa/SGM.

### Fase D3. Planificador MVP

Entregables:

- Selector de backlog elegible.
- Adaptador SND Valkimia.
- Calculo de prioridad.
- Generacion de Plan y PlanLine.
- Modo simulacion y modo real.

### Fase D4. Publicacion y ejecucion

Entregables:

- Adaptador V-03.
- Idempotencia.
- Registro de Execution y ExecutionLine.
- Manejo de aceptacion, parcialidad y rechazo.

### Fase D5. Tracking y replanificacion

Entregables:

- Adaptador V-04.
- Actualizacion de estados y cantidades.
- Requeue de rechazadas.
- Backoff.
- Job de replanificacion.

### Fase D6. Reconciliacion y tableros

Entregables:

- Adaptador V-02.
- ExternalExecution.
- Bloqueo anti-duplicacion.
- KPIs operativos.
- Alertas basicas.

---

## 16. Dependencias y decisiones pendientes

Antes de cerrar el diseno tecnico final deben confirmarse:

- Estados reales de Valkimia y mapping definitivo.
- Disponibilidad real de V-01, V-02, V-03 y V-04 o mecanismos equivalentes.
- Si V-05 de eventos incrementales estara disponible.
- Fuente maestra de stock tienda, stock minimo, ventas y promociones.
- Definicion final de bucket por familia.
- Unidad minima de transferencia por SKU.
- Fecha y mecanismo de corte de SGM como publicador.
- Politica final de absorcion externa conservadora o agresiva.
- Tecnologia de implementacion del planificador y scheduler.

---

## 17. Anexos de referencia

Documentos fuente:

- `PDD - Vision Requerimiento y Plan Connexa v1.0.md`
- `PDD - 10) Especificacion de Interfaces Valkimia v1.0.md`
- `PDD - 11) Modelo ER fisico preliminar (PostgreSQL).md`

Modelo fisico recomendado:

- Usar esquema `transfer`.
- Usar UUID como PK tecnica.
- Usar `numeric(18,4)` para cantidades.
- Usar catalogos para estados.
- Mantener `event_log` append-only.
- Mantener `external_execution` desde el inicio para controlar convivencia con SGM.

---

## 18. Resultado esperado

Al implementar esta especificacion, Connexa quedara preparada para gobernar el ciclo completo de transferencias, desde la necesidad inicial hasta la entrega o replanificacion. El equipo de desarrollo podra avanzar con un dominio claro, contratos de integracion definidos, modelo de datos preliminar, reglas de negocio trazables y criterios de aceptacion verificables.
