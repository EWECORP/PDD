# Diseno de Pantallas Operativas

Sistema: Planificacion de la Distribucion sobre Connexa  
Version: 1.0  
Fecha: 2026-06-10  
Destino: Producto, UX/UI, desarrollo, QA, planificacion y operacion

---

## 1. Objetivo del diseno

Definir el esquema funcional de pantallas necesarias para operar el nuevo sistema de Planificacion de la Distribucion en Connexa.

La aplicacion debe permitir que los equipos de planificacion, operacion e integraciones puedan:

- Ver el estado real del abastecimiento CD -> sucursal.
- Gestionar backlog y necesidades pendientes.
- Ejecutar y auditar corridas de planificacion.
- Publicar transferencias a Valkimia de forma controlada.
- Monitorear ejecuciones logisticas.
- Detectar duplicaciones, rechazos, errores y lineas colgadas.
- Ajustar reglas operativas sin modificar codigo.

El foco de estas pantallas no es estetico sino operativo: deben ayudar a decidir rapido, explicar el estado de cada linea y reducir incertidumbre.

---

## 2. Principios de experiencia operativa

### P1. Una pantalla debe responder una pregunta operativa

Ejemplos:

- Que esta pendiente?
- Que puedo planificar hoy?
- Que se publico?
- Que rechazo Valkimia?
- Que esta trabado?
- Que duplicados se evitaron?

### P2. La unidad de control es la linea SKU-sucursal

Aunque existan cabeceras de plan o ejecucion, el operador debe poder bajar siempre hasta:

```text
CD -> Sucursal -> SKU -> Need -> PlanLine -> ExecutionLine -> Eventos
```

### P3. Ningun estado debe ser caja negra

Cada estado visible debe permitir ver:

- Motivo.
- Fecha/hora.
- Sistema origen.
- Cantidad afectada.
- Proxima accion esperada.

### P4. Operar por excepcion

El usuario no debe revisar miles de lineas una por una. Las pantallas deben priorizar:

- Backlog vencido.
- Rechazos por stock.
- Ejecuciones colgadas.
- Duplicaciones detectadas.
- Errores de integracion.
- Necesidades bloqueadas.

### P5. Simular antes de ejecutar

La planificacion debe poder verse en modo simulacion antes de publicar, especialmente durante pilotos y ajustes de reglas.

---

## 3. Roles y permisos

| Rol | Permisos principales |
| --- | --- |
| Planificador | Ver backlog, ejecutar simulacion, generar plan, aprobar/publicar, ajustar prioridades. |
| Operador CD | Ver ejecuciones, estados fisicos, incidencias y transferencias en preparacion/despacho. |
| Supervisor | Aprobar publicaciones, cancelar o liberar holds, ver KPIs y excepciones. |
| IT Integraciones | Ver errores tecnicos, reintentos, payloads, logs y estado de interfaces. |
| Auditor/Consulta | Acceso solo lectura a trazabilidad, eventos y reportes. |
| Administrador | Configurar parametros, mappings, familias, roles y umbrales. |

---

## 4. Mapa general de navegacion

```text
Inicio / Dashboard Ejecutivo
  |
  +-- Backlog Operativo
  |     +-- Detalle de Need
  |     +-- Ajuste de prioridad / Hold
  |
  +-- Planificacion
  |     +-- Nueva corrida
  |     +-- Simulador de plan
  |     +-- Detalle de plan
  |     +-- Publicacion a Valkimia
  |
  +-- Ejecucion Logistica
  |     +-- Transferencias activas
  |     +-- Detalle de ejecucion
  |     +-- Tracking por linea
  |
  +-- Reconciliacion
  |     +-- Ejecuciones externas
  |     +-- Duplicados detectados
  |     +-- Vincular a Need
  |
  +-- Alertas y Monitoreo
  |     +-- Integraciones
  |     +-- Rechazos
  |     +-- Ejecuciones colgadas
  |
  +-- Configuracion
        +-- Reglas por familia
        +-- Mapping estados Valkimia
        +-- Parametros de replanificacion
        +-- Usuarios y permisos
```

---

## 5. Pantalla 1 - Dashboard Ejecutivo / Inicio

### Objetivo

Dar una vision rapida del estado general de la distribucion y orientar al usuario hacia las excepciones.

### Usuarios principales

Supervisor, planificador, gerencia operativa.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Planificacion de Distribucion                         Fecha/Hora ultima sync    |
+--------------------------------------------------------------------------------+
| Backlog total | Backlog vencido | Rechazo stock | Publicadas hoy | Fill rate    |
|  125.430 u    |  8.210 u        |  12,4%        |  1.248 lineas  |  91,2%       |
+--------------------------------------------------------------------------------+
| Alertas criticas                         | Estado por CD                        |
| - CD1: aging perecederos > 6h            | CD1  Verde / Amarillo / Rojo         |
| - Valkimia V-01 latencia alta            | CD2  Verde / Amarillo / Rojo         |
| - 14 ejecuciones sin picking             | CD3  Verde / Amarillo / Rojo         |
+--------------------------------------------------------------------------------+
| Evolucion backlog 7 dias                 | Distribucion por estado              |
| [grafico lineal]                         | [barras Need/Plan/Execution]         |
+--------------------------------------------------------------------------------+
| Accesos rapidos: Ver backlog | Nueva corrida | Rechazos | Ejecuciones activas |
+--------------------------------------------------------------------------------+
```

### Componentes

- Tarjetas KPI.
- Semaforo por CD.
- Alertas criticas.
- Grafico de backlog por dia.
- Distribucion por estado.
- Accesos rapidos.

### KPIs minimos

- Backlog total.
- Backlog vencido.
- Backlog aging p95.
- Rechazo por stock ultimas 24h.
- Publicaciones exitosas.
- Transferencias activas.
- Ejecuciones colgadas.
- Fill rate.

### Acciones

- Ir a Backlog filtrado.
- Ir a Rechazos.
- Iniciar nueva corrida.
- Ver estado de integraciones.

---

## 6. Pantalla 2 - Backlog Operativo

### Objetivo

Permitir ver, filtrar, priorizar y actuar sobre necesidades pendientes.

### Usuarios principales

Planificador, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Backlog Operativo                                                               |
+--------------------------------------------------------------------------------+
| Filtros: CD | Familia | Sucursal | SKU | Estado | SLA | Origen | Hold | Bucket |
+--------------------------------------------------------------------------------+
| Resumen: Pendiente total | Vencido | Waiting stock | Hold | Bloqueado externo  |
+--------------------------------------------------------------------------------+
| [ ] CD | Suc | SKU | Desc | Familia | Backlog | Score | Estado | Motivo | Accion |
| [ ] 1  | 041 | 123 | ...  | Secos   | 120     | 86,4  | WAIT_STOCK | SND=0 | Ver |
| [ ] 1  | 052 | 456 | ...  | Perec.  | 24      | 92,1  | RETRYING    | Rech. | Ver |
+--------------------------------------------------------------------------------+
| Acciones masivas: Recalcular prioridad | Hold | Liberar hold | Incluir en plan  |
+--------------------------------------------------------------------------------+
```

### Filtros obligatorios

- CD.
- Familia.
- Sucursal.
- SKU.
- Estado de Need.
- Estado operativo de backlog.
- Rango de antiguedad.
- SLA vencido/no vencido.
- Origen: Connexa, SGM, manual, ajuste.
- Bloqueado por ejecucion externa.

### Columnas minimas

- CD.
- Sucursal.
- SKU.
- Descripcion articulo.
- Familia.
- Bucket.
- `qty_need`.
- `qty_fulfilled`.
- `backlog_qty`.
- `priority_score`.
- Estado Need.
- Estado backlog.
- Motivo.
- `next_replan_at`.
- Ultimo estado ejecucion.

### Acciones

- Ver detalle de Need.
- Ajustar prioridad manual.
- Aplicar hold.
- Liberar hold.
- Forzar recalculo de prioridad.
- Incluir en proxima corrida.
- Exportar resultado.

### Reglas visuales

- Rojo: SLA vencido o aging critico.
- Ambar: `next_replan_at` vencido pero no planificado.
- Azul: bloqueado por ejecucion externa.
- Gris: hold manual.
- Verde: planificado/publicado sin excepcion.

---

## 7. Pantalla 3 - Detalle de Need

### Objetivo

Explicar completamente una necesidad: origenes, cantidades, planes, ejecuciones, bloqueos y eventos.

### Usuarios principales

Planificador, auditor, IT soporte.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Need #UUID                                         Estado: NEED_PARTIALLY_PLANNED|
+--------------------------------------------------------------------------------+
| CD: 1 | Sucursal: 041 | SKU: 123456 | Familia: Secos | Bucket: 2026-06-10      |
| Necesidad: 150 | Planificado: 80 | Publicado: 80 | Cumplido: 30 | Backlog: 120 |
+--------------------------------------------------------------------------------+
| Score y prioridad                 | Replanificacion                            |
| Manual: 60 | Score: 86,4           | Attempts: 2 | Next: 2026-06-10 14:30     |
+--------------------------------------------------------------------------------+
| Origenes de necesidad                                                        |
| CONNEXA forecast 100 | SGM ref 789 50                                        |
+--------------------------------------------------------------------------------+
| Planes asociados                     | Ejecuciones asociadas                     |
| Plan A - 80 u - publicado            | TRF-894470 - PICKING - 30 preparadas      |
+--------------------------------------------------------------------------------+
| Timeline de eventos                                                            |
| 10:00 NeedCreated -> 10:05 NeedMerged -> 10:30 PlanAllocated -> ...           |
+--------------------------------------------------------------------------------+
```

### Secciones

- Cabecera funcional.
- Saldos.
- Score y componentes.
- Replanificacion.
- Origenes.
- PlanLines asociadas.
- ExecutionLines asociadas.
- ExternalExecutions vinculadas.
- Timeline/event log.

### Acciones

- Ajustar prioridad.
- Aplicar hold.
- Liberar hold.
- Cancelar Need.
- Reabrir si esta permitido.
- Ver plan.
- Ver ejecucion.

---

## 8. Pantalla 4 - Nueva Corrida de Planificacion

### Objetivo

Permitir configurar y lanzar una corrida de planificacion en modo simulacion o real.

### Usuarios principales

Planificador, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Nueva Corrida de Planificacion                                                  |
+--------------------------------------------------------------------------------+
| CD: [1]  Familia: [Todas]  Bucket: [Hoy]  Estrategia: [Por configuracion]       |
| Modo: (x) Simulacion  ( ) Real con publicacion                                  |
+--------------------------------------------------------------------------------+
| Opciones                                                                         |
| [x] Consultar stock neto Valkimia                                                |
| [x] Verificar ejecuciones activas                                                |
| [x] Excluir Needs en hold                                                        |
| [ ] Forzar recalculo de score                                                    |
+--------------------------------------------------------------------------------+
| Estimacion previa                                                                |
| Needs elegibles: 12.450 | SKUs: 3.120 | Sucursales: 84                         |
+--------------------------------------------------------------------------------+
| [Simular plan] [Cancelar]                                                        |
+--------------------------------------------------------------------------------+
```

### Campos

- CD.
- Familia.
- Bucket.
- Ventana de despacho deseada.
- Estrategia de asignacion.
- Modo simulacion/real.
- Incluir/excluir bloqueadas.
- Recalcular score.

### Acciones

- Simular.
- Crear plan real.
- Cancelar.

### Validaciones

- No permitir plan real si V-01 stock neto no esta disponible.
- Advertir si V-02 ejecuciones activas no esta disponible.
- Solicitar confirmacion para publicacion real.

---

## 9. Pantalla 5 - Simulador / Resultado de Plan

### Objetivo

Mostrar el resultado de una corrida antes de publicarla o como auditoria de una corrida real.

### Usuarios principales

Planificador, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Resultado de Plan #UUID                              Modo: SIMULACION           |
+--------------------------------------------------------------------------------+
| Lineas elegibles | Planificadas | Parciales | Sin stock | Bloq. externas       |
| 12.450           | 8.920        | 1.105     | 2.010     | 415                  |
+--------------------------------------------------------------------------------+
| Stock usado por familia [grafico]          | Top sucursales con faltante        |
+--------------------------------------------------------------------------------+
| CD | Suc | SKU | Backlog | SND | Planificado | Estado | Motivo | Score          |
| 1  | 041 | 123 | 150     | 80  | 80          | PARTIAL| Stock | 86,4           |
+--------------------------------------------------------------------------------+
| [Aprobar y publicar] [Guardar simulacion] [Descartar] [Exportar]                |
+--------------------------------------------------------------------------------+
```

### Componentes

- Resumen de resultado.
- Comparativo backlog vs planificado.
- Lineas no planificadas con motivo.
- Bloqueos por ejecucion externa.
- Consumo de SND por SKU.
- Tabla detalle.

### Acciones

- Aprobar y publicar.
- Guardar simulacion.
- Descartar.
- Exportar.
- Ver detalle de linea.

### Reglas

- La aprobacion debe pedir confirmacion.
- Debe mostrar advertencia si hay rechazos esperados por stock o SND desactualizado.
- Debe mostrar version/timestamp de stock usado.

---

## 10. Pantalla 6 - Publicacion a Valkimia

### Objetivo

Monitorear el envio de transferencias y respuestas de Valkimia.

### Usuarios principales

Planificador, IT integraciones, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Publicacion a Valkimia - Plan #UUID                                             |
+--------------------------------------------------------------------------------+
| Ejecuciones: 84 | Enviadas: 80 | Aceptadas: 75 | Parciales: 3 | Rechazadas: 2  |
+--------------------------------------------------------------------------------+
| Execution ID | Sucursal | Lineas | Estado | Valkimia ID | Error/Motivo | Accion |
| UUID         | 041      | 25     | ACCEPTED | TRF-894470 | -           | Ver    |
| UUID         | 052      | 12     | PARTIAL  | TRF-894471 | NO_NET_STOCK| Ver    |
+--------------------------------------------------------------------------------+
| [Reintentar errores tecnicos] [Ver payloads] [Cerrar publicacion]               |
+--------------------------------------------------------------------------------+
```

### Estados visibles

- Pendiente.
- Enviando.
- Aceptada.
- Parcial.
- Rechazada por stock.
- Rechazada por regla.
- Error tecnico.
- Reintentable.

### Acciones

- Reintentar error tecnico.
- Ver request/response.
- Ver Execution.
- Ver lineas rechazadas.
- Exportar log de publicacion.

### Reglas

- No reintentar automaticamente `REJECTED_STOCK`.
- Reintentar con backoff solo errores tecnicos.
- Mantener idempotencia por `connexa_execution_id`.

---

## 11. Pantalla 7 - Ejecucion Logistica / Transferencias Activas

### Objetivo

Dar visibilidad operativa de transferencias aceptadas y en proceso logistico.

### Usuarios principales

Operacion CD, planificador, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Ejecucion Logistica                                                             |
+--------------------------------------------------------------------------------+
| Filtros: CD | Sucursal | Estado | Valkimia ID | Fecha | Familia | Colgadas     |
+--------------------------------------------------------------------------------+
| Transferencias activas por estado: Accepted | ACO | Picking | Shipped          |
+--------------------------------------------------------------------------------+
| Valkimia ID | Suc | Estado | Lineas | Prep | Desp | Rec | Ult.Act | Alerta      |
| TRF-894470  | 041 | PICKING | 25    | 18   | 0    | 0   | 11:15   | -           |
| TRF-894455  | 052 | ACCEPTED| 12    | 0    | 0    | 0   | 08:10   | Sin picking |
+--------------------------------------------------------------------------------+
```

### Columnas

- `valkimia_transfer_id`.
- `connexa_execution_id`.
- CD.
- Sucursal.
- Estado.
- Cantidad de lineas.
- Cantidad solicitada.
- Cantidad preparada.
- Cantidad despachada.
- Cantidad recibida.
- Ultima actualizacion.
- Alerta.

### Acciones

- Ver detalle de ejecucion.
- Forzar consulta de tracking.
- Ver timeline.
- Ver lineas con incidencia.

---

## 12. Pantalla 8 - Detalle de Ejecucion

### Objetivo

Mostrar el estado completo de una transferencia en Valkimia y su impacto en Needs.

### Usuarios principales

Operacion CD, planificador, IT soporte.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Ejecucion TRF-894470                         Estado: PICKING                    |
+--------------------------------------------------------------------------------+
| Connexa execution: UUID | Plan: UUID | CD: 1 | Sucursal: 041 | Publicada: 10:40 |
+--------------------------------------------------------------------------------+
| Lineas                                                                            |
| SKU | Desc | Req | Accepted | Prepared | Shipped | Delivered | Estado | Need    |
| 123 | ...  | 12  | 12       | 12       | 0       | 0         | PICKING| Ver     |
+--------------------------------------------------------------------------------+
| Eventos Valkimia / Connexa                                                       |
| 10:40 Published | 10:40 Accepted | 11:10 PickingStarted                         |
+--------------------------------------------------------------------------------+
| [Consultar ahora] [Ver payload] [Ver Need relacionada]                           |
+--------------------------------------------------------------------------------+
```

### Secciones

- Cabecera.
- Lineas.
- Cantidades.
- Eventos.
- Payload request/response.
- Links a Need y PlanLine.

### Acciones

- Consultar estado ahora.
- Ver payload.
- Ver Need relacionada.
- Ver Plan.
- Marcar incidencia manual, si se habilita.

---

## 13. Pantalla 9 - Reconciliacion y Duplicados

### Objetivo

Controlar transferencias externas detectadas, especialmente durante convivencia con SGM.

### Usuarios principales

Planificador, IT integraciones, supervisor.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Reconciliacion de Ejecuciones Externas                                          |
+--------------------------------------------------------------------------------+
| Detectadas hoy | Vinculadas | Sin Need | Bloqueos activos | Duplicados evitados |
| 320            | 280        | 40       | 95               | 112                 |
+--------------------------------------------------------------------------------+
| Valkimia ID | Origen | CD | Suc | SKU | Estado | Need match | Accion            |
| TRF-777001  | SGM    | 1  | 041 | 123 | ACO    | Si         | Ver/Vincular      |
+--------------------------------------------------------------------------------+
| [Vincular seleccionadas] [Ignorar] [Exportar] [Actualizar desde Valkimia]       |
+--------------------------------------------------------------------------------+
```

### Funciones

- Ver ejecuciones activas externas.
- Identificar match con Need.
- Vincular a Need.
- Bloquear publicacion duplicada.
- Marcar como ignorada si no aplica.

### Reglas

- Modo inicial conservador: bloquear duplicacion sin descontar backlog hasta despacho/entrega.
- Toda vinculacion debe generar evento.

---

## 14. Pantalla 10 - Alertas y Monitoreo

### Objetivo

Centralizar problemas que requieren accion inmediata.

### Usuarios principales

Supervisor, IT integraciones, planificador.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Alertas y Monitoreo                                                             |
+--------------------------------------------------------------------------------+
| Criticas | Altas | Medias | Informativas                                        |
+--------------------------------------------------------------------------------+
| Tipo | Severidad | CD | Entidad | Descripcion | Desde | Responsable | Accion    |
| INT  | Critica   | 1  | V-01    | Timeout SND | 10:05 | IT          | Ver       |
| OPE  | Alta      | 1  | TRF...  | Sin picking | 08:10 | Operacion   | Ver       |
+--------------------------------------------------------------------------------+
```

### Tipos de alerta

- Backlog aging critico.
- Rechazo por stock anomalo.
- Stock neto inconsistente.
- Ejecucion colgada.
- Duplicacion detectada.
- Error de integracion.
- Rate limit.
- Publicacion fallida.

### Acciones

- Asignar responsable.
- Marcar en investigacion.
- Resolver.
- Ver entidad asociada.
- Reintentar si es tecnico.

---

## 15. Pantalla 11 - Configuracion de Reglas

### Objetivo

Permitir parametrizar comportamiento del planificador sin tocar codigo.

### Usuarios principales

Administrador, supervisor, planificacion.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Configuracion de Reglas por Familia                                             |
+--------------------------------------------------------------------------------+
| Familia | Bucket | Estrategia | SLA h | Age max | Backoff | FairShare | Editar |
| Perec.  | AM/PM  | PRIORITY   | 12    | 12      | 15m/4h  | Si        | Editar |
| Secos   | Diario | PRIORITY   | 72    | 96      | 30m/12h | Si        | Editar |
+--------------------------------------------------------------------------------+
| Pesos score: Manual | SLA | Quiebre | Venta | Promo | Aging | Penalty          |
+--------------------------------------------------------------------------------+
```

### Configuraciones

- Familia.
- Bucket mode.
- Estrategia.
- Ventana SLA.
- Age max.
- Backoff base y maximo.
- Umbral bajo stock.
- Maximo de reintentos.
- Pesos del score.
- Activacion de fair share.

### Reglas

- Toda modificacion debe auditarse.
- Debe poder verse historico de cambios.
- Cambios deben aplicar a nuevas corridas, no alterar planes ya cerrados.

---

## 16. Pantalla 12 - Mapping de Estados Valkimia

### Objetivo

Administrar el mapeo entre estados externos de Valkimia y estados internos Connexa.

### Usuarios principales

Administrador, IT integraciones.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Mapping Estados Valkimia                                                        |
+--------------------------------------------------------------------------------+
| Source status | Entidad | Estado interno | Activo | Es final | Editar          |
| ACO           | EXEC    | EXEC_RESERVED_ACO | Si   | No       | Editar          |
| PREPARACION   | EXEC    | EXEC_PICKING      | Si   | No       | Editar          |
+--------------------------------------------------------------------------------+
| [Nuevo mapping] [Validar contra eventos recientes] [Exportar]                   |
+--------------------------------------------------------------------------------+
```

### Reglas

- No debe haber estados externos activos sin mapping.
- Cambios deben auditarse.
- Debe permitir marcar estados activos para anti-duplicacion.

---

## 17. Pantalla 13 - Auditoria / Event Log

### Objetivo

Permitir investigar cualquier decision o cambio de estado.

### Usuarios principales

Auditoria, IT soporte, planificador.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Auditoria de Eventos                                                            |
+--------------------------------------------------------------------------------+
| Filtros: Entidad | ID | Evento | Sistema origen | Fecha | Usuario | Estado     |
+--------------------------------------------------------------------------------+
| Fecha | Entidad | ID | Evento | Old | New | Origen | Usuario | Payload        |
| 10:40 | EXEC    | .. | PublishAck | PUBLISHED | ACCEPTED | VAL | system | Ver |
+--------------------------------------------------------------------------------+
```

### Funciones

- Buscar por Need, Plan, Execution, Valkimia ID o SKU.
- Ver payload.
- Ver transicion old/new status.
- Exportar.

---

## 18. Pantalla 14 - Monitor Tecnico de Interfaces

### Objetivo

Dar visibilidad tecnica a IT sobre salud de integraciones.

### Usuarios principales

IT integraciones, soporte.

### Wireframe conceptual

```text
+--------------------------------------------------------------------------------+
| Monitor Tecnico de Interfaces                                                   |
+--------------------------------------------------------------------------------+
| V-01 Stock | V-02 Active | V-03 Publish | V-04 Tracking | V-05 Events          |
| OK 180ms   | OK 320ms    | Warning 2%   | OK 150ms      | No disponible        |
+--------------------------------------------------------------------------------+
| Ultimas llamadas                                                                 |
| Interface | CD | Status | Latencia | Error | Retry | Timestamp | Payload        |
+--------------------------------------------------------------------------------+
```

### Metricas

- Latencia p50/p95.
- Tasa de error.
- Rate limit.
- Timeouts.
- Reintentos.
- Ultima llamada exitosa.
- Payloads fallidos.

---

## 19. Flujo principal de usuario

### Flujo A - Planificacion diaria

```text
Dashboard
  -> Backlog Operativo
  -> Nueva Corrida
  -> Simulador
  -> Aprobar y publicar
  -> Publicacion Valkimia
  -> Ejecucion Logistica
```

### Flujo B - Resolver rechazo por stock

```text
Dashboard / Alertas
  -> Rechazos por stock
  -> Detalle de ExecutionLine
  -> Detalle de Need
  -> Ver next_replan_at
  -> Esperar replanificacion o ajustar prioridad
```

### Flujo C - Evitar duplicacion SGM

```text
Reconciliacion
  -> Ejecuciones externas
  -> Detectar match CD-sucursal-SKU
  -> Vincular a Need
  -> Bloquear publicacion duplicada
  -> Auditar evento
```

### Flujo D - Investigar linea no entregada

```text
Ejecucion Logistica
  -> Transferencia activa / colgada
  -> Detalle de Ejecucion
  -> Timeline eventos
  -> Need relacionada
  -> Event Log / Payload
```

---

## 20. MVP de pantallas recomendado

Para iniciar desarrollo sin sobredimensionar, el MVP visual deberia incluir:

1. Dashboard Ejecutivo.
2. Backlog Operativo.
3. Detalle de Need.
4. Nueva Corrida de Planificacion.
5. Resultado de Plan / Simulador.
6. Publicacion a Valkimia.
7. Ejecucion Logistica.
8. Detalle de Ejecucion.
9. Reconciliacion de Externas.
10. Event Log.
11. Configuracion de Reglas.
12. Monitor Tecnico de Interfaces.

Pantallas que pueden quedar para etapa posterior:

- Gestion avanzada de usuarios.
- Tablero ejecutivo ampliado.
- Cubicaje y optimizacion de viajes.
- Analitica historica avanzada.

---

## 21. Backlog inicial de componentes UI

Componentes reutilizables:

- KPI card.
- Semaforo CD.
- Tabla operativa con filtros persistentes.
- Badge de estado.
- Timeline de eventos.
- Drawer de detalle de linea.
- Modal de confirmacion de publicacion.
- Panel de payload JSON.
- Selector CD/familia/bucket.
- Grafico backlog temporal.
- Grafico distribucion por estado.
- Editor de parametros.
- Visor de errores de integracion.

---

## 22. Criterios de aceptacion UX funcional

La aplicacion se considera operativa si:

- Un planificador puede identificar backlog critico en menos de 2 minutos.
- Un supervisor puede ver si hay problemas por CD en la pantalla inicial.
- Una linea SKU-sucursal puede trazarse desde Need hasta ExecutionLine y EventLog.
- Una publicacion rechazada por stock muestra motivo y proxima replanificacion.
- Un error tecnico muestra interfaz, request, response, reintentos y estado.
- El usuario puede distinguir rechazo de negocio versus error tecnico.
- Las acciones peligrosas piden confirmacion.
- Las tablas principales permiten filtrar, ordenar y exportar.
- Los estados tienen colores y etiquetas consistentes.

---

## 23. Recomendacion visual

Se recomienda usar una interfaz sobria, operativa y de alta densidad, similar a una torre de control logistica:

- Fondo claro.
- Estados con colores consistentes.
- Tablas densas pero legibles.
- Paneles laterales para detalle sin perder contexto.
- KPIs arriba, detalle abajo.
- Timeline siempre disponible para auditoria.
- Acciones masivas protegidas con confirmacion.

Paleta sugerida:

- Verde: correcto / entregado.
- Azul: en proceso / informado.
- Ambar: pendiente / atencion.
- Rojo: critico / rechazado / vencido.
- Gris: hold / cancelado / expirado.

---

## 24. Resultado esperado

Con estas pantallas, Connexa deja de ser un sistema que solo genera solicitudes y pasa a funcionar como una torre de control operativa de distribucion. El usuario puede ver que falta, que se puede planificar, que se publico, que ejecuto Valkimia, que fallo, que esta bloqueado y cual es la siguiente accion esperada.

El objetivo final de la experiencia es simple:

> Ninguna linea debe quedar sin explicacion, sin responsable o sin proxima accion.
