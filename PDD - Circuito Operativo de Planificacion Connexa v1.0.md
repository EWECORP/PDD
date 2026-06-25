# Circuito Operativo de Planificacion de la Distribucion - Connexa

Sistema: Planificacion de la Distribucion sobre Connexa  
Version: 1.0  
Fecha: 2026-06-25  
Destino: Producto, Operacion, Compras, Logistica, IT Integraciones y Direccion

---

## 1. Objetivo del documento

Este documento describe el circuito operativo objetivo para una planificacion de distribucion en DIARCO, tomando como base la disponibilidad de stock en el Centro de Distribucion (CD) y las necesidades de abastecimiento de los locales.

El objetivo es explicar, de forma funcional y operativa:

- Como nace una necesidad de distribucion.
- Como Connexa consolida y prioriza esa necesidad.
- Como se valida la factibilidad contra stock neto disponible del CD.
- Como se publica a Valkimia solo lo ejecutable.
- Como se conserva el backlog de todo lo no satisfecho.
- Que roles intervienen en cada momento del circuito.
- Donde puede intervenir Compras / Abastecimiento sin romper la gobernanza del proceso.

---

## 2. Principio rector del modelo

El nuevo sistema debe operar bajo el siguiente principio:

> Connexa no debe limitarse a enviar pedidos de transferencia. Debe consolidar necesidades, validar factibilidad contra stock neto real, decidir que se puede ejecutar, publicar solo lo factible a Valkimia y conservar en backlog todo lo pendiente.

Bajo este modelo:

- Connexa es el orquestador funcional del ciclo.
- Valkimia es el proveedor de stock neto y ejecutor logistico.
- El CD ejecuta fisicamente la preparacion y despacho.
- La sucursal confirma la recepcion.
- Compras participa en criterios de abastecimiento, prioridades y excepciones.
- IT Integraciones asegura la continuidad tecnica de las interfaces.

---

## 3. Circuito operativo de una planificacion

### 3.1 Captura de necesidades

Connexa recibe o genera necesidades de reposicion para los locales.

Las necesidades pueden originarse en:

- Forecast.
- Reglas de reposicion.
- Riesgo de quiebre.
- Promociones.
- Necesidades manuales.
- SGM, durante una etapa de transicion.
- Requerimientos comerciales o de abastecimiento definidos por Compras.

Cada necesidad se normaliza por la siguiente clave funcional:

```text
CD + Sucursal + SKU + bucket de necesidad
```

Si llegan varias necesidades para el mismo CD, sucursal, SKU y periodo, Connexa no debe generar transferencias duplicadas. Debe consolidar las cantidades en una unica necesidad funcional.

Resultado esperado:

- Se crea o actualiza una `TransferNeed`.
- Se registra cantidad requerida, origen, motivo, prioridad y fecha objetivo.
- La necesidad queda viva en Connexa y no se elimina fisicamente.

---

### 3.2 Construccion del backlog

Connexa calcula que parte de cada necesidad sigue pendiente:

```text
backlog_qty = qty_need - qty_fulfilled
```

El backlog representa todo lo que aun no fue satisfecho.

Puede existir backlog porque:

- La necesidad todavia no fue planificada.
- No habia stock neto disponible en el CD.
- El stock alcanzaba solo para una planificacion parcial.
- Valkimia rechazo la transferencia por falta de stock.
- La ejecucion fue incompleta.
- La linea quedo bloqueada por una regla de negocio.
- Hay una ejecucion externa activa durante la transicion.

Resultado esperado:

- Connexa mantiene visibilidad de todo lo pendiente.
- El backlog queda disponible para futuras corridas de planificacion.
- Nada se pierde por rechazos o ejecuciones parciales.

---

### 3.3 Inicio de una corrida de planificacion

La corrida de planificacion puede iniciarse:

- Manualmente por un planificador.
- Por una agenda automatica.
- Por evento de disponibilidad de stock.
- Por una ventana operativa del CD.
- Por familia, proveedor, categoria, CD o criterio operativo.

Connexa selecciona las necesidades elegibles:

```text
backlog pendiente
sin hold operativo
sin cancelacion ni expiracion
con fecha de replanificacion disponible
```

Resultado esperado:

- Se crea un `TransferPlan` o `PlanRun`.
- La corrida queda identificada, auditada y trazable.
- Si no hay trabajo planificable, la corrida se cierra sin publicar.

---

### 3.4 Consulta de stock neto disponible

Antes de decidir, Connexa consulta a Valkimia el stock neto disponible para los SKU involucrados en la corrida.

No debe planificarse contra stock bruto.

La formula conceptual es:

```text
Stock Neto Disponible =
  stock fisico CD
  - reservas / ACO
  - picking en curso
  - pedidos o compromisos pendientes
  - bloqueos de calidad o reservas tecnicas
```

Valkimia debe devolver:

- Stock neto disponible por CD-SKU.
- Timestamp del snapshot.
- Version de stock.
- Componentes del calculo, cuando esten disponibles.

Resultado esperado:

- Connexa decide sobre una foto trazable del stock real utilizable.
- Cada linea planificada conserva el snapshot usado para la decision.

---

### 3.5 Priorizacion de necesidades

Cuando el stock no alcanza para todas las necesidades, Connexa debe definir un orden de asignacion.

Estrategias posibles:

- `PRIORITY`: asignacion por score de prioridad.
- `FAIR_SHARE`: reparto proporcional o minimo entre sucursales.
- `FIFO`: asignacion por antiguedad de la necesidad.

El score de prioridad puede considerar:

- Prioridad manual.
- Urgencia por fecha objetivo o SLA.
- Riesgo de quiebre en sucursal.
- Venta promedio.
- Promocion activa.
- Antiguedad del backlog.
- Criticidad por familia, proveedor o negocio.
- Penalidad por reintentos.

Resultado esperado:

- El stock escaso se asigna con criterios consistentes.
- La decision puede explicarse y auditarse.

---

### 3.6 Asignacion de stock

Para cada SKU, Connexa compara el stock neto disponible contra el backlog.

Escenarios posibles:

| Escenario | Resultado |
| --- | --- |
| Stock suficiente | Planificacion total de las necesidades elegibles. |
| Stock insuficiente | Planificacion parcial y saldo pendiente en backlog. |
| Sin stock disponible | La necesidad queda en backlog esperando stock. |

Connexa solo debe generar lineas de plan cuando la cantidad planificada sea mayor a cero.

Resultado esperado:

- Se crean `TransferPlanLine` solo para cantidades factibles.
- Las necesidades sin stock quedan como backlog.
- Las necesidades parcialmente cubiertas conservan el saldo pendiente.

---

### 3.7 Control anti-duplicacion

Antes de publicar una linea, Connexa debe verificar si ya existe una ejecucion activa en Valkimia para:

```text
CD + Sucursal + SKU
```

Se consideran activas, entre otras:

- Transferencias aceptadas.
- Transferencias reservadas / ACO.
- Transferencias en preparacion.
- Transferencias en picking.
- Transferencias despachadas o en transito sin recepcion confirmada.

Si existe una ejecucion activa:

- Connexa no debe publicar una nueva transferencia duplicada.
- Durante la transicion, puede absorber la ejecucion como `ExternalExecution`.
- La necesidad queda bloqueada o vinculada hasta que se resuelva la ejecucion activa.

Resultado esperado:

- Se evitan duplicaciones entre Connexa, SGM y Valkimia.
- La trazabilidad queda centralizada en Connexa.

---

### 3.8 Publicacion controlada a Valkimia

Connexa agrupa las lineas planificadas por CD y sucursal y publica la transferencia a Valkimia.

La publicacion debe usar una clave idempotente:

```text
connexa_execution_id
```

Valkimia puede responder:

- Aceptada.
- Rechazada por stock.
- Rechazada por regla.
- Error tecnico.
- Imposibilidad operativa.

Si Valkimia acepta, debe devolver:

- `valkimia_transfer_id`.
- `valkimia_line_id`, cuando corresponda.
- Estado inicial de ejecucion.

Resultado esperado:

- Nace una `TransferExecution` vinculada a la necesidad y al plan.
- Connexa conserva la relacion entre lo requerido, lo planificado, lo publicado y lo ejecutado.

---

### 3.9 Ejecucion logistica

Valkimia ejecuta logisticamente la transferencia y la Operacion CD realiza el proceso fisico.

Estados funcionales esperados:

```text
EXEC_PUBLISHED
EXEC_ACCEPTED
EXEC_REJECTED_STOCK
EXEC_RESERVED_ACO
EXEC_PICKING
EXEC_SHIPPED
EXEC_DELIVERED
EXEC_CANCELLED
EXEC_FAILED
```

La Operacion CD interviene en:

- Reserva / ACO.
- Preparacion.
- Picking.
- Control de incidencias.
- Despacho.

La Operacion Sucursal interviene en:

- Recepcion.
- Confirmacion de entrega.
- Informacion de diferencias, faltantes o incidencias.

Resultado esperado:

- Connexa mantiene el estado funcional maestro.
- Valkimia conserva el detalle operativo logistico.
- CD y sucursal ejecutan fisicamente sin gobernar el estado maestro del plan.

---

### 3.10 Actualizacion de necesidad y backlog

Cuando la transferencia avanza o finaliza, Connexa actualiza:

- Cantidad publicada.
- Cantidad ejecutada.
- Cantidad recibida.
- Cantidad cumplida.
- Saldo pendiente.
- Estado de la necesidad.
- Estado del backlog.

Si Valkimia rechaza por stock, la necesidad no se elimina.

Accion esperada:

```text
qty_published -= qty_rejected
backlog vuelve a quedar pendiente
replan_attempts += 1
next_replan_at = now + backoff
estado backlog = BL_WAITING_STOCK
```

Regla critica:

> Nada se elimina silenciosamente. Todo rechazo, parcialidad o pendiente vuelve a Connexa como informacion operativa.

---

## 4. Flujo resumido

```text
Necesidad local / comercial / reposicion
   |
   v
Connexa consolida TransferNeed
   |
   v
Connexa calcula backlog
   |
   v
Se dispara corrida de planificacion
   |
   v
Connexa consulta stock neto a Valkimia
   |
   v
Connexa prioriza y asigna stock
   |
   v
Hay stock?
   |
   +-- No --------> queda en backlog
   |
   +-- Parcial ---> plan parcial + saldo en backlog
   |
   +-- Si --------> plan completo
   |
   v
Control anti-duplicacion
   |
   v
Publicacion controlada a Valkimia
   |
   v
Ejecucion CD / Valkimia
   |
   v
Recepcion en sucursal
   |
   v
Actualizacion de Need, Execution y Backlog
   |
   v
Replanificacion automatica de pendientes
```

---

## 5. Roles que intervienen

### 5.1 Roles principales

| Rol | Intervencion en el circuito |
| --- | --- |
| Connexa | Orquestador funcional y tecnico. Consolida necesidades, calcula backlog, consulta stock neto, planifica, publica, replanifica y conserva trazabilidad. |
| Planificador | Opera Connexa. Revisa backlog, ejecuta simulaciones, genera planes, ajusta prioridades y propone o publica corridas segun permisos. |
| Supervisor | Aprueba publicaciones, libera o aplica holds, revisa excepciones, KPIs y decisiones criticas. |
| Compras / Abastecimiento | Define criterios comerciales de abastecimiento, revisa faltantes, prioriza excepciones y analiza backlog asociado a stock/proveedor/familia. |
| Valkimia | Proveedor de stock neto y ejecutor logistico. Acepta, reserva, prepara, despacha o rechaza transferencias. |
| Operacion CD | Ejecuta fisicamente acopio, preparacion, picking, despacho e incidencias operativas. |
| Operacion Sucursal | Recibe mercaderia, confirma recepcion e informa diferencias o faltantes. |
| SGM | Durante transicion, puede ser origen secundario de necesidades. En el modelo objetivo no deberia publicar transferencias directas. |
| IT Integraciones | Soporta interfaces, errores tecnicos, payloads, reintentos, monitoreo y estabilidad. |
| Auditor / Consulta | Consulta trazabilidad, eventos, reportes y decisiones historicas. |
| Administrador | Configura parametros, reglas, mappings, familias, permisos, usuarios y umbrales. |

---

## 6. Participacion de Compras / Abastecimiento

### 6.1 Criterio general

Compras puede y debe intervenir en el circuito, pero no como ejecutor logistico ni como publicador directo de transferencias.

La regla recomendada es:

> Compras interviene como duenio funcional de criterios de abastecimiento y prioridades comerciales, pero no como ejecutor de transferencias. Su participacion ocurre en la generacion, priorizacion, bloqueo, liberacion y analisis de necesidades. La planificacion operativa y la publicacion logistica siguen gobernadas por Connexa.

Esto permite incorporar la mirada comercial y de aprovisionamiento sin romper la trazabilidad ni generar canales paralelos.

---

### 6.2 Momentos donde puede intervenir Compras

| Momento | Intervencion posible |
| --- | --- |
| Antes de la planificacion | Definir prioridades por proveedor, familia, promocion, criticidad comercial o productos estrategicos. |
| Captura de necesidades | Solicitar necesidades extraordinarias por campanias, lanzamientos, acuerdos comerciales o reposiciones excepcionales. |
| Consolidacion de necesidades | Validar necesidades especiales o de alto impacto comercial. |
| Backlog operativo | Revisar faltantes persistentes, productos sin stock CD, aging alto, quiebres reiterados o necesidades bloqueadas. |
| Reglas de negocio | Proponer reglas por familia, proveedor, promocion, temporada, margen, perecibilidad o criticidad. |
| Falta de stock CD | Definir accion aguas arriba: compra a proveedor, sustitucion, redistribucion futura, cancelacion comercial o ajuste de expectativa. |
| Excepciones | Solicitar hold, liberar hold, cambiar prioridad o justificar una excepcion. |
| Analisis posterior | Revisar fill rate, rechazos por stock, backlog por proveedor/familia y cumplimiento de abastecimiento. |

---

### 6.3 Acciones que Compras no deberia realizar

Compras no deberia:

- Publicar transferencias directamente a Valkimia.
- Crear ejecuciones logisticas por fuera de Connexa.
- Modificar estados fisicos de preparacion, picking o despacho.
- Reintentar transferencias manualmente por canales paralelos.
- Alterar stock disponible sin pasar por el sistema responsable.

Estas acciones deben permanecer bajo Connexa, Valkimia, Operacion CD o IT Integraciones, segun corresponda.

---

## 7. RACI operativo sugerido

Referencias:

- R = Responsible, ejecuta o realiza la actividad.
- A = Accountable, responsable final de la decision o resultado.
- C = Consulted, participa o aporta criterio.
- I = Informed, debe estar informado.

| Evento | Connexa | Planificador | Supervisor | Compras | Valkimia | Operacion CD | Operacion Sucursal | IT Integraciones |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Generar Need por forecast/reposicion | A | R | I | C | I | I | I | C |
| Generar Need comercial/promocional | A | C | I | R | I | I | I | C |
| Consolidar Need | R/A | C | I | C | I | I | I | C |
| Ajustar prioridad comercial | A | R | C | R/C | I | I | I | I |
| Aplicar hold por excepcion | A | R | A/C | C | I | I | I | I |
| Liberar hold | A | R | A/C | C | I | I | I | I |
| Consultar stock neto | R | I | I | I | A | I | I | C |
| Calcular plan | R/A | R | C | C | I | I | I | C |
| Simular plan | A | R | C | C | I | I | I | I |
| Aprobar publicacion | A | R/C | A | C/I | I | I | I | I |
| Publicar transferencia | R/A | R | C | I | A | I | I | C |
| Aceptar o rechazar transferencia | I | I | I | I | R/A | C | I | C |
| Reserva / ACO | I | I | I | I | R/A | C | I | C |
| Picking | I | I | I | I | R | A | I | C |
| Despacho | I | I | I | I | R | A | I | C |
| Recepcion | I | I | I | I | I | C | R/A | C |
| Rechazo por stock | A | R/C | I | C | R/A | I | I | C |
| Replanificacion | R/A | R | C | C | I | I | I | C |
| Analisis de backlog sin stock | A | R | C | R/C | C | I | I | I |
| Error de integracion | C | I | I | I | C | I | I | R/A |
| Auditoria de trazabilidad | A | C | C | C | C | C | C | C |

---

## 8. Reglas operativas clave

1. Connexa debe ser la fuente maestra funcional de la planificacion, backlog, estados y trazabilidad.

2. Valkimia debe informar stock neto disponible y ejecutar logisticamente, pero no debe eliminar silenciosamente una solicitud por falta de stock.

3. No se debe planificar contra stock bruto. Toda decision debe basarse en stock neto disponible con timestamp y version.

4. Toda necesidad no satisfecha debe permanecer en backlog.

5. Una transferencia rechazada por stock debe volver al backlog con motivo auditable y proxima fecha de replanificacion.

6. Antes de publicar, Connexa debe verificar ejecuciones activas para evitar duplicados.

7. SGM no deberia publicar transferencias directas en el modelo objetivo. Durante la transicion, sus ejecuciones deben detectarse y reconciliarse.

8. Compras puede definir o influir prioridades, reglas y excepciones, pero no debe operar transferencias por fuera de Connexa.

9. Operacion CD ejecuta el proceso fisico, pero no gobierna el estado maestro funcional.

10. Operacion Sucursal confirma recepcion y diferencias, cerrando el ciclo operativo.

---

## 9. Frase ejecutiva

El circuito operativo propuesto convierte la planificacion en un proceso gobernado por Connexa: las necesidades se consolidan, se contrastan contra stock neto disponible, se priorizan, se publican solo cuando son factibles y todo saldo no cumplido permanece visible en backlog para futuras replanificaciones. Valkimia ejecuta la operacion logistica, mientras Connexa conserva la decision, la trazabilidad y el estado funcional del ciclo completo. Compras participa aportando criterios comerciales, prioridades y gestion de excepciones, sin convertirse en un canal paralelo de ejecucion.

