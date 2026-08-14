# Modelo de Datos Conceptual — Fase 1

Versión: **2.1**
Fecha: **2026-07-28**
Estado: **Base para modelo físico**

---

## 1. Objetivo y límites

Modelar cálculo diario, DECAS, backlog, consulta/importación Valkimia y ejecución por línea. El modelo no administra distribución.

Entidades prohibidas en Fase 1:

```text
allocation_run, reservation, branch_transfer_request,
vehicle, trip, route, load_plan, load_optimization, capacity_slot
```

Peso, volumen, bultos y pallets son atributos derivados o snapshots informativos, no entidades de planificación.

## 2. Principios

1. snapshots históricos inmutables;
2. proyección vigente separada;
3. D/S recalculadas y E/C/A persistentes;
4. necesidad, importación y ejecución separadas;
5. eventos externos append-only;
6. idempotencia mediante claves explícitas;
7. cantidades e imputaciones por línea;
8. configuración versionada;
9. adaptadores fuera del dominio;
10. sin anticipar Fase 2.

## 3. Mapa de entidades

```text
CalculationRun
  ├── SourceSnapshot
  ├── BranchStockPosition
  └── NeedSnapshot (D/S)
              │
DirectedNeed ─┴── DirectedNeedLine (E/C/A)
              │
              v
      CurrentBacklogLine
              │
              └── BacklogSourceAllocation
                         │
                         v
              ValkimiaImportLine ── ValkimiaImport
                         │
                         v
                   ExecutionEvent

ConfigurationVersion
IntegrationMessage
BusinessEventLog
```

## 4. Corrida y fuentes

### `pdd_calculation_run`

Campos:

- `calculation_run_id`;
- `business_date`;
- `scope_type`, `scope_id`;
- `formula_version`;
- `status`;
- `is_current`;
- inicio/fin;
- resumen de conteos y cantidades;
- actor.

Unicidad: una corrida vigente por fecha y ámbito.

### `pdd_source_snapshot`

- corrida;
- tipo de fuente;
- lote;
- `as_of_ts`;
- obligatoriedad y frescura;
- conteos/checksum;
- estado y errores.

## 5. Posición de stock

### `pdd_branch_stock_position`

Grano:

```text
corrida + CD + sucursal + artículo
```

Campos:

- stock físico;
- ingreso OC directo;
- tránsito desde CD;
- compromiso venta especial;
- transferencia confirmada pendiente;
- Stock Neto Sucursal;
- PDVB;
- lead time;
- días stock/sobre-stock;
- crítico, mínimo, máximo, sobre-stock;
- cobertura;
- IDs de snapshots fuente;
- explicación y alertas.

Las transferencias aparecen solo como cantidad fuente; no tienen ciclo gestionado.

### `pdd_cd_stock_position`

Grano: corrida + CD + artículo.

Campos:

- stock físico de referencia;
- OC pendiente on-time;
- OC vencida;
- demanda DECAS consolidada;
- índice de cobertura;
- timestamp.

No contiene reserva o cantidad asignada.

## 6. Necesidades automáticas

### `pdd_need_snapshot`

Grano:

```text
corrida + CD + sucursal + artículo + tipo(D|S)
```

Campos:

- `need_snapshot_id`;
- proveedor;
- tipo;
- obligatorio/opcional;
- cantidad calculada y redondeada;
- IRQ;
- prioridad;
- fecha objetivo;
- fórmula y parámetros;
- explicación;
- alertas;
- factores/logística estimada;
- estado de cálculo.

Es inmutable. La nueva corrida crea otra foto.

## 7. Necesidades dirigidas

### `pdd_directed_need`

Cabecera:

- `directed_need_id`;
- tipo `E`, `C` o `A`;
- referencia;
- proveedor;
- vigencia;
- prioridad;
- responsable/aprobador;
- estado;
- versión;
- motivo/observación;
- timestamps.

### `pdd_directed_need_line`

Grano: necesidad + sucursal + artículo.

Campos:

- cantidad original;
- fecha objetivo/SLA;
- preparada imputada;
- cancelada;
- saldo;
- unidad;
- factores logísticos snapshot;
- última actividad.

Restricción: el saldo nunca es negativo.

### `pdd_directed_need_version`

Conserva antes/después, actor, motivo y vigencia de cambios.

## 8. Backlog vigente

### `pdd_current_backlog_line`

Vista o proyección reconstruible:

```text
fecha vigente + CD + sucursal + artículo + proveedor
```

Campos:

- `backlog_line_id`;
- `snapshot_version`;
- D/E/C/A/S abiertas;
- obligatorio total;
- opcional total;
- cantidad total abierta;
- IRQ/prioridad;
- fechas;
- importado activo;
- preparado;
- tránsito;
- saldo;
- Base 2 de referencia;
- bultos/pallets/kg/volumen estimados;
- frescura y alertas.

No es un segundo maestro editable.

### `pdd_backlog_source_allocation`

Explica e imputa:

- línea de backlog/importación;
- tipo e ID fuente;
- cantidad aportada;
- cantidad preparada imputada;
- orden;
- versión de regla.

El término `allocation` refiere a atribución contable del cumplimiento, no a asignación de stock.

## 9. Importación Valkimia

### `pdd_valkimia_import`

- `valkimia_import_id`;
- clave idempotente;
- adaptador;
- CD;
- fecha/hora;
- operador/sistema;
- versión de foto;
- referencia externa;
- estado;
- totales.

### `pdd_valkimia_import_line`

- importación;
- línea backlog;
- versión de línea;
- artículo/sucursal;
- cantidad importada;
- cantidad preparada;
- estado normalizado;
- referencia/línea externa;
- última actualización.

Unicidad: adaptador + clave idempotente + línea.

Importar no reduce el saldo de necesidad.

## 10. Ejecución

### `pdd_execution_event`

Evento inmutable:

- `execution_event_id`;
- clave de deduplicación;
- importación/línea;
- documento y línea externa;
- tipo (`IMPORTED`, `PREPARED`, `DISPATCHED`, `CANCELLED`, etc.);
- estado externo y normalizado;
- cantidad delta o acumulada con semántica explícita;
- remito/ETA opcional;
- timestamp externo y de recepción;
- payload técnico protegido;
- versión de mapping.

La proyección actual se deriva de eventos válidos.

## 11. Datos logísticos informativos

### `pdd_item_logistics_snapshot`

Puede estar embebido en la corrida o referenciado por versión:

- unidad base;
- unidades por bulto;
- bultos por pallet;
- peso;
- volumen;
- fuente y vigencia;
- estado de calidad.

Si falta, la necesidad continúa con indicador `logistics_data_missing`.

## 12. Transversales

### `pdd_configuration_version`

Fórmulas, parámetros, IRQ, prioridad, imputación, redondeos, frescura y mappings, con vigencia y aprobación.

### `pdd_integration_message`

Inbox/outbox:

- correlación/idempotencia;
- interfaz;
- dirección;
- estado;
- hash;
- intentos;
- timestamps;
- error;
- referencia al payload protegido.

### `pdd_business_event_log`

Entidad, ID, evento, actor, fecha, correlación, antes/después y motivo.

## 13. Saldos

```text
directed_open =
  max(original - prepared_allocated - cancelled, 0)

automatic_open =
  max(current_calculated - valid_pipeline_at_snapshot, 0)

import_unprepared =
  max(imported - prepared, 0)

backlog_open =
  suma de fuentes vigentes menos cumplimiento imputado
```

`import_unprepared` y `backlog_open` no se suman: la importación es una vista del mismo universo, no nueva demanda.

## 14. Controles e índices

Controles:

- cantidades no negativas;
- un solo snapshot vigente;
- evento externo deduplicado;
- preparado no superior al permitido sin corrección explícita;
- E/C/A no recreadas por corrida;
- D/S no acumuladas entre fotos;
- versión de línea validada al importar;
- fuente y fórmula recuperables;
- ningún campo de reserva, viaje o carga.

Índices:

- backlog por proveedor/sucursal/artículo/IRQ/SLA;
- corrida por fecha/ámbito;
- dirigida por tipo/estado/vigencia;
- importación por clave/referencia/estado;
- evento por documento/línea/fecha;
- mensaje por correlación/estado;
- auditoría por entidad/fecha.

## 15. Pendientes de modelo físico

- motor y esquema;
- volumen y particionado;
- unidad y precisión decimal;
- estrategia de proyección vigente;
- transacción inbox/outbox;
- locking idempotente;
- retención de snapshots/payloads;
- seguridad por ámbito;
- semántica acumulada o delta de Valkimia;
- catálogo final de estados.

