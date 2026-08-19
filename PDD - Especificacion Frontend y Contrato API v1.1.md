# PDD — Especificación Frontend y Contrato API

Versión: **1.1**  
Fecha: **2026-08-19**  
Estado: **Contrato aprobado para frontend y backend Java**  
Ambiente inicial: **TEST — `connexa_platform_test.stock_management`**

## 1. Propósito y propiedad

Este documento permite desarrollar el módulo de Planificación Diaria de
Distribución sin acceso directo a PostgreSQL y sin depender de que estén
terminadas las interfaces Valkimia.

La definición ejecutable es
`backend/contracts/pdd-frontend-openapi-v1.yaml`. El OpenAPI es la fuente de
verdad para paths, parámetros, payloads, respuestas y errores.

Responsabilidades:

- **Python/Prefect:** carga, calidad, cálculo PDVB/DECAS y publicación de tablas
  `stock_management.pdd_*`;
- **backend Java Stock Management:** API REST, casos de uso E/C/A, seguridad,
  auditoría e integración con la librería
  `connexa-platform-lib-model-stockmanagement`;
- **frontend Connexa:** consume únicamente la API;
- **mock local:** simula el contrato y no es un backend productivo.

## 2. Foto Test de referencia

Foto validada después del orquestador diario completo:

| Dato | Valor |
| --- | ---: |
| Fecha operativa | 2026-08-16 |
| Snapshot | `00ce50c9-6eac-48b7-9c0a-2425638c76b2` |
| Corrida backlog | `3f146fea-4852-58f4-ba12-797f475455d8` |
| Líneas abiertas | 14.792 |
| Líneas CURRENT | 14.212 |
| Líneas INCOMPLETE | 580 |
| D abierta | 1.296.792 |
| S abierta | 79.640 |
| Total abierto | 1.376.432 |
| Líneas sin atribución | 0 |

E/C/A están en cero porque aún no existen necesidades dirigidas activas. Los
mocks incluyen E/C/A sintéticas para desarrollar todos los estados.

## 3. Base URL y convenciones

Base pública:

```text
/connexa/api/v1/pdd
```

Si el gateway o `server.servlet.context-path` aporta `/connexa`, el controller
Java mapea internamente `/api/v1/pdd`. El consumidor siempre usa la base
pública y no debe conocer esa composición.

- JSON UTF-8 y propiedades `camelCase`;
- fechas `YYYY-MM-DD`;
- timestamps ISO-8601 UTC;
- UUID como string;
- cantidades con hasta seis decimales y volumen con hasta nueve;
- dato desconocido es `null`, no cero;
- listas sin elementos son `[]`;
- autenticación Bearer JWT corporativa;
- `X-Correlation-Id` aceptado y devuelto;
- errores `application/problem+json` según OpenAPI.

## 4. Pantallas y operaciones

### 4.1 Resumen

`GET /dashboard/summary`

Mostrar fecha, publicación, snapshot, frescura, D/E/C/A/S, obligatorio,
opcional, total, líneas, artículos, sucursales, proveedores, IRQ y alertas.
Cada indicador puede navegar al backlog con el filtro correspondiente.

### 4.2 Backlog

`GET /backlog`

Grano: `CD + sucursal + artículo + proveedor`.

Columnas iniciales:

- sucursal, artículo y proveedor, con código visible aunque falte nombre;
- D/E/C/A/S, obligatorio, opcional y total;
- IRQ, prioridad, fecha objetivo y antigüedad;
- stock CD de referencia;
- bultos, pallets, kg y volumen;
- frescura, alertas y versión.

Filtros: sucursal, artículo, proveedor, tipos DECAS, obligatorio/opcional, IRQ,
fecha, frescura, con alertas y búsqueda textual.

La paginación es por cursor. Cambiar filtros reinicia el cursor. Si se publicó
otro snapshot, la API devuelve 409 `SNAPSHOT_CHANGED` y la UI reinicia la lista.

### 4.3 Detalle explicable

- `GET /backlog/{backlogLineUuid}`;
- `GET /backlog/{backlogLineUuid}/explanation`.

Mostrar cantidades, posición de stock, PDVB, lead time, niveles crítico/mínimo/
máximo, fórmula, redondeo, fuentes DECAS, imputación, corrida, configuración,
snapshots fuente, logística y alertas.

### 4.4 Necesidades dirigidas E/C/A

- `GET|POST /directed-needs`;
- `GET|PUT /directed-needs/{directedNeedUuid}`;
- `POST /directed-needs/{directedNeedUuid}/activate`;
- `POST /directed-needs/{directedNeedUuid}/cancel`;
- `POST /directed-needs/{directedNeedUuid}/close`;
- `GET /directed-needs/{directedNeedUuid}/versions`.

La UI ofrece listado, formulario con múltiples líneas, detalle, historial y
acciones según estado/rol. D y S nunca son editables.

### 4.5 Diagnóstico y catálogos

- `GET /status`;
- `GET /calculation-runs/{calculationRunUuid}`;
- `GET /catalogs/filters`.

Los catálogos devuelven solo valores presentes en la foto vigente. Si falla un
maestro, se conserva el código y el nombre es `null`; no se oculta la línea.

## 5. Semántica DECAS

| Tipo | Nombre | Clase | Persistencia |
| --- | --- | --- | --- |
| D | Demanda | Obligatoria | Reemplazada por la foto diaria |
| E | Especial | Obligatoria | Hasta cumplimiento/cierre |
| C | Campaña | Obligatoria | Durante vigencia y hasta cierre |
| A | Acopio | Opcional | Hasta cumplimiento/vencimiento/cierre |
| S | Sobre-stock | Opcional | Reemplazada por la foto diaria |

```text
mandatory = D + E + C
optional  = A + S
total     = mandatory + optional
```

La prioridad no reserva ni asigna stock.

## 6. Estados y reglas E/C/A

Cabecera:

```text
DRAFT -> ACTIVE -> CLOSED
   |         |  \-> EXPIRED
   |         \----> CANCELLED
   \--------------> CANCELLED
```

Línea: `OPEN`, `PARTIAL`, `FULFILLED`, `CANCELLED`.

Reglas principales:

- tipo exclusivamente E, C o A;
- referencia única por CD/tipo y al menos una línea;
- cantidad original mayor que cero;
- par artículo–sucursal dentro del scope vigente;
- `validTo >= validFrom`;
- actor tomado de la sesión, no del payload;
- activar/cancelar/cerrar requiere supervisor y motivo;
- no reducir por debajo de lo preparado más lo cancelado;
- una línea con actividad se cancela, no se elimina;
- no reabrir estados terminales en v1;
- ausencia de stock no cancela la necesidad.

## 7. Concurrencia e idempotencia

- detalle incluye `rowVersion` y `ETag`;
- PUT y acciones requieren `If-Match`;
- versión vencida: 409 `VERSION_CONFLICT`;
- alta requiere `Idempotency-Key`;
- misma clave y payload devuelve el resultado original;
- misma clave con otro payload: 409 `IDEMPOTENCY_CONFLICT`;
- mutaciones usan `Cache-Control: no-store`.

## 8. Roles

| Capacidad | VIEWER | BUYER | SUPERVISOR | AUDITOR | TECHNICAL |
| --- | :---: | :---: | :---: | :---: | :---: |
| Ver resumen/backlog/detalle | Sí | Sí | Sí | Sí | Sí |
| Crear/modificar DRAFT | No | Sí | Sí | No | No |
| Activar/cancelar/cerrar | No | No | Sí | No | No |
| Ver auditoría | No | Propia | Sí | Sí | Sí |
| Diagnóstico técnico | No | No | No | Sí | Sí |

Authorities: `PDD_VIEWER`, `PDD_BUYER`, `PDD_SUPERVISOR`, `PDD_AUDITOR`,
`PDD_TECHNICAL`.

## 9. Errores que debe resolver la UI

| HTTP | Código | Comportamiento |
| ---: | --- | --- |
| 400 | `INVALID_QUERY` | Marcar parámetros |
| 401 | `UNAUTHENTICATED` | Renovar sesión/login |
| 403 | `FORBIDDEN` | Ocultar acción y explicar permiso |
| 404 | `NO_CURRENT_SNAPSHOT` | Estado vacío con diagnóstico |
| 404 | `RESOURCE_NOT_FOUND` | Cerrar detalle y refrescar |
| 409 | `SNAPSHOT_CHANGED` | Reiniciar paginación |
| 409 | `VERSION_CONFLICT` | Recargar conservando cambios locales |
| 409 | `IDEMPOTENCY_CONFLICT` | No reintentar con otro payload automático |
| 422 | `OUT_OF_SCOPE` | Marcar línea |
| 422 | `INVALID_QUANTITY` | Marcar campo/regla |
| 422 | `INVALID_STATE_TRANSITION` | Refrescar estado y acciones |
| 503 | `DATA_UNAVAILABLE` | Mostrar degradado y permitir reintento |

## 10. Rendimiento y UX

- volumen piloto aproximado: 15.000 líneas;
- página predeterminada 50, máximo 200;
- p95 objetivo menor a 3 segundos;
- filtros/orden en servidor;
- debounce de búsqueda 300–500 ms;
- no descargar toda la foto para paginar;
- distinguir visualmente obligatorio de opcional;
- no usar color como único indicador;
- exportaciones incluyen snapshot, fecha operativa y timestamp.

## 11. Historias mínimas

| ID | Historia |
| --- | --- |
| FE-01 | Estado y resumen vigente |
| FE-02 | Filtrar, ordenar y paginar backlog |
| FE-03 | Detalle explicable |
| FE-04 | Alertas y datos logísticos incompletos |
| FE-05 | Listar y consultar E/C/A |
| FE-06 | Crear/editar DRAFT |
| FE-07 | Activar/cancelar/cerrar |
| FE-08 | Historial de versiones |
| FE-09 | Resolver conflictos de snapshot/versión |
| FE-10 | Loading, empty, error y degraded |
| BE-01 | Lecturas status/summary/backlog |
| BE-02 | Detalle, explicación y catálogos |
| BE-03 | Comandos E/C/A transaccionales |
| BE-04 | JWT, roles, nombres y observabilidad |
| QA-01 | Contract testing OpenAPI |
| QA-02 | UAT DECAS y concurrencia |

## 12. Criterios de aceptación

1. El resumen coincide con la foto vigente.
2. Filtros nuevos reinician el cursor.
3. No se mezclan snapshots durante paginación.
4. `null` y cero se muestran de forma diferente.
5. INCOMPLETE sigue navegable y explica la carencia.
6. D/E/C son obligatorias; A/S opcionales.
7. El detalle explica fórmula, stock, PDVB, fuentes y corrida.
8. Repetir una alta con la misma clave no duplica E/C/A.
9. Una versión vencida produce conflicto recuperable.
10. Activar requiere supervisor y motivo.
11. E/C/A activa aparece en la siguiente foto publicada.
12. Cancelar no elimina historia.
13. Frontend nunca consulta PostgreSQL directamente.
14. La API Java no depende del runtime Python.

## 13. Fuera de alcance v1

- reserva o asignación de stock;
- órdenes de distribución y prorrateo;
- selección automática para camiones;
- vehículos, rutas, viajes o turnos;
- cubicaje/optimización;
- transferencias intersucursal;
- edición de D/S;
- reducir backlog por una simple selección/importación.

## 14. Entregables

- esta especificación funcional;
- OpenAPI v1.1 en `backend/contracts/pdd-frontend-openapi-v1.yaml`;
- ejemplos JSON y mock local en `backend/contracts`/`backend/tools`;
- especificación Java `PDD - Especificación Implementación API Java Stock Management v1.0.md`;
- consultas de referencia para repositorios Java;
- DDL y diccionario físico vigentes.
