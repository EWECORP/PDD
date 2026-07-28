# Especificación de Requerimiento de Software

Sistema: **Planificación Diaria de Necesidades de Distribución — Connexa**
Versión: **2.1 — Alcance Fase 1 integrado**
Fecha: **2026-07-28**
Estado: **Listo para refinamiento, construcción y UAT**
Fuente rectora: `PDD - ALCANCE Fase 1.md`

---

## 1. Propósito y resultado

Definir el producto entregable en 40 días para que Connexa calcule y priorice necesidades DECAS, mantenga un backlog diario trazable y permita la ejecución oportunista desde Valkimia.

La Fase 1 termina en la **planificación de necesidades y seguimiento de su cumplimiento**. No incluye gestión de distribución ni optimización logística.

## 2. Alcance

### 2.1 Incluido

- foto diaria de stock y pipeline;
- Stock Neto Sucursal;
- PDVB, coberturas y umbrales;
- NDD-D y NDD-S automáticas;
- NDD-E, NDD-C y NDD-A dirigidas;
- IRQ y prioridad;
- backlog consolidado por artículo–sucursal–proveedor;
- cobertura de Base 2/CD;
- datos informativos de peso, volumen, bultos y pallets;
- consulta/importación oportunista desde Valkimia;
- tracking de importado, preparado, despachado y tránsito según datos disponibles;
- recálculo diario, alertas, auditoría y monitoreo.

### 2.2 Excluido

- creación o gestión de órdenes de distribución;
- asignación, reserva o prorrateo de stock;
- gestión de transferencias intersucursal;
- selección automática de líneas para un vehículo;
- flota, vehículos, viajes, rutas, ventanas y turnos;
- cubicaje y optimización de carga;
- picking, carga, despacho o recepción como procesos administrados por Connexa;
- optimización intradía y simulación logística;
- migración obligatoria a Valkimia WEB;
- reemplazo integral de SGM fuera de este circuito.

Una referencia a peso, volumen, pallet, camión o tránsito no amplía el alcance: en Fase 1 es dato informativo o resultado externo.

## 3. Glosario

| Término | Definición |
| --- | --- |
| PDVB | Promedio Diario de Venta Basal |
| Stock Neto Sucursal | Stock físico + ingresos confirmados − compromisos |
| NDD | Necesidad de Distribución |
| DECAS | D Demanda, E Especial, C Campaña, A Acopio, S Sobre-stock |
| Obligatoria | Línea D/E/C que Valkimia puede seleccionar, pero no debe ocultarse mientras tenga saldo |
| Opcional | Línea A/S ofrecida como oportunidad |
| IRQ | Índice de Riesgo de Quiebre, entre 0 y 100 |
| Backlog | Saldo abierto y trazable de necesidades |
| Importación Valkimia | Selección de líneas por el operador; no equivale a cumplimiento |
| Preparado | Cantidad efectivamente confirmada por Valkimia |
| Pipeline | Ingresos o movimientos confirmados aún no recibidos |
| Base 2/CD | Centro de distribución origen inicial |

## 4. Actores y responsabilidades

| Actor | Responsabilidad en Fase 1 |
| --- | --- |
| Comprador/Comercial | Consultar posición; crear y mantener E/C/A; gestionar alertas |
| Supervisor | Aprobar excepciones según umbral; controlar cierre y UAT |
| Operador Valkimia | Filtrar, seleccionar e importar backlog; ejecutar por fuera de Connexa |
| Valkimia/WMS | Conservar IDs Connexa e informar cantidades y estados reales |
| Proceso diario | Validar fuentes, calcular, consolidar y publicar la foto vigente |
| Datos/IT | Operar interfaces, parámetros, alertas técnicas y reconciliación |
| Auditor | Consultar fórmulas, versiones, eventos y cambios |

Connexa no asume el rol de planificador de transporte ni de operador de depósito.

## 5. Reglas y fórmulas normativas

```text
stock_neto_sucursal =
  stock_fisico_cierre
  + ingresos_confirmados
  - stock_comprometido

stock_critico = PDVB × lead_time
stock_minimo  = PDVB × 2 × lead_time
stock_maximo  = PDVB × dias_stock
sobre_stock   = PDVB × dias_sobre_stock

NDD_D = max(stock_maximo - stock_neto_sucursal, 0)

NDD_S = max(
  (stock_maximo + sobre_stock)
  - max(stock_neto_sucursal, 0)
  - NDD_D,
  0
)
```

La corrección del signo de NDD-D queda registrada en el alcance rector. Toda fórmula se implementa versionada.

IRQ inicial:

| Condición | IRQ |
| --- | ---: |
| `stock_neto <= 0` | 100 |
| `0 < cobertura < lead_time` | 90 |
| `lead_time <= cobertura <= 2 × lead_time` | 50 |
| `2 × lead_time < cobertura < dias_stock` | 25 |
| `cobertura >= dias_stock` | 0 |

Si `PDVB = 0`, la cobertura no se divide y no se generan D/S; la línea queda informada para tratamiento manual.

## 6. Requerimientos funcionales

### 6.1 Ingesta y calidad

#### RF-001. Capturar la foto diaria

El sistema debe recibir por fecha operativa:

- stock físico de sucursal al cierre anterior;
- ingresos directos de OC confirmados;
- tránsito confirmado desde Base 2;
- ventas especiales comprometidas;
- transferencias confirmadas pendientes;
- stock físico e ingresos de Base 2;
- PDVB y parámetros;
- maestro artículo–sucursal–proveedor;
- unidades logísticas disponibles.

Aceptación:

- cada lote conserva fuente, fecha/hora, conteo y estado;
- no se mezclan fechas operativas sin advertencia;
- una fuente obligatoria ausente bloquea solo el ámbito afectado;
- toda degradación es visible.

#### RF-002. Validar maestros y parámetros

Debe detectar artículo, sucursal o proveedor inexistente; PDVB negativo; lead time o días faltantes; unidad inválida y duplicados de fuente.

#### RF-003. Conservar trazabilidad de entrada

Para cada valor usado debe poder recuperarse lote, timestamp y valor original.

### 6.2 Corrida diaria

#### RF-010. Ejecutar y reejecutar

Debe ejecutar una corrida diaria automática y permitir reejecución autorizada.

- una corrida tiene ID, fecha, versión de fórmula, inicio, fin y estado;
- solo una versión queda vigente por ámbito;
- reejecutar reemplaza la foto vigente; nunca suma el resultado previo;
- una corrida fallida no sustituye la última foto válida.

#### RF-011. Calcular Stock Neto Sucursal

Debe aplicar la fórmula normativa y conservar cada componente.

#### RF-012. Calcular umbrales y cobertura

Debe calcular crítico, mínimo, máximo, sobre-stock y días de cobertura con redondeo parametrizado.

#### RF-013. Generar NDD-D

Debe generar una línea D cuando la cantidad calculada sea mayor que cero, clasificada como obligatoria.

#### RF-014. Generar NDD-S

Debe generar únicamente el tramo adicional S, separado de D y clasificado como opcional.

#### RF-015. Calcular IRQ

Debe asignar IRQ, regla aplicada y explicación. Los compromisos E/C vencidos o próximos prevalecen en el orden final.

#### RF-016. Explicar el cálculo

La UI y la API deben exponer fórmula, valores, parámetros, redondeo, alertas y corrida.

#### RF-017. Manejar reglas de borde

- ningún saldo será negativo;
- `PDVB=0` no produce D/S;
- un parámetro inválido genera línea rechazada y alerta;
- las unidades se convierten solo con factor maestro vigente;
- el redondeo no modifica la cantidad fuente.

### 6.3 Necesidades dirigidas

#### RF-020. Crear NDD-E

Campos mínimos: sucursal, artículo, cantidad, fecha/SLA, referencia de negocio, prioridad, responsable y observación.

#### RF-021. Crear NDD-C

Campos mínimos: campaña, vigencia desde/hasta, proveedor, artículos, sucursales, cantidades, fecha objetivo y responsable.

#### RF-022. Crear NDD-A

Campos mínimos: sucursal, artículo, cantidad, motivo, vigencia, fecha requerida y responsable.

#### RF-023. Mantener identidad y saldo

E/C/A deben tener ID estable, cantidad original, preparada imputada, cancelada y saldo.

#### RF-024. Versionar cambios

Un cambio de cantidad, vigencia, prioridad o estado requiere motivo, actor y versión; no reescribe la historia.

#### RF-025. Detectar posible duplicado

Debe advertir coincidencias de tipo, referencia, sucursal, artículo y vigencia. La advertencia no fusiona registros automáticamente.

#### RF-026. Cerrar o cancelar

Solo se cierra por cumplimiento, vencimiento según política o acción autorizada con motivo. La falta de stock no cierra una necesidad.

### 6.4 Consolidación y backlog

#### RF-030. Consolidar DECAS

Debe producir una vista por fecha, CD, sucursal, artículo y proveedor, preservando cantidades D/E/C/A/S por separado.

#### RF-031. Clasificar obligatoriedad

D/E/C son obligatorias; A/S son opcionales. La clasificación debe acompañar toda salida.

#### RF-032. Priorizar

Orden mínimo:

1. E/C vencidas;
2. E/C por vencer;
3. mayor IRQ;
4. mayor antigüedad;
5. fecha objetivo más próxima;
6. clave determinística de desempate.

La prioridad no asigna stock.

#### RF-033. Recalcular sin duplicar

D/S se sustituyen por la nueva foto. E/C/A conservan identidad y saldo. El pipeline confirmado se descuenta una sola vez.

#### RF-034. Imputar cumplimiento

La cantidad preparada se imputa a las fuentes de una línea consolidada con regla determinística y auditable. Regla inicial: E vencida, E vigente, C, D, A, S; dentro del tipo, fecha objetivo y antigüedad.

#### RF-035. Mantener remanente

Importar o seleccionar no reduce backlog. Solo un evento válido de preparación, despacho o cancelación autorizada modifica saldos.

#### RF-036. Exponer Base 2

Debe mostrar demanda consolidada, stock físico, OC pendientes on-time/vencidas e índice de cobertura. El dato se etiqueta como referencia, no como reserva.

#### RF-037. Exponer unidades logísticas

Cuando existan factores vigentes debe mostrar unidades, bultos, pallets, kg y volumen estimados; un dato faltante no impide mostrar la necesidad.

### 6.5 Integración oportunista Valkimia

#### RF-040. Consultar backlog elegible

El adaptador debe ofrecer a Valkimia consulta paginada y filtrable por CD, sucursal, proveedor, DECAS, obligatoriedad, prioridad, IRQ, fecha, peso, volumen, bultos y pallets.

#### RF-041. Identificar líneas

Cada línea debe incluir `need_line_id`, versión, fecha operativa, tipo DECAS, sucursal, artículo, proveedor, cantidad abierta, prioridad, IRQ, fechas y unidades.

#### RF-042. Registrar importación

Valkimia debe confirmar qué versión y cantidad importó. La operación usa clave idempotente y puede ser parcial.

#### RF-043. Evitar duplicación

La misma clave no crea dos importaciones. Una versión vencida devuelve conflicto y obliga a refrescar.

#### RF-044. Recibir ejecución

Debe recibir por línea:

- referencia Valkimia;
- cantidad importada;
- cantidad preparada acumulada o delta inequívoco;
- estado externo;
- timestamp;
- opcionalmente remito, despacho, ETA y recepción.

#### RF-045. Procesar preparación parcial

La parte preparada se imputa; el saldo no preparado permanece abierto.

#### RF-046. Conservar estado externo

Debe guardar estado original y normalizado. Un código desconocido genera alerta y no cierra la línea.

#### RF-047. Operar contingencia

Si Valkimia no puede consumir la interfaz, se permite exportación/importación controlada con los mismos IDs e idempotencia. No se crea un backlog alternativo.

### 6.6 Cierre, paneles y administración

#### RF-050. Cerrar el día

Debe reconciliar eventos recibidos, actualizar pipeline, controlar duplicados y habilitar la siguiente foto.

#### RF-051. Panel operativo

Debe mostrar por proveedor–sucursal–artículo: stock neto, cobertura, DECAS, IRQ, prioridad, importado, preparado, tránsito, saldo, SLA, frescura y alertas.

#### RF-052. Alertas

Mínimas:

- quiebre o cobertura crítica;
- compromiso E/C vencido o próximo;
- parámetros/datos ausentes o vencidos;
- importación sin avance;
- preparación parcial;
- estado externo desconocido;
- referencia duplicada o resultado ambiguo;
- diferencia inválida de cantidades.

#### RF-053. Auditoría

Altas, cambios, corridas, consolidaciones, importaciones, eventos externos, imputaciones, reintentos y cierres generan eventos append-only.

#### RF-054. Parametrización

Debe versionar PDVB/lead time/días, umbrales IRQ, redondeos, prioridades, imputación, frescura, polling y mappings.

#### RF-055. Separar permisos

Compras no ejecuta reintentos técnicos; IT no modifica necesidades comerciales sin permiso; Valkimia solo consume y reporta dentro del contrato.

## 7. Estados mínimos

### Corrida

`STARTED`, `VALIDATING`, `CALCULATING`, `COMPLETED`, `FAILED`, `SUPERSEDED`.

### Necesidad dirigida

`DRAFT`, `ACTIVE`, `FULFILLED`, `EXPIRED`, `CANCELLED`.

### Línea ofrecida a Valkimia

`OPEN`, `IMPORTED_PARTIAL`, `IMPORTED`, `PREPARED_PARTIAL`, `PREPARED`, `DISPATCHED`, `CANCELLED`, `TECHNICAL_ERROR`, `UNKNOWN_EXTERNAL_STATUS`.

Los estados de ejecución describen información recibida; no convierten a Connexa en gestor logístico.

## 8. Modelo lógico mínimo

| Entidad | Propósito |
| --- | --- |
| `calculation_run` | Corrida y versión vigente |
| `source_snapshot` | Evidencia de fuentes |
| `branch_stock_position` | Componentes de stock neto |
| `need_snapshot` | D/S calculadas e IRQ |
| `directed_need` / `directed_need_line` | E/C/A persistentes |
| `current_backlog_line` | Proyección consolidada vigente |
| `backlog_source_allocation` | Origen DECAS e imputación |
| `valkimia_import` / `valkimia_import_line` | Selección oportunista |
| `execution_event` | Preparado/despacho/estado externo |
| `configuration_version` | Fórmulas y parámetros |
| `integration_message` | Inbox/outbox e idempotencia |
| `business_event_log` | Auditoría |

No implementar en Fase 1 entidades `trip`, `route`, `vehicle`, `load_plan`, `reservation`, `allocation_run` ni `branch_transfer_request`.

## 9. Interfaces mínimas

### IF-01. Datos diarios de entrada

Batch o API idempotente por fuente y fecha operativa. Debe soportar validación previa, rechazo por línea y control de totales.

### IF-02. Consulta de backlog para Valkimia

`GET` lógico paginado con filtros, versión de foto y totales informativos.

### IF-03. Confirmación de importación

`POST` lógico idempotente con versión y cantidades seleccionadas.

### IF-04. Eventos de ejecución

`POST`/polling lógico idempotente por documento, línea, tipo de evento y timestamp.

### IF-05. Consulta operativa Connexa

APIs para panel, detalle explicable, excepciones, alertas, corridas y auditoría.

El adaptador oculta endpoints, tablas y códigos específicos de la versión instalada de Valkimia.

## 10. Requerimientos no funcionales

- **RNF-01 Idempotencia:** reintentos de lotes, importaciones y eventos no duplican efectos.
- **RNF-02 Trazabilidad:** de una línea se navega a fuente, fórmula, excepción, importación y ejecución.
- **RNF-03 Rendimiento:** la corrida completa termina dentro de la ventana acordada; consultas comunes responden p95 < 3 s bajo volumen de diseño.
- **RNF-04 Consistencia:** actualización de eventos e imputación es transaccional o compensable.
- **RNF-05 Seguridad:** autenticación corporativa, mínimo privilegio, secretos fuera de logs y payloads protegidos.
- **RNF-06 Observabilidad:** métricas, correlación, colas, latencia, errores, estados desconocidos y frescura.
- **RNF-07 Recuperación:** última foto válida sigue consultable si falla una corrida.
- **RNF-08 Configurabilidad:** cambios versionados, con vigencia y auditoría.
- **RNF-09 Usabilidad:** fórmulas, timestamps, obligatoriedad y saldos son visibles.
- **RNF-10 Evolución:** el dominio no depende de la versión actual o WEB de Valkimia.

## 11. Criterios de aceptación de Fase 1

1. Una muestra acordada reproduce Stock Neto Sucursal y D/S con exactitud.
2. El signo de NDD-D y los bordes `PDVB=0`, stock negativo y parámetros faltantes están probados.
3. E/C/A conservan identidad y saldo entre dos corridas.
4. DECAS se consolida sin perder origen ni obligatoriedad.
5. IRQ y prioridad se explican por línea.
6. Dos confirmaciones iguales de importación producen un solo efecto.
7. Una preparación parcial reduce solo lo confirmado.
8. Una línea importada pero no preparada permanece en backlog.
9. La corrida del día siguiente no duplica pipeline ni excepciones.
10. Stock Base 2 y unidades logísticas se muestran como información, no como asignación.
11. Un estado Valkimia desconocido queda alertado y no cierra la necesidad.
12. Compras navega del panel al cálculo y a la ejecución en no más de tres interacciones.
13. Auditoría reconstruye los cambios de una línea.
14. UAT demuestra de punta a punta D, E, C, A y S.
15. No existen funciones de viajes, rutas, vehículos, cubicaje, optimización o transferencias intersucursal.

## 12. Plan mínimo de pruebas

- unitarias de fórmulas, IRQ, redondeo, prioridad e imputación;
- propiedades: no negatividad, conservación de cantidades e idempotencia;
- integración de todas las fuentes;
- contrato Valkimia: filtros, paginación, versión vencida, parcial, timeout y duplicado;
- reconciliación de acumulados/deltas y estados desconocidos;
- rendimiento de corrida y consulta;
- permisos y auditoría;
- UAT con datos reales anonimizados o controlados;
- regresión del recálculo durante al menos tres días operativos simulados.

## 13. Inicio del equipo de desarrollo

### 13.1 Orden de construcción

1. **Vertical 0 — Contratos y datos:** fixtures reales, catálogo, decisiones y prueba de conectividad Valkimia.
2. **Vertical 1 — Cálculo:** snapshots, Stock Neto, D/S, IRQ y explicación.
3. **Vertical 2 — Dirigidas:** altas E/C/A, vigencia, versiones y saldos.
4. **Vertical 3 — Backlog:** consolidación, prioridad, imputación y panel.
5. **Vertical 4 — Valkimia:** consulta/importación, idempotencia y ejecución parcial.
6. **Vertical 5 — Cierre:** recálculo, alertas, auditoría, operación y UAT.

### 13.2 Plan Día 1–40

| Período | Resultado |
| --- | --- |
| D1–D5 | decisiones críticas, datos de prueba, contratos, arquitectura y backlog refinado |
| D6–D14 | cálculo diario vertical con detalle explicable |
| D10–D18 | E/C/A y parámetros, en paralelo con UI base |
| D15–D24 | consolidado DECAS, IRQ, prioridad, Base 2 y panel |
| D20–D30 | integración Valkimia, parcialidad, idempotencia y monitor |
| D31–D35 | cierre diario, reconciliación, seguridad y rendimiento |
| D36–D38 | UAT punta a punta y correcciones |
| D39–D40 | despliegue controlado, capacitación y estabilización |

### 13.3 Definición de terminado

Una historia está terminada cuando tiene criterios automatizados, trazabilidad, permisos, observabilidad, documentación de contrato y evidencia con fixture representativo. Una épica no termina solo con UI o persistencia aislada: debe demostrar su vertical de punta a punta.

## 14. Decisiones críticas de los primeros cinco días

No deben frenar la preparación técnica, pero sí cerrarse antes de comprometer UAT:

1. ratificación funcional del signo y redondeo de NDD-D/NDD-S;
2. granularidad y fuente oficial de PDVB, lead time y días;
3. composición exacta de ingresos y compromisos;
4. unidad base y factores logísticos;
5. regla de prioridad e imputación;
6. contrato pull/importación con Valkimia y campo de ID Connexa;
7. semántica de cantidad preparada: delta o acumulada;
8. estados que prueban despacho/tránsito;
9. volumen, ventana y SLA de frescura;
10. calendario exacto del Día 1 al Día 40.

Toda decisión se registra en un ADR o acta breve y actualiza la configuración o el contrato correspondiente.

## 15. Evolución posterior

Gestión de Distribución Inteligente, asignación, reservas, prorrateo, transferencias, vehículos, viajes, rutas, cubicaje y optimización se mantienen en un backlog de Fase 2 separado. No se anticipan entidades, pantallas ni reglas de esas capacidades dentro del MVP.

