# Planificación de la Distribución - Connexa como Orquestador Único

Version: 1.0  
Fecha: 2026-06-10  
Documento base: replanteo estratégico del sistema de transferencias CD -> sucursales

---

## 1. Vision resumida del enfoque del plan

El nuevo sistema de Planificación de la Distribución debe centralizar en Connexa la decisión, trazabilidad y gobierno completo del ciclo de vida de las transferencias. El problema actual no debe abordarse solo como una falla de integración entre Connexa, SGM y Valkimia, sino como una falla de arquitectura: hoy no existe una única fuente de verdad para la planificación y ejecución de transferencias.

El principio rector del nuevo modelo es:

> Connexa debe ser el orquestador único del ciclo de vida de transferencias.

Bajo este enfoque, Connexa deja de ser solamente un generador de necesidades y pasa a controlar el proceso completo:

- Recibe y consolida necesidades de reposición.
- Evalúa factibilidad usando stock neto disponible del CD.
- Decide que se planifica, cuanto se planifica y cuando se publica.
- Publica transferencias a Valkimia de forma idempotente.
- Conserva trazabilidad por línea SKU-sucursal.
- Mantiene backlog vivo para todo lo que no pudo ejecutarse.
- Replanifica automáticamente faltantes, rechazos o pendientes.
- Provee visibilidad ejecutiva y operativa del estado real del abastecimiento.

La arquitectura objetivo redefine responsabilidades:

- Connexa: fuente única de planificacion, backlog, decisión, trazabilidad y replanificación.
- Valkimia: ejecutor logístico y proveedor del stock neto disponible real.
- SGM: origen eventual de necesidades durante la transición, pero no publicador ni decisor de transferencias.
- Operación CD y sucursales: ejecutan y confirman eventos físicos, sin gobernar el estado maestro del plan.

El cambio central es pasar del modelo actual:

```text
Necesidad primero -> factibilidad después -> ejecución oportunista
```

al modelo objetivo:

```text
Necesidad consolidada -> factibilidad real -> plan controlado -> ejecución trazable -> replanificación
```

Este enfoque resuelve los problemas actuales de duplicación, eliminación silenciosa en Valkimia, falta de visibilidad, ausencia de backlog y baja confiabilidad del stock planificable. Además, deja preparada la base para una evolución posterior hacia supply planning avanzado: priorización por criticidad, fair share, cubicaje, consolidación por viaje, optimización de capacidad y medición de fill rate CD-sucursal.

---

## 2. Especificación del requerimiento para construirlo sobre Connexa

### 2.1 Objetivo del sistema

Construir en Connexa un modulo de Planificación de la Distribución que administre de punta a punta las necesidades, planes, publicaciones, ejecuciones, estados y backlog de transferencias desde CD hacia sucursales, integrándose con Valkimia para stock neto, publicación y seguimiento logístico.

### 2.2 Alcance funcional

El sistema debe cubrir los siguientes dominios funcionales.

#### A. Gestión de necesidades

Connexa debe crear, recibir y consolidar necesidades de transferencia por clave funcional:

```text
CD + Sucursal + SKU + bucket de necesidad
```

Requerimientos:

- Crear necesidades desde Connexa por forecast, reposición, quiebre, promoción u otras reglas.
- Recibir necesidades externas, especialmente desde SGM durante la transición.
- Consolidar necesidades repetidas para el mismo SKU-sucursal-bucket.
- Evitar duplicación funcional por múltiples orígenes.
- Mantener cantidades acumuladas: requerida, planificada, publicada, ejecutada y pendiente.
- Registrar origen, motivo, prioridad y fecha objetivo.
- No eliminar necesidades físicamente; solo cambiar estado.

Estados mínimos sugeridos:

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

Definición:

```text
backlog_qty = qty_need - qty_fulfilled
```

Requerimientos:

- Identificar backlog por falta de stock, plan parcial, rechazo de Valkimia o ejecución incompleta.
- Registrar `next_replan_at`, intentos de replanificación, motivo de espera y estado operativo.
- Permitir congelamiento manual por excepción operativa.
- Soportar cooldown y backoff para evitar reintentos excesivos.
- Reincorporar automáticamente al backlog cualquier línea rechazada o no ejecutada.

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
  stock físico
  - reservas / ACO
  - picking en curso
  - pedidos o compromisos pendientes
  - bloqueos de calidad o reservas técnicas
```

Requerimientos:

- Consultar stock neto en batch para los SKU involucrados en una corrida.
- Recibir timestamp y version de stock para trazabilidad.
- No planificar contra stock bruto.
- Alertar inconsistencias, por ejemplo stock neto negativo o fluctuaciones anormales.

#### D. Motor de planificación

Connexa debe generar corridas de planificación por CD, familia, ventana o criterio operativo.

Requerimientos:

- Seleccionar necesidades elegibles con backlog pendiente.
- Consultar stock neto disponible en Valkimia.
- Calcular prioridad por línea.
- Asignar stock de manera determinística.
- Generar planes parciales cuando el stock no alcance.
- No publicar líneas sin stock disponible.
- Evitar duplicados verificando ejecuciones activas en Valkimia.
- Registrar snapshot de stock utilizado para cada decisión.

Estrategias iniciales:

- `PRIORITY`: asignación por score de prioridad.
- `FAIR_SHARE`: reparto proporcional o minimo entre sucursales cuando hay stock escaso.
- `FIFO`: fallback simple por antigüedad.

Componentes sugeridos del score:

- Prioridad manual.
- Urgencia por SLA o fecha objetivo.
- Riesgo de quiebre en sucursal.
- Venta promedio.
- Promoción activa.
- Antigüedad del backlog.
- Penalidad por reintentos.

#### E. Publicación controlada a Valkimia

Connexa debe ser el único publicador objetivo de transferencias a Valkimia.

Requerimientos:

- Publicar solo líneas planificables o parcialmente planificables.
- Agrupar líneas por CD-sucursal para crear ejecuciones logísticas.
- Usar clave idempotente `connexa_execution_id`.
- Recibir y persistir `valkimia_transfer_id`.
- Registrar `valkimia_line_id` cuando exista.
- Reintentar publicaciones sin duplicar.
- Soportar rechazo total o parcial por stock, sin perder la necesidad.

Regla critica:

> Valkimia puede rechazar o informar imposibilidad operativa, pero nunca debe provocar perdida de trazabilidad en Connexa.

#### F. Seguimiento de ejecución

Connexa debe mantener el estado real de cada transferencia y línea.

Estados mínimos sugeridos:

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
- Mantener histórico de eventos y transiciones.

#### G. Reconciliación durante transición

Mientras SGM pueda seguir publicando a Valkimia, Connexa debe detectar esas ejecuciones externas.

Requerimientos:

- Consultar ejecuciones activas en Valkimia por CD-sucursal-SKU.
- Bloquear publicación duplicada cuando exista una ejecución activa.
- Crear `ExternalExecution` para absorber trazabilidad.
- Linkear ejecuciones externas a necesidades existentes cuando corresponda.
- Medir cuantas duplicaciones fueron evitadas.

Estados Valkimia considerados activos para anti-duplicacion:

- Aceptada.
- Reservada / ACO.
- En preparación / picking.
- Despachada o en transito sin recepción confirmada.

#### H. Auditoria, observabilidad y control

El sistema debe registrar cada transición relevante en un log de eventos.

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
- Tasa de publicación exitosa.
- Tiempo publicado -> picking -> despacho -> recepción.
- Duplicaciones detectadas.
- Ejecuciones activas por estado.
- Ejecuciones colgadas.

### 2.3 Modelo conceptual de datos

Entidades mínimas en Connexa:

- `transfer_need`: necesidad consolidada y backlog funcional.
- `transfer_plan`: cabecera de corrida de planificacion.
- `transfer_plan_line`: decisión por SKU-sucursal.
- `transfer_execution`: transferencia publicada o absorbida.
- `transfer_execution_line`: seguimiento logístico por SKU.
- `external_execution`: ejecución detectada fuera del flujo Connexa.
- `external_execution_line`: detalle de ejecución externa.
- `transfer_event_log`: auditoria de estados y eventos.
- `planning_parameters`: parámetros de score, backoff, buckets, familias y estrategias.

Restricciones clave:

- Unicidad de necesidad: `(cd_id, sucursal_id, sku_id, need_bucket_date)`.
- Unicidad de línea de plan: `(plan_id, sucursal_id, sku_id)`.
- Unicidad de publicación: `connexa_execution_id`.
- Unicidad de referencia Valkimia: `valkimia_transfer_id`.
- Control de concurrencia por `need_version` u optimistic locking.

### 2.4 Integraciones requeridas

#### Valkimia -> Connexa

Capacidades minimas:

- Stock neto disponible por CD-SKU.
- Ejecuciones activas por CD-sucursal-SKU.
- Estado de transferencia y líneas.
- Cantidades preparadas, despachadas y recibidas.

#### Connexa -> Valkimia

Capacidades minimas:

- Publicación idempotente de transferencias.
- Reintento seguro de publicaciones.
- Cancelación o ajuste, si el proceso operativo lo permite.

#### SGM -> Connexa

Capacidad transitoria:

- Envío de necesidades SGM a Connexa.

Regla objetivo:

> SGM no debe publicar transferencias directamente a Valkimia en el modelo final.

### 2.5 Requerimientos no funcionales

- Trazabilidad completa por línea.
- Idempotencia en integraciones.
- Reprocesamiento seguro.
- Observabilidad operacional.
- Auditoria de decisiones.
- Parametrización sin cambios de código.
- Performance para planificacion masiva por CD y SKU.
- Reversibilidad durante transición.
- Seguridad por roles: planificacion, operación, auditoria e IT.
- Capacidad de operar en modo degradado si faltan datos de score, pero nunca si falta stock neto.

### 2.6 Decisiones funcionales a cerrar antes de codificar

- Bucket por familia: diario, AM/PM o intradía.
- Estados reales de Valkimia y mapping definitivo.
- Si las ejecuciones externas se absorben en modo conservador o agresivo.
- Parametría de unidad mínima de transferencia.
- Política de corte para eliminar SGM como publicador.
- Polling inicial versus eventos desde Valkimia.
- Pesos iniciales de prioridad por familia.

### 2.7 Supuestos, restricciones operativas y factores clave de éxito

Este proyecto no depende solo de desarrollo e integraciones. Su éxito requiere cambios explícitos en el modelo operativo del CD, en el uso de Valkimia y en la disciplina de gobierno de transferencias.

#### A. Supuestos base del modelo

Se asume que:

- Connexa puede convertirse en la fuente maestra del estado funcional de las transferencias.
- Valkimia puede exponer de forma consultable y suficientemente confiable el stock neto, las reservas activas y el estado de las ejecuciones.
- SGM puede migrar progresivamente a un rol de origen de necesidades, dejando de ser publicador directo durante el modelo objetivo.
- La operación acepta que no toda necesidad debe publicarse de inmediato; lo no ejecutable debe permanecer como backlog visible y replanificadle.
- Los usuarios operativos aceptan trabajar con trazabilidad por estado, en lugar de resolver excepciones borrando, recreando o duplicando solicitudes fuera del flujo.
- Existe capacidad de pilotear por CD, familia o ventana operativa antes de hacer el corte total.

#### B. Restricciones estructurales del proyecto

El modelo propuesto funciona bien solo si se respetan las siguientes restricciones:

- No debe existir mas de un publicador activo hacia Valkimia una vez completada la fase de corte.
- No se debe planificar contra stock bruto; la decisión siempre debe basarse en stock neto disponible y trazable.
- No debe haber actualizaciones silenciosas o eliminaciones no auditadas de solicitudes en Valkimia o en sistemas intermedios.
- Las integraciones deben soportar idempotencia, reconciliación y reproceso seguro.
- El estado maestro del plan no puede quedar repartido entre planillas, operadores, SGM y Valkimia al mismo tiempo.
- La calidad de datos maestros debe ser suficiente: SKU, sucursal, CD, unidades logísticas, estados y equivalencias deben estar alineados entre sistemas.
- Debe existir una política formal de contingencia para operar cuando falte conectividad, falle una interfaz o se detecte inconsistencia de stock.

#### C. Cambios operativos requeridos en CD y en el uso de Valkimia

Para que Connexa pueda gobernar el proceso de punta a punta, la operación debe cambiar en algunos puntos concretos:

- El CD no debería crear transferencias por canales paralelos cuando la necesidad ya fue capturada o planificada por Connexa, salvo contingencias formalmente definidas.
- Si hoy Valkimia se usa como espacio de ajuste manual informal, ese uso debe acotarse, registrarse y quedar bajo reglas de excepción.
- Las reservas, ACO, picking en curso, bloqueos y demás compromisos de stock en Valkimia deben mantenerse al día, porque pasan a impactar directamente en la factibilidad del plan.
- La operación debe aceptar planes parciales y backlog visible como comportamiento normal del sistema cuando el stock no alcanza.
- Los rechazos o imposibilidades operativas deben registrarse con motivo estructurado, no resolverse solo por teléfono, chat o acuerdos informales.
- Los eventos físicos clave deben reflejarse en tiempo y forma: aceptación, reserva, picking, despacho, recepción y cancelación.
- Debe definirse quien tiene autoridad para congelar backlog, priorizar manualmente o liberar excepciones, y bajo que criterio.
- Debe existir disciplina para no reintentar manualmente la misma transferencia por afuera del flujo, porque eso rompe la anti-duplicacion y la trazabilidad.
- Las ventanas operativas del CD, reglas de corte y capacidades logísticas deben parametrizarse para que la planificacion no genere promesas imposibles de ejecutar.

#### D. Que cosas tienen que cambiar respecto del modelo actual

Los principales cambios de operación esperados son:

- Pasar de "publicar para ver si entra" a "evaluar factibilidad y luego publicar".
- Pasar de resolver faltantes fuera de sistema a administrar backlog formal y replanificable.
- Pasar de estados dispersos entre sistemas a un estado funcional maestro en Connexa.
- Pasar de reintentos manuales a reintentos controlados, auditados e idempotentes.
- Pasar de una lógica reactiva por urgencia puntual a una lógica de prioridad parametrizada y explicable.
- Pasar de una reconciliación artesanal posterior a una reconciliación sistemática y continua.

#### E. Factores clave de éxito del proyecto

Los factores mas importantes para que el proyecto funcione bien son:

- Confiabilidad del stock neto disponible publicado por Valkimia.
- Definición completa del mapping de estados y eventos entre Connexa y Valkimia.
- Decidido patrocinio operativo para eliminar la publicación paralela SGM -> Valkimia.
- Disciplina operativa del CD para respetar el flujo gobernado y registrar excepciones.
- Idempotencia real en la publicación y capacidad de reconciliar ejecuciones externas o inconsistentes.
- Tableros visibles para operación, abastecimiento y soporte con backlog, rechazos, aging y duplicados evitados.
- Piloto acotado con criterios de salida medibles antes de escalar a toda la red.
- Gobierno claro de parámetros: prioridades, cooldown, buckets, reglas por familia y ventanas operativas.
- Capacitación de usuarios clave y acompañamiento del cambio durante la transición.
- Runbooks de contingencia y soporte para incidentes de integración, stock o estados colgados.

---

## 3. Plan en fases de construcción e implementación

### Fase 0 - Diagnostico y línea base

Duración estimada: 2 a 4 semanas.

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

- Informe de línea base.
- Mapa de integraciones AS-IS.
- Catalogo de estados Valkimia.
- Primer tablero de diagnostico.

Criterio de salida:

- Volumen y tipos de inconsistencias cuantificados.
- Estados reales conocidos.
- Decisiones criticas iniciales cerradas.

### Fase 1 - Fundación Connexa en modo observador

Duración estimada: 4 semanas.

Objetivo:

Crear el modelo nuevo dentro de Connexa sin modificar aun la operación.

Actividades:

- Crear entidades `Need`, `Plan`, `Execution`, `ExternalExecution` y `EventLog`.
- Ingerir necesidades actuales y transferencias activas.
- Construir backlog sombra.
- Implementar reconciliación inicial contra Valkimia.
- Crear tablero operativo de trazabilidad.
- Simular corridas de planificacion sin publicar.

Entregables:

- Modelo de datos inicial.
- Jobs de ingesta y reconciliación.
- Backlog consolidado en shadow mode.
- Simulador de planificacion.

Criterio de salida:

- Connexa puede explicar el estado de las transferencias actuales.
- El backlog sombra es consistente.
- Las simulaciones muestran duplicados evitables y stock requerido.

### Fase 2 - Stock neto y planificacion controlada

Duración estimada: 4 a 6 semanas.

Objetivo:

Activar la planificacion Connexa basada en stock neto, manteniendo convivencia controlada con el modelo actual.

Actividades:

- Implementar interfaz de stock neto Valkimia.
- Implementar motor de prioridad y asignación.
- Crear planes reales con snapshot de stock.
- Aplicar anti-duplicacion contra ejecuciones activas.
- Publicar en modo controlado para un CD, familia o conjunto piloto.
- Mantener SGM operativo, pero con reconciliación activa.

Entregables:

- Motor de planificacion v1.
- Publicación idempotente a Valkimia.
- Reglas de prioridad configurables.
- Tablero de backlog, publicaciones y rechazos.

Criterio de salida:

- Reducción significativa de duplicaciones.
- Publicaciones Connexa sin duplicados.
- Rechazos por stock medidos y replanificados.
- Operación piloto estable.

### Fase 3 - Connexa como publicador único

Duración estimada: 3 a 5 semanas.

Objetivo:

Eliminar la dualidad de origen y convertir a Connexa en único publicador de transferencias.

Actividades:

- Bloquear o deshabilitar publicación directa SGM -> Valkimia.
- Convertir SGM en origen de necesidades hacia Connexa.
- Activar replanificación automática de rechazos y pendientes.
- Formalizar SLA de integración Connexa-Valkimia.
- Mantener reconciliación como red de seguridad.
- Ejecutar plan de Pollack controlado si aparecen inconsistencias.

Entregables:

- Corte operativo SGM publicador.
- Contrato SGM -> Connexa para necesidades.
- Connexa publicador único.
- Monitoreo productivo de integración y backlog.

Criterio de salida:

- Cero publicaciones directas SGM -> Valkimia.
- 100% de transferencias nuevas nacen o se gobiernan en Connexa.
- Trazabilidad end-to-end por línea.
- Backlog real y replanificable.

### Fase 4 - Industrialización operativa

Duración estimada: 4 a 8 semanas posteriores al corte.

Objetivo:

Estabilizar, parametrizar y escalar el modelo a toda la operación.

Actividades:

- Ajustar pesos de prioridad con datos reales.
- Incorporar fair share por bajo stock.
- Mejorar alertas y tableros.
- Automatizar reconciliaciones y cierres de ciclo.
- Medir fill rate, aging y tiempos de ciclo por familia.
- Documentar procedimientos operativos y soporte.

Entregables:

- Parametriza por familia/CD.
- Tablero ejecutivo y tablero operativo.
- Runbooks de soporte.
- Reporte de beneficios y oportunidades.

Criterio de salida:

- Modelo estable a escala.
- Operación confía en el backlog Connexa.
- Alertas accionables y trazabilidad auditada.

### Fase 5 - Optimización logística y cubicaje

Duración estimada: etapa evolutiva posterior.

Objetivo:

Evolucionar desde planificacion de líneas hacia optimización de viajes y capacidad logística.

Actividades:

- Incorporar volumen, peso y unidad logística por SKU.
- Agrupar planes por viaje, sucursal, ruta o ventana.
- Simular ocupación de camión.
- Completar capacidad con backlog elegible.
- Medir costo por viaje, ocupación y productividad.

Entregables:

- Motor de consolidación por viaje.
- Cubicaje y peso por plan.
- Optimización de capacidad.
- Indicadores logísticos avanzados.

Criterio de salida:

- Connexa no solo planifica transferencias, sino que optimiza distribución.

---

## 4. Riesgos principales y mitigaciones

| Riesgo | Impacto | Mitigación |
| --- | --- | --- |
| Stock neto Valkimia no confiable | Planes rechazados o faltantes | Definir formula, timestamp, version y alertas |
| SGM sigue publicando en paralelo | Duplicaciones | Fase de reconciliación y corte controlado |
| Falta de mapping de estados Valkimia | Trazabilidad incompleta | Catalogo de estados obligatorio antes de piloto |
| Reintentos excesivos | Ruido operativo e integración saturada | Cooldown y backoff por familia |
| Resistencia operativa | Baja adopción | Shadow mode, tableros visibles y evidencia |
| Publicación no idempotente | Duplicados técnicos | Clave `connexa_execution_id` obligatoria |

---

## 5. Resultado esperado

Al finalizar la implementación, Connexa será la fuente de verdad del plan de distribución y el orquestador único de transferencias. El sistema dejara de depender de intentos aislados o publicaciones paralelas, y pasara a operar con un backlog controlado, stock factible, estados auditables y replanificación automática.

El beneficio no se limita a corregir duplicaciones o perdidas de solicitudes. El nuevo modelo crea una plataforma de suplí planning sobre la cual será posible incorporar priorización avanzada, optimización de viajes, cubicaje, simulación y control ejecutivo de la distribución.


