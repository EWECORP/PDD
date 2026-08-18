# PDD — Diccionario de datos e identidades

Versión: **1.0**  
Fecha: **2026-08-18**  
Estado: **Referencia para desarrollo**  
Contrato físico considerado: **manifiesto DDL v2.6**

## 1. Respuesta corta sobre IDs y UUIDs

PDD usa dos identificadores para propósitos distintos:

- los campos `*_id bigint GENERATED ALWAYS AS IDENTITY` son claves físicas internas. Los genera PostgreSQL y se usan para PK/FK y joins dentro de `connexa_platform_*`;
- los campos `*_uuid uuid` son identidades lógicas, públicas o transportables. Se usan en API, Prefect, manifiestos, idempotencia y referencias entre bases, donde una FK PostgreSQL no es posible.

No todos los UUID se generan igual:

1. Si la aplicación omite una columna declarada con `DEFAULT gen_random_uuid()`, PostgreSQL genera un UUID aleatorio.
2. La aplicación puede enviar explícitamente un UUID a esa misma columna; en ese caso el `DEFAULT` no se ejecuta.
3. Los UUID de una etapa del orquestador se calculan en Python con UUIDv5. Son determinísticos: la misma revisión, etapa, fecha, scope, modelo y configuración producen el mismo UUID.
4. Los UUID permanentes de scope, modelo y configuración provienen de manifiestos o parámetros de runtime. No deben regenerarse en cada corrida.

Por lo tanto, la respuesta correcta no es «los UUID los genera la base» ni «los genera la aplicación»: **depende de la identidad**. La matriz de la sección 5 define cada caso.

## 2. Ubicación y responsabilidad de los datos

| Base | Esquema | Prefijo | Responsabilidad |
|---|---|---|---|
| `connexa_platform_test` | `stock_management` | `pdd_` | Operación de Test, API, gobierno, estados vigentes, auditoría e integración |
| `connexa_platform_ms` | `stock_management` | `pdd_` | La misma capa operativa en Producción |
| `diarco_data` | `datamart` | `dm_pdd_` | Historia analítica pesada, features, scope congelado, estimaciones explicables y backtest |

Las referencias entre `diarco_data` y `connexa_platform_*` son lógicas mediante UUID. PostgreSQL no implementa FK entre bases de datos distintas.

## 3. Flujo principal

```text
dm_pdd_scope_* ───────────────┐
dm_pdd_stock_diario ──────┐   │
dm_pdd_venta_diaria ──────┼──► dm_pdd_pdvb_estimate_detail
                          │              │ publicación validada
                          │              ▼
                          │    pdd_pdvb_estimate + pdd_pdvb_current
                          │              │
                          └──────────────► pdd_branch_stock_position
                                         │
                                         ▼
                                  pdd_need_snapshot (D/S)
                                         │
pdd_directed_need (E/C/A) ───────────────┤
                                         ▼
                              pdd_current_backlog_line
                                         │
                                         ▼
                               pdd_valkimia_import
                                         │
                                         ▼
                               pdd_execution_event
```

`pdd_calculation_run` y `pdd_source_snapshot` atraviesan todo el proceso: identifican cada ejecución y dejan evidencia de sus entradas.

## 4. Diccionario de tablas

### 4.1 Gobierno, scope y corridas

| Tabla | Grano / clave | Función | Campos y relaciones principales |
|---|---|---|---|
| `pdd_configuration_version` | Una versión de `configuration_code`; PK `configuration_version_id`; UUID único | Versiona fórmulas, parámetros DECAS, redondeos, prioridades y reglas operativas | `version_no`, `status`, vigencia, `parameters`, `checksum`, creación y aprobación. Una versión `APPROVED` exige aprobador y fecha. |
| `pdd_pdvb_model_version` | Una versión de `model_code`; PK `model_version_id`; UUID único | Registra la identidad reproducible del modelo PDVB | `parameters`, `implementation_sha256`, commit, vigencia, estado y aprobación. No contiene estimaciones. |
| `pdd_distribution_scope_version` | Una foto del universo del CD; PK `scope_version_id`; UUID único | Cabecera operativa del scope congelado: qué universo de artículos/sucursales puede distribuir CD 41 | Fecha, filtros, conteos, checksum, fuente, estado e `is_current`. Solo puede existir una vigente por CD y debe estar `APPROVED`. |
| `pdd_distribution_scope_article` | `scope_version_id + codigo_articulo` | Membresía de artículos comprables por el CD en una versión de scope | Proveedor primario, flags del CD, hash de la fila fuente. Depende de la cabecera de scope. |
| `pdd_distribution_scope_pair` | `scope_version_id + destination_branch + codigo_articulo` | Membresía distribuible artículo–sucursal | CD origen, ruta, modo de abastecimiento, flags de sucursal y hash. Debe pertenecer a `pdd_distribution_scope_article`; Fase 1 fuerza CD 41/ruta `41CD`. |
| `pdd_calculation_run` | Una ejecución/intentona; PK `calculation_run_id`; UUID único | Cabecera universal de las corridas de scope, preparación, PDVB, DECAS, backtest o publicación | Tipo, fecha de negocio/corte, ámbito, intento, versiones usadas, estado, vigencia, tiempos, conteos, checksums, resumen y error. Es el eje de trazabilidad. |
| `pdd_source_snapshot` | Una fuente por corrida: `calculation_run_id + source_code` | Evidencia qué datos leyó una corrida y si estaban frescos/completos | Base/relación física, lote, rango de fechas, `as_of_ts`, conteo, checksum, frescura, estado y diagnóstico. |

Reglas de lectura:

- `*_version_id` es la FK física local;
- `*_version_uuid` es la identidad estable que cruza API, manifiestos y bases;
- `is_current` indica la proyección vigente, no elimina la historia;
- `checksum` demuestra identidad de contenido; el UUID demuestra identidad de la entidad/versionado.

### 4.2 Publicación y operación PDVB

| Tabla | Grano / clave | Función | Campos y relaciones principales |
|---|---|---|---|
| `pdd_pdvb_publication_batch` | Un lote por `calculation_run_id`; PK ID y UUID único | Controla la copia transaccional desde el datamart hacia la base operativa | Fuente, conteos esperado/stage/publicado, checksums, estado y timestamps. Solo publica si conteo y checksum coinciden. |
| `pdd_pdvb_publication_stage` | `publication_batch_id + sucursal + articulo` | Staging descartable/operativo previo a publicar | Referencias a modelo y scope, método, fallback, estado, confianza, PDVB, checksum y resumen explicativo. `ON DELETE CASCADE` con el lote. |
| `pdd_pdvb_estimate` | Historia por fecha/corrida/par; PK particionada `business_date + pdvb_estimate_id` | Historia operativa compacta de estimaciones publicadas | Une corrida, lote, detalle analítico lógico, modelo, scope y par; conserva método, confianza, valor y explicación. Particionada por fecha. |
| `pdd_pdvb_current` | `origin_cd + articulo + sucursal` | Proyección vigente de PDVB que consume DECAS/API | Apunta a una estimación histórica no bloqueada y conserva fecha, corrida, modelo, scope, valor, estado y confianza. Se actualiza por publicación; no es historia. |
| `pdd_pdvb_quality_issue` | Un hallazgo; PK `quality_issue_id` | Registra problemas de calidad detectados durante PDVB | Corrida, par opcional, severidad, código, evidencia, detalle y resolución. Los abiertos tienen `resolved_at IS NULL`. |
| `pdd_pdvb_backtest_metric` | Corrida + ventana + horizonte + modo + estimador + muestra + segmento + métrica | Copia operativa de métricas agregadas para gobierno/comparación | Modelo/scope, `POINT_DAILY` o `CUMULATIVE`, estimador, muestra, MAE/WAPE/BIAS/RMSE, cobertura y tamaños. Las migraciones v2.4/v2.5 completan el contrato base v2.2. |

Estados PDVB:

- `OK`: cálculo normal;
- `WARN`: publicable con advertencias;
- `ZERO_VALID`: cero válido, distinto de ausencia de dato;
- `BLOCKED`: no hay estimación publicable y `pdvb_value` debe ser `NULL`.

### 4.3 Posiciones y necesidades DECAS

| Tabla | Grano / clave | Función | Campos y relaciones principales |
|---|---|---|---|
| `pdd_item_logistics_snapshot` | Corrida + CD + artículo | Foto de factores logísticos utilizados por DECAS | Unidad base, unidades/bulto, bultos/pallet, peso, volumen, fuente, calidad y checksum. Faltantes no inventan valores; se marcan. |
| `pdd_branch_stock_position` | Fecha + corrida + CD + sucursal + artículo | Foto inmutable y explicable de la posición de stock de sucursal | Stock físico, OC directa, tránsito, compromisos, transferencia pendiente, `net_stock`, PDVB, lead time, niveles objetivo, cobertura, fuentes, configuración y alertas. Particionada. |
| `pdd_cd_stock_position` | Fecha + corrida + CD + artículo | Posición consolidada del CD para contrastar demanda y abastecimiento | Stock físico, OC a tiempo/vencida, backlog obligatorio/opcional, cobertura, snapshots fuente y estado. No reserva ni asigna stock. |
| `pdd_need_snapshot` | Fecha + corrida + CD + sucursal + artículo + tipo D/S | Foto inmutable de necesidades automáticas recalculadas | Cantidades calculada/redondeada/abierta, IRQ, prioridad, objetivo, fórmula/configuración, logística estimada y diagnóstico. `D` es obligatoria; `S` es opcional. |
| `pdd_directed_need` | Una cabecera E/C/A; PK ID y UUID único | Necesidad dirigida persistente creada por usuario/API, no recreada por la corrida diaria | Referencia de negocio, proveedor, vigencia, prioridad, responsable, aprobador, estado, versión, motivo y auditoría. |
| `pdd_directed_need_line` | Necesidad dirigida + sucursal + artículo | Detalle cuantitativo de una E/C/A | Cantidad original, preparada imputada, cancelada, saldo abierto calculado, SLA, unidad, factores logísticos, estado y `row_version`. |
| `pdd_directed_need_version` | Necesidad dirigida + `version_no` | Historial de cambios de una necesidad dirigida | Estado anterior/posterior JSON, actor, motivo, vigencia y correlación de la petición. |

Campos calculados por PostgreSQL:

- `pdd_branch_stock_position.net_stock = physical_stock + direct_po_inbound + cd_in_transit - special_sale_committed - confirmed_transfer_pending`;
- `pdd_directed_need_line.open_quantity = max(original - prepared_allocated - cancelled, 0)`.

Tipos DECAS:

| Código | Significado | Persistencia |
|---|---|---|
| `D` | Déficit automático obligatorio | Se recalcula en cada snapshot |
| `S` | Sobre-stock automático opcional | Se recalcula en cada snapshot |
| `E` | Necesidad dirigida especial | Persiste hasta cierre/cancelación |
| `C` | Necesidad dirigida comercial/comprometida | Persiste hasta cierre/cancelación |
| `A` | Necesidad dirigida adicional/opcional | Persiste hasta cierre/cancelación |

### 4.4 Backlog, Valkimia, integración y auditoría

| Tabla | Grano / clave | Función | Campos y relaciones principales |
|---|---|---|---|
| `pdd_current_backlog_line` | CD + sucursal + artículo + proveedor normalizado | Proyección vigente y reconstruible del saldo DECAS | UUID estable de línea, UUID de foto, cantidades D/E/C/A/S, totales calculados, prioridad, fechas, importado/preparado/tránsito, logística, frescura y versión optimista. No es una orden. |
| `pdd_backlog_source_allocation` | Línea backlog + tipo + entidad fuente + fecha fuente | Explica qué necesidad aporta al saldo y cómo se imputa el preparado | Cantidad aportada/preparada, orden y versión de regla. «Allocation» es atribución contable, no asignación de stock. |
| `pdd_valkimia_import` | Una importación; PK ID y UUID único | Cabecera idempotente de una foto enviada/importada por un adaptador Valkimia | Clave de idempotencia, adaptador, UUID de snapshot backlog, referencia externa, estado, actor, conteos, cantidades, checksum y detalle. |
| `pdd_valkimia_import_line` | Importación + UUID de línea backlog | Relaciona cada línea enviada con su seguimiento externo | Versión del backlog, par, cantidad importada/preparada, estado normalizado, referencias externas y versión de fila. |
| `pdd_execution_event` | Un evento externo deduplicado | Ledger append-only de ejecución Valkimia | Importación/línea, tipo, estado, semántica DELTA/CUMULATIVE, cantidad, documento, remito/ETA, tiempos, mapping, hash y procesamiento. Importar no reduce por sí solo la necesidad. |
| `pdd_integration_message` | Mensaje idempotente por interfaz + dirección + clave | Inbox/outbox técnico de integraciones y API | Correlación, tipo, estado, referencia/hash de payload, reintentos, tiempos y error. |
| `pdd_business_event_log` | Un evento de negocio | Auditoría transversal append-only | Entidad/ID, evento, actor, correlación, motivo, antes/después y metadatos. |

Campos calculados del backlog:

- `mandatory_open_quantity = D + E + C`;
- `optional_open_quantity = A + S`;
- `total_open_quantity = D + E + C + A + S`;
- `active_imported_quantity` informa cuánto del mismo backlog está importado; **no se suma** a `total_open_quantity`.

### 4.5 Datamart analítico

| Tabla | Grano / clave | Función | Campos y relaciones principales |
|---|---|---|---|
| `dm_pdd_stock_diario` | Fecha + artículo + sucursal | Stock diario normalizado desde LEGACY | Cantidad y signo, disponibilidad, componentes de fecha fuente, procesamiento, regla de cierre, hash y normalización. Ausencia de fila significa desconocido, no cero. Particionada. |
| `dm_pdd_venta_diaria` | Fecha + artículo + sucursal | Feature diario canónico para PDVB | UUID de scope y corrida feature, jerarquía comercial, unidades observadas/devueltas/basales/promocionales, precios, surtido, disponibilidad, stock asociado, promociones, elegibilidad, exclusiones y linaje. Particionada. |
| `dm_pdd_pdvb_estimate_detail` | Fecha de negocio + corrida + artículo + sucursal | Detalle histórico completo, reproducible y explicable de PDVB | UUIDs lógicos de corrida/modelo/scope, ventanas, medias/pesos, cobertura, ADI/CV², método, fallback, confianza, PDVB crudo/final, explicación y publicación. Particionada. |
| `dm_pdd_pdvb_backtest_detail` | Evaluación + corrida + par + origen + horizonte + modo + estimador | Observación detallada de backtest rolling-origin | Predicción, demanda real, cobertura, errores, muestra, estimador/parámetros, régimen de demanda, jerarquía y exclusiones. Contrato final = DDL v2.2 + migraciones v2.4/v2.5. |
| `dm_pdd_scope_version` | UUID de versión | Cabecera sellada del universo analítico reproducible | Código/versión, antecesor, CD/fecha, filtros, conteos, checksums, captura y detalle. Aquí el UUID es la PK. |
| `dm_pdd_scope_article` | UUID scope + artículo | Membresía analítica de artículos | Proveedor, flags del CD, timestamp/hash fuente y captura. |
| `dm_pdd_scope_pair` | UUID scope + sucursal + artículo | Membresía analítica de pares distribuibles | CD, proveedor, ruta/modo, flags, timestamp/hash y captura. |
| `dm_pdd_pdvb_backtest_run` | `calculation_run_uuid` | Cabecera de una campaña de backtest | Modelo/scope, rangos origen/evaluación, horizonte, modo, cobertura mínima, estimadores, parámetros, avance, conteos, estado y error. |
| `dm_pdd_pdvb_backtest_metric` | Corrida + modo + estimador + muestra + segmento + métrica | Métricas agregadas analíticas para comparar modelos | MAE/WAPE/BIAS/RMSE, tamaño y coberturas, ceros y sumas reales/predichas. Su PK técnica es identity; la unicidad funcional es compuesta. |

## 5. Matriz de generación de identidades

### 5.1 IDs numéricos

Todos los campos declarados `bigint GENERATED ALWAYS AS IDENTITY` los genera **PostgreSQL** al insertar. La aplicación normalmente los obtiene con `RETURNING` y los usa inmediatamente como FK.

Incluye, entre otros, `configuration_version_id`, `model_version_id`, `scope_version_id`, `calculation_run_id`, `publication_batch_id`, `pdvb_estimate_id`, `need_snapshot_id`, `directed_need_id`, `backlog_line_id`, `valkimia_import_id` y los IDs de eventos/mensajes.

Regla de desarrollo: no exponer estos IDs como identidad pública ni copiarlos entre Test, Producción y `diarco_data`. Su valor solo tiene significado dentro de la base que lo generó.

### 5.2 UUIDs

| UUID | Default de BD | Generador efectivo actual | Política |
|---|---|---|---|
| `configuration_version_uuid` | `gen_random_uuid()` | Normalmente manifiesto/aplicación al registrar la configuración | Permanente por versión; no cambia por corrida. |
| `model_version_uuid` | `gen_random_uuid()` | Manifiesto cargado por la aplicación | Permanente por versión del modelo; se replica igual al operacional. |
| `scope_version_uuid` operativo | `gen_random_uuid()` | Aplicación copia el UUID de `dm_pdd_scope_version` | Debe conservar exactamente la identidad analítica. |
| `dm_pdd_scope_version.scope_version_uuid` | Sin default | Parámetro/manifiesto enviado por aplicación | La inserción debe proporcionarlo. Es PK analítica. |
| `calculation_run_uuid` operativo | `gen_random_uuid()` | Aplicación: UUIDv4 en jobs independientes o UUIDv5 en etapas del orquestador | No depender del default en flujos idempotentes. |
| UUIDs de etapa del pipeline | No son columna separada | `uuid5(namespace, revision|stage|date|scope|model|config)` en Python | Repetir la misma etapa reutiliza identidad; cambiar `pipeline_revision` crea otra. |
| `feature_run_uuid` | Sin default | Aplicación: UUIDv4 si el caller no lo envía | Identifica la materialización de features de venta. |
| UUIDs lógicos en `dm_pdd_*` | Sin default | Aplicación/parámetros | Copian corrida, modelo y scope para trazabilidad cross-database. |
| `publication_batch_uuid` operativo | `gen_random_uuid()` | Aplicación genera UUIDv4 y lo inserta explícitamente | Une lote operativo con marcas de publicación analíticas. |
| `directed_need_uuid` | `gen_random_uuid()` | Base de datos; el API omite la columna y lee `RETURNING` | Identidad pública estable de la necesidad dirigida. |
| `backlog_line_uuid` | `gen_random_uuid()` | Base al crear una línea nueva; el job lo conserva en updates | Identidad estable de la línea, distinta de `snapshot_version`. |
| `snapshot_version` del backlog | Sin default | Aplicación genera UUIDv4 por publicación de backlog | Todas las líneas de la misma foto comparten el UUID. |
| `valkimia_import_uuid` | `gen_random_uuid()` | Base si la aplicación lo omite | Identidad pública de la importación; la idempotencia real está en `adapter_code + idempotency_key`. |
| `correlation_id` | Sin default | Middleware/API genera UUIDv4 o acepta uno válido del cliente | Traza una petición a través de mensaje, versión y evento de negocio; no es PK. |
| `dm_pdd_pdvb_backtest_run.calculation_run_uuid` | Sin default | Job de backtest genera UUIDv4 | Es PK de la campaña analítica y referencia lógica en sus detalles/métricas. |

Importante: `DEFAULT gen_random_uuid()` solo actúa cuando el `INSERT` omite la columna o usa `DEFAULT`. Si el `INSERT` contiene un valor, PostgreSQL lo conserva y valida `NOT NULL/UNIQUE`.

### 5.3 Identidad, idempotencia y correlación no son sinónimos

| Concepto | Pregunta que responde | Ejemplo |
|---|---|---|
| PK identity | ¿Cómo uno filas eficientemente dentro de esta base? | `calculation_run_id` |
| UUID lógico | ¿Qué entidad/version/corrida es esta entre procesos o bases? | `calculation_run_uuid` |
| Clave de idempotencia | ¿Ya procesé esta orden del cliente/sistema? | `adapter_code + idempotency_key` |
| Correlation ID | ¿Qué mensajes y eventos pertenecen a una misma petición? | `correlation_id` |
| Checksum/hash | ¿El contenido es exactamente el mismo? | `scope_checksum`, `payload_hash` |
| Clave natural/funcional | ¿Se repite el mismo hecho de negocio? | fecha + corrida + sucursal + artículo |

No conviene reemplazar una por otra. Dos intentos pueden compartir una clave de negocio pero tener corridas distintas; dos payloads no deben compartir clave de idempotencia si su hash difiere.

## 6. Convenciones de campos

| Patrón | Semántica |
|---|---|
| `business_date` | Día operativo al que pertenece el resultado |
| `cutoff_date` | Último día de información permitido; debe ser anterior a `business_date` |
| `*_at` | Instante con zona (`timestamptz`) salvo que el origen legacy no la provea |
| `*_by`, `actor_id` | Usuario o servicio responsable |
| `status` | Estado de la entidad; consultar el `CHECK` de su tabla, no asumir catálogo global |
| `is_current` | Marca la versión/corrida vigente sin borrar historia |
| `row_version` | Control de concurrencia optimista, no versión de modelo |
| `source_*` | Linaje físico y temporal del dato de entrada |
| `input_checksum`, `source_row_hash`, `payload_hash` | Evidencia de contenido para reproducibilidad/idempotencia |
| `detail`, `summary`, `explanation`, `evidence`, `metadata` | Extensión JSON explicativa; no debe ocultar campos indispensables para filtros o constraints |
| `alert_codes`, `exclusion_codes` | Catálogos de razones múltiples en arrays de texto |
| `origin_cd` | CD de origen; Fase 1 restringe el valor a 41 |
| `codigo_articulo`, `sucursal`, `c_proveedor_primario` | Claves de negocio provenientes del ecosistema Diarco |

## 7. Reglas para implementar nuevos INSERTs

1. Omitir siempre los `*_id GENERATED ALWAYS AS IDENTITY` y recuperar el valor con `RETURNING` cuando sea necesario.
2. En procesos idempotentes, generar/resolver el UUID antes del `INSERT` y enviarlo explícitamente.
3. En entidades CRUD simples cuyo UUID tiene default, se puede omitir el UUID y leerlo con `RETURNING` dentro de la misma transacción.
4. Nunca transformar un `*_id` local en referencia cross-database; transportar el UUID lógico.
5. No generar nuevamente UUID de scope/modelo/configuración al arrancar un job. Se reciben como parámetros y se validan contra el manifiesto/registro.
6. No usar un UUID aleatorio como única solución de idempotencia. Mantener además la restricción de negocio o `idempotency_key` y validar el hash.
7. Insertar cabecera y dependencias en una única transacción cuando la identidad de la cabecera sea necesaria para las líneas.
8. Respetar las claves compuestas con `business_date` en tablas particionadas.

Ejemplo: UUID generado por la base para una necesidad dirigida:

```sql
INSERT INTO stock_management.pdd_directed_need (
    origin_cd, need_type, business_reference, valid_from,
    owner_user, status, reason, created_by, updated_by
) VALUES (
    41, 'E', :reference, :valid_from,
    :owner, 'DRAFT', :reason, :actor, :actor
)
RETURNING directed_need_id, directed_need_uuid;
```

Ejemplo: UUID definido por la aplicación para una corrida reanudable:

```sql
INSERT INTO stock_management.pdd_calculation_run (
    calculation_run_uuid, run_type, business_date, cutoff_date,
    scope_id, status, created_by
) VALUES (
    :precomputed_uuid, :run_type, :business_date, :cutoff_date,
    :scope_id, 'RUNNING', :actor
)
RETURNING calculation_run_id;
```

## 8. Decisiones que el equipo debe conservar

- Historia y vigente son objetos separados: `pdd_pdvb_estimate` frente a `pdd_pdvb_current`; snapshots frente a backlog vigente.
- D/S se recalculan; E/C/A persisten.
- El backlog es una proyección de saldos, no una orden, reserva ni asignación de stock.
- Una importación Valkimia representa el mismo backlog y no crea demanda adicional.
- Los eventos de ejecución y auditoría son append-only.
- Scope, modelo y configuración son versiones inmutables: un cambio relevante crea otra versión y otro UUID.
- Los `dm_pdd_*` guardan historia pesada; los `pdd_*` dan servicio a operación/API y conservan trazabilidad compacta.

## 9. Fuentes normativas

Este documento resume el contrato compuesto por:

- `PDD - 00 Manifiesto DDL v2.6.sql`;
- DDL operativo Core y DECAS v2.2;
- DDL analítico v2.2;
- migraciones analíticas y operativas v2.3–v2.5;
- migración de prefijo operativo v2.6;
- implementación actual de `pdd_backend` para publicación, API, backlog, features, backtest y orquestación diaria.

Ante una diferencia, la secuencia de DDL/migraciones aplicada a la base es el contrato físico; el código debe adaptarse a ella y este documento debe versionarse.
