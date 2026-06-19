# Planificacion de la Distribucion - Connexa como Orquestador Unico

Version: 1.0  
Fecha: 2026-06-10  
Documento base: replanteo estrategico del sistema de transferencias CD -> sucursales

---

## 1. Vision resumida del enfoque del plan

El nuevo sistema de Planificacion de la Distribucion debe centralizar en Connexa la decision, trazabilidad y gobierno completo del ciclo de vida de las transferencias. El problema actual no debe abordarse solo como una falla de integracion entre Connexa, SGM y Valkimia, sino como una falla de arquitectura: hoy no existe una unica fuente de verdad para la planificacion y ejecucion de transferencias.

El principio rector del nuevo modelo es:

> Connexa debe ser el orquestador unico del ciclo de vida de transferencias.

Bajo este enfoque, Connexa deja de ser solamente un generador de necesidades y pasa a controlar el proceso completo:

- Recibe y consolida necesidades de reposicion.
- Evalua factibilidad usando stock neto disponible del CD.
- Decide que se planifica, cuanto se planifica y cuando se publica.
- Publica transferencias a Valkimia de forma idempotente.
- Conserva trazabilidad por linea SKU-sucursal.
- Mantiene backlog vivo para todo lo que no pudo ejecutarse.
- Replanifica automaticamente faltantes, rechazos o pendientes.
- Provee visibilidad ejecutiva y operativa del estado real del abastecimiento.

La arquitectura objetivo redefine responsabilidades:

- Connexa: fuente unica de planificacion, backlog, decision, trazabilidad y replanificacion.
- Valkimia: ejecutor logistico y proveedor del stock neto disponible real.
- SGM: origen eventual de necesidades durante la transicion, pero no publicador ni decisor de transferencias.
- Operacion CD y sucursales: ejecutan y confirman eventos fisicos, sin gobernar el estado maestro del plan.

El cambio central es pasar del modelo actual:

```text
Necesidad primero -> factibilidad despues -> ejecucion oportunista
```

al modelo objetivo:

```text
Necesidad consolidada -> factibilidad real -> plan controlado -> ejecucion trazable -> replanificacion
```

Este enfoque resuelve los problemas actuales de duplicacion, eliminacion silenciosa en Valkimia, falta de visibilidad, ausencia de backlog y baja confiabilidad del stock planificable. Ademas, deja preparada la base para una evolucion posterior hacia supply planning avanzado: priorizacion por criticidad, fair share, cubicaje, consolidacion por viaje, optimizacion de capacidad y medicion de fill rate CD-sucursal.

---

## 2. Especificacion del requerimiento para construirlo sobre Connexa

### 2.1 Objetivo del sistema

Construir en Connexa un modulo de Planificacion de la Distribucion que administre de punta a punta las necesidades, planes, publicaciones, ejecuciones, estados y backlog de transferencias desde CD hacia sucursales, integrandose con Valkimia para stock neto, publicacion y seguimiento logistico.

### 2.2 Alcance funcional

El sistema debe cubrir los siguientes dominios funcionales.

#### A. Gestion de necesidades

Connexa debe crear, recibir y consolidar necesidades de transferencia por clave funcional:

```text
CD + Sucursal + SKU + bucket de necesidad
```

Requerimientos:

- Crear necesidades desde Connexa por forecast, reposicion, quiebre, promocion u otras reglas.
- Recibir necesidades externas, especialmente desde SGM durante la transicion.
- Consolidar necesidades repetidas para el mismo SKU-sucursal-bucket.
- Evitar duplicacion funcional por multiples origenes.
- Mantener cantidades acumuladas: requerida, planificada, publicada, ejecutada y pendiente.
- Registrar origen, motivo, prioridad y fecha objetivo.
- No eliminar necesidades fisicamente; solo cambiar estado.

Estados minimos sugeridos:

- `NEED_OPEN`
- `NEED_CONSOLIDATED`
- `NEED_PARTIALLY_PLANNED`
- `NEED_FULLY_PLANNED`
- `NEED_PARTIALLY_FULFILLED`
- `NEED_FULFILLED`
- `NEED_CANCELLED`
- `NEED_EXPIRED`

#### B. Backlog operativo

Connexa debe mantener backlog real de todo lo no satisfecho.

Definicion:

```text
backlog_qty = qty_need - qty_fulfilled
```

Requerimientos:

- Identificar backlog por falta de stock, plan parcial, rechazo de Valkimia o ejecucion incompleta.
- Registrar `next_replan_at`, intentos de replanificacion, motivo de espera y estado operativo.
- Permitir congelamiento manual por excepcion operativa.
- Soportar cooldown y backoff para evitar reintentos excesivos.
- Reincorporar automaticamente al backlog cualquier linea rechazada o no ejecutada.

Estados operativos derivados:

- `BL_OPEN`
- `BL_WAITING_STOCK`
- `BL_WAITING_WINDOW`
- `BL_RETRYING`
- `BL_HOLD`
- `BL_CLOSED`

#### C. Stock neto disponible

Valkimia debe proveer a Connexa una vista o interfaz de stock neto disponible por CD-SKU.

Formula conceptual:

```text
Stock Neto Disponible =
  stock fisico
  - reservas / ACO
  - picking en curso
  - pedidos o compromisos pendientes
  - bloqueos de calidad o reservas tecnicas
```

Requerimientos:

- Consultar stock neto en batch para los SKU involucrados en una corrida.
- Recibir timestamp y version de stock para trazabilidad.
- No planificar contra stock bruto.
- Alertar inconsistencias, por ejemplo stock neto negativo o fluctuaciones anormales.

#### D. Motor de planificacion

Connexa debe generar corridas de planificacion por CD, familia, ventana o criterio operativo.

Requerimientos:

- Seleccionar necesidades elegibles con backlog pendiente.
- Consultar stock neto disponible en Valkimia.
- Calcular prioridad por linea.
- Asignar stock de manera deterministica.
- Generar planes parciales cuando el stock no alcance.
- No publicar lineas sin stock disponible.
- Evitar duplicados verificando ejecuciones activas en Valkimia.
- Registrar snapshot de stock utilizado para cada decision.

Estrategias iniciales:

- `PRIORITY`: asignacion por score de prioridad.
- `FAIR_SHARE`: reparto proporcional o minimo entre sucursales cuando hay stock escaso.
- `FIFO`: fallback simple por antiguedad.

Componentes sugeridos del score:

- Prioridad manual.
- Urgencia por SLA o fecha objetivo.
- Riesgo de quiebre en sucursal.
- Venta promedio.
- Promocion activa.
- Antiguedad del backlog.
- Penalidad por reintentos.

#### E. Publicacion controlada a Valkimia

Connexa debe ser el unico publicador objetivo de transferencias a Valkimia.

Requerimientos:

- Publicar solo lineas planificables o parcialmente planificables.
- Agrupar lineas por CD-sucursal para crear ejecuciones logisticas.
- Usar clave idempotente `connexa_execution_id`.
- Recibir y persistir `valkimia_transfer_id`.
- Registrar `valkimia_line_id` cuando exista.
- Reintentar publicaciones sin duplicar.
- Soportar rechazo total o parcial por stock, sin perder la necesidad.

Regla critica:

> Valkimia puede rechazar o informar imposibilidad operativa, pero nunca debe provocar perdida de trazabilidad en Connexa.

#### F. Seguimiento de ejecucion

Connexa debe mantener el estado real de cada transferencia y linea.

Estados minimos sugeridos:

- `EXEC_PUBLISHED`
- `EXEC_ACCEPTED`
- `EXEC_REJECTED_STOCK`
- `EXEC_RESERVED_ACO`
- `EXEC_PICKING`
- `EXEC_SHIPPED`
- `EXEC_DELIVERED`
- `EXEC_CANCELLED`
- `EXEC_FAILED`

Requerimientos:

- Obtener estados desde Valkimia por polling inicialmente.
- Evolucionar luego a eventos si Valkimia lo permite.
- Registrar cantidades preparadas, despachadas y recibidas.
- Actualizar saldos de Need y Backlog.
- Mantener historico de eventos y transiciones.

#### G. Reconciliacion durante transicion

Mientras SGM pueda seguir publicando a Valkimia, Connexa debe detectar esas ejecuciones externas.

Requerimientos:

- Consultar ejecuciones activas en Valkimia por CD-sucursal-SKU.
- Bloquear publicacion duplicada cuando exista una ejecucion activa.
- Crear `ExternalExecution` para absorber trazabilidad.
- Linkear ejecuciones externas a necesidades existentes cuando corresponda.
- Medir cuantas duplicaciones fueron evitadas.

Estados Valkimia considerados activos para anti-duplicacion:

- Aceptada.
- Reservada / ACO.
- En preparacion / picking.
- Despachada o en transito sin recepcion confirmada.

#### H. Auditoria, observabilidad y control

El sistema debe registrar cada transicion relevante en un log de eventos.

Entidad sugerida:

```text
transfer_event_log
```

Campos minimos:

- `event_id`
- `entity_type`
- `entity_id`
- `event_type`
- `old_status`
- `new_status`
- `source_system`
- `event_ts`
- `payload`

KPIs minimos:

- Backlog total por CD, familia y sucursal.
- Backlog aging p95.
- Fill rate de transferencias.
- Tasa de rechazo por stock.
- Tasa de publicacion exitosa.
- Tiempo publicado -> picking -> despacho -> recepcion.
- Duplicaciones detectadas.
- Ejecuciones activas por estado.
- Ejecuciones colgadas.

### 2.3 Modelo conceptual de datos

Entidades minimas en Connexa:

- `transfer_need`: necesidad consolidada y backlog funcional.
- `transfer_plan`: cabecera de corrida de planificacion.
- `transfer_plan_line`: decision por SKU-sucursal.
- `transfer_execution`: transferencia publicada o absorbida.
- `transfer_execution_line`: seguimiento logistico por SKU.
- `external_execution`: ejecucion detectada fuera del flujo Connexa.
- `external_execution_line`: detalle de ejecucion externa.
- `transfer_event_log`: auditoria de estados y eventos.
- `planning_parameters`: parametros de score, backoff, buckets, familias y estrategias.

Restricciones clave:

- Unicidad de necesidad: `(cd_id, sucursal_id, sku_id, need_bucket_date)`.
- Unicidad de linea de plan: `(plan_id, sucursal_id, sku_id)`.
- Unicidad de publicacion: `connexa_execution_id`.
- Unicidad de referencia Valkimia: `valkimia_transfer_id`.
- Control de concurrencia por `need_version` u optimistic locking.

### 2.4 Integraciones requeridas

#### Valkimia -> Connexa

Capacidades minimas:

- Stock neto disponible por CD-SKU.
- Ejecuciones activas por CD-sucursal-SKU.
- Estado de transferencia y lineas.
- Cantidades preparadas, despachadas y recibidas.

#### Connexa -> Valkimia

Capacidades minimas:

- Publicacion idempotente de transferencias.
- Reintento seguro de publicaciones.
- Cancelacion o ajuste, si el proceso operativo lo permite.

#### SGM -> Connexa

Capacidad transitoria:

- Envio de necesidades SGM a Connexa.

Regla objetivo:

> SGM no debe publicar transferencias directamente a Valkimia en el modelo final.

### 2.5 Requerimientos no funcionales

- Trazabilidad completa por linea.
- Idempotencia en integraciones.
- Reprocesamiento seguro.
- Observabilidad operacional.
- Auditoria de decisiones.
- Parametrizacion sin cambios de codigo.
- Performance para planificacion masiva por CD y SKU.
- Reversibilidad durante transicion.
- Seguridad por roles: planificacion, operacion, auditoria e IT.
- Capacidad de operar en modo degradado si faltan datos de score, pero nunca si falta stock neto.

### 2.6 Decisiones funcionales a cerrar antes de codificar

- Bucket por familia: diario, AM/PM o intradia.
- Estados reales de Valkimia y mapping definitivo.
- Si las ejecuciones externas se absorben en modo conservador o agresivo.
- Parametria de unidad minima de transferencia.
- Politica de corte para eliminar SGM como publicador.
- Polling inicial versus eventos desde Valkimia.
- Pesos iniciales de prioridad por familia.

### 2.7 Supuestos, restricciones operativas y factores clave de exito

Este proyecto no depende solo de desarrollo e integraciones. Su exito requiere cambios explicitos en el modelo operativo del CD, en el uso de Valkimia y en la disciplina de gobierno de transferencias.

#### A. Supuestos base del modelo

Se asume que:

- Connexa puede convertirse en la fuente maestra del estado funcional de las transferencias.
- Valkimia puede exponer de forma consultable y suficientemente confiable el stock neto, las reservas activas y el estado de las ejecuciones.
- SGM puede migrar progresivamente a un rol de origen de necesidades, dejando de ser publicador directo durante el modelo objetivo.
- La operacion acepta que no toda necesidad debe publicarse de inmediato; lo no ejecutable debe permanecer como backlog visible y replanificable.
- Los usuarios operativos aceptan trabajar con trazabilidad por estado, en lugar de resolver excepciones borrando, recreando o duplicando solicitudes fuera del flujo.
- Existe capacidad de pilotear por CD, familia o ventana operativa antes de hacer el corte total.

#### B. Restricciones estructurales del proyecto

El modelo propuesto funciona bien solo si se respetan las siguientes restricciones:

- No debe existir mas de un publicador activo hacia Valkimia una vez completada la fase de corte.
- No se debe planificar contra stock bruto; la decision siempre debe basarse en stock neto disponible y trazable.
- No debe haber actualizaciones silenciosas o eliminaciones no auditadas de solicitudes en Valkimia o en sistemas intermedios.
- Las integraciones deben soportar idempotencia, reconciliacion y reproceso seguro.
- El estado maestro del plan no puede quedar repartido entre planillas, operadores, SGM y Valkimia al mismo tiempo.
- La calidad de datos maestros debe ser suficiente: SKU, sucursal, CD, unidades logisticas, estados y equivalencias deben estar alineados entre sistemas.
- Debe existir una politica formal de contingencia para operar cuando falte conectividad, falle una interfaz o se detecte inconsistencia de stock.

#### C. Cambios operativos requeridos en CD y en el uso de Valkimia

Para que Connexa pueda gobernar el proceso de punta a punta, la operacion debe cambiar en algunos puntos concretos:

- El CD no deberia crear transferencias por canales paralelos cuando la necesidad ya fue capturada o planificada por Connexa, salvo contingencias formalmente definidas.
- Si hoy Valkimia se usa como espacio de ajuste manual informal, ese uso debe acotarse, registrarse y quedar bajo reglas de excepcion.
- Las reservas, ACO, picking en curso, bloqueos y demas compromisos de stock en Valkimia deben mantenerse al dia, porque pasan a impactar directamente en la factibilidad del plan.
- La operacion debe aceptar planes parciales y backlog visible como comportamiento normal del sistema cuando el stock no alcanza.
- Los rechazos o imposibilidades operativas deben registrarse con motivo estructurado, no resolverse solo por telefono, chat o acuerdos informales.
- Los eventos fisicos clave deben reflejarse en tiempo y forma: aceptacion, reserva, picking, despacho, recepcion y cancelacion.
- Debe definirse quien tiene autoridad para congelar backlog, priorizar manualmente o liberar excepciones, y bajo que criterio.
- Debe existir disciplina para no reintentar manualmente la misma transferencia por afuera del flujo, porque eso rompe la anti-duplicacion y la trazabilidad.
- Las ventanas operativas del CD, reglas de corte y capacidades logisticas deben parametrizarse para que la planificacion no genere promesas imposibles de ejecutar.

#### D. Que cosas tienen que cambiar respecto del modelo actual

Los principales cambios de operacion esperados son:

- Pasar de "publicar para ver si entra" a "evaluar factibilidad y luego publicar".
- Pasar de resolver faltantes fuera de sistema a administrar backlog formal y replanificable.
- Pasar de estados dispersos entre sistemas a un estado funcional maestro en Connexa.
- Pasar de reintentos manuales a reintentos controlados, auditados e idempotentes.
- Pasar de una logica reactiva por urgencia puntual a una logica de prioridad parametrizada y explicable.
- Pasar de una reconciliacion artesanal posterior a una reconciliacion sistematica y continua.

#### E. Factores clave de exito del proyecto

Los factores mas importantes para que el proyecto funcione bien son:

- Confiabilidad del stock neto disponible publicado por Valkimia.
- Definicion completa del mapping de estados y eventos entre Connexa y Valkimia.
- Decidido patrocinio operativo para eliminar la publicacion paralela SGM -> Valkimia.
- Disciplina operativa del CD para respetar el flujo gobernado y registrar excepciones.
- Idempotencia real en la publicacion y capacidad de reconciliar ejecuciones externas o inconsistentes.
- Tableros visibles para operacion, abastecimiento y soporte con backlog, rechazos, aging y duplicados evitados.
- Piloto acotado con criterios de salida medibles antes de escalar a toda la red.
- Gobierno claro de parametros: prioridades, cooldown, buckets, reglas por familia y ventanas operativas.
- Capacitacion de usuarios clave y acompanamiento del cambio durante la transicion.
- Runbooks de contingencia y soporte para incidentes de integracion, stock o estados colgados.

---

## 3. Plan en fases de construccion e implementacion

### Fase 0 - Diagnostico y linea base

Duracion estimada: 2 a 4 semanas.

Objetivo:

Medir la realidad actual antes de intervenir el flujo operativo.

Actividades:

- Relevar transferencias generadas por Connexa, SGM y Valkimia.
- Medir duplicaciones por CD-sucursal-SKU.
- Identificar solicitudes eliminadas o no trazables.
- Medir rechazos, faltantes, tiempos de despacho y fill rate.
- Definir estados reales de Valkimia.
- Definir fuentes de datos para stock, ventas, promociones y stock tienda.

Entregables:

- Informe de linea base.
- Mapa de integraciones AS-IS.
- Catalogo de estados Valkimia.
- Primer tablero de diagnostico.

Criterio de salida:

- Volumen y tipos de inconsistencias cuantificados.
- Estados reales conocidos.
- Decisiones criticas iniciales cerradas.

### Fase 1 - Fundacion Connexa en modo observador

Duracion estimada: 4 semanas.

Objetivo:

Crear el modelo nuevo dentro de Connexa sin modificar aun la operacion.

Actividades:

- Crear entidades `Need`, `Plan`, `Execution`, `ExternalExecution` y `EventLog`.
- Ingerir necesidades actuales y transferencias activas.
- Construir backlog sombra.
- Implementar reconciliacion inicial contra Valkimia.
- Crear tablero operativo de trazabilidad.
- Simular corridas de planificacion sin publicar.

Entregables:

- Modelo de datos inicial.
- Jobs de ingesta y reconciliacion.
- Backlog consolidado en shadow mode.
- Simulador de planificacion.

Criterio de salida:

- Connexa puede explicar el estado de las transferencias actuales.
- El backlog sombra es consistente.
- Las simulaciones muestran duplicados evitables y stock requerido.

### Fase 2 - Stock neto y planificacion controlada

Duracion estimada: 4 a 6 semanas.

Objetivo:

Activar la planificacion Connexa basada en stock neto, manteniendo convivencia controlada con el modelo actual.

Actividades:

- Implementar interfaz de stock neto Valkimia.
- Implementar motor de prioridad y asignacion.
- Crear planes reales con snapshot de stock.
- Aplicar anti-duplicacion contra ejecuciones activas.
- Publicar en modo controlado para un CD, familia o conjunto piloto.
- Mantener SGM operativo, pero con reconciliacion activa.

Entregables:

- Motor de planificacion v1.
- Publicacion idempotente a Valkimia.
- Reglas de prioridad configurables.
- Tablero de backlog, publicaciones y rechazos.

Criterio de salida:

- Reduccion significativa de duplicaciones.
- Publicaciones Connexa sin duplicados.
- Rechazos por stock medidos y replanificados.
- Operacion piloto estable.

### Fase 3 - Connexa como publicador unico

Duracion estimada: 3 a 5 semanas.

Objetivo:

Eliminar la dualidad de origen y convertir a Connexa en unico publicador de transferencias.

Actividades:

- Bloquear o deshabilitar publicacion directa SGM -> Valkimia.
- Convertir SGM en origen de necesidades hacia Connexa.
- Activar replanificacion automatica de rechazos y pendientes.
- Formalizar SLA de integracion Connexa-Valkimia.
- Mantener reconciliacion como red de seguridad.
- Ejecutar plan de rollback controlado si aparecen inconsistencias.

Entregables:

- Corte operativo SGM publicador.
- Contrato SGM -> Connexa para necesidades.
- Connexa publicador unico.
- Monitoreo productivo de integracion y backlog.

Criterio de salida:

- Cero publicaciones directas SGM -> Valkimia.
- 100% de transferencias nuevas nacen o se gobiernan en Connexa.
- Trazabilidad end-to-end por linea.
- Backlog real y replanificable.

### Fase 4 - Industrializacion operativa

Duracion estimada: 4 a 8 semanas posteriores al corte.

Objetivo:

Estabilizar, parametrizar y escalar el modelo a toda la operacion.

Actividades:

- Ajustar pesos de prioridad con datos reales.
- Incorporar fair share por bajo stock.
- Mejorar alertas y tableros.
- Automatizar reconciliaciones y cierres de ciclo.
- Medir fill rate, aging y tiempos de ciclo por familia.
- Documentar procedimientos operativos y soporte.

Entregables:

- Parametria por familia/CD.
- Tablero ejecutivo y tablero operativo.
- Runbooks de soporte.
- Reporte de beneficios y oportunidades.

Criterio de salida:

- Modelo estable a escala.
- Operacion confia en el backlog Connexa.
- Alertas accionables y trazabilidad auditada.

### Fase 5 - Optimizacion logistica y cubicaje

Duracion estimada: etapa evolutiva posterior.

Objetivo:

Evolucionar desde planificacion de lineas hacia optimizacion de viajes y capacidad logistica.

Actividades:

- Incorporar volumen, peso y unidad logistica por SKU.
- Agrupar planes por viaje, sucursal, ruta o ventana.
- Simular ocupacion de camion.
- Completar capacidad con backlog elegible.
- Medir costo por viaje, ocupacion y productividad.

Entregables:

- Motor de consolidacion por viaje.
- Cubicaje y peso por plan.
- Optimizacion de capacidad.
- Indicadores logisticos avanzados.

Criterio de salida:

- Connexa no solo planifica transferencias, sino que optimiza distribucion.

---

## 4. Riesgos principales y mitigaciones

| Riesgo | Impacto | Mitigacion |
| --- | --- | --- |
| Stock neto Valkimia no confiable | Planes rechazados o faltantes | Definir formula, timestamp, version y alertas |
| SGM sigue publicando en paralelo | Duplicaciones | Fase de reconciliacion y corte controlado |
| Falta de mapping de estados Valkimia | Trazabilidad incompleta | Catalogo de estados obligatorio antes de piloto |
| Reintentos excesivos | Ruido operativo e integracion saturada | Cooldown y backoff por familia |
| Resistencia operativa | Baja adopcion | Shadow mode, tableros visibles y evidencia |
| Publicacion no idempotente | Duplicados tecnicos | Clave `connexa_execution_id` obligatoria |

---

## 5. Resultado esperado

Al finalizar la implementacion, Connexa sera la fuente de verdad del plan de distribucion y el orquestador unico de transferencias. El sistema dejara de depender de intentos aislados o publicaciones paralelas, y pasara a operar con un backlog controlado, stock factible, estados auditables y replanificacion automatica.

El beneficio no se limita a corregir duplicaciones o perdidas de solicitudes. El nuevo modelo crea una plataforma de supply planning sobre la cual sera posible incorporar priorizacion avanzada, optimizacion de viajes, cubicaje, simulacion y control ejecutivo de la distribucion.
