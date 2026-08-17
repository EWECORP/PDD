# PDD — Especificación Frontend y Contrato API

Versión: **1.0**  
Fecha: **2026-08-17**  
Estado: **Contrato para desarrollo frontend y backend de plataforma**  
Ambiente inicial: **TEST — `connexa_platform_test.stock_management`**

## 1. Objetivo

Entregar al equipo frontend un contrato estable para construir el módulo de
Planificación Diaria de Distribución sin acceso directo a PostgreSQL y sin
depender de que estén terminadas las interfaces Valkimia.

El contrato cubre:

- tablero y consulta del backlog DECAS vigente;
- detalle explicable de cálculo, stock y fuentes;
- consulta de corridas y frescura;
- alta y mantenimiento de necesidades dirigidas E/C/A;
- errores, concurrencia, permisos, paginación y criterios UAT.

La definición ejecutable se encuentra en
`backend/contracts/pdd-frontend-openapi-v1.yaml`. Los ejemplos de respuesta de
`backend/contracts/examples/` son sintéticos y pueden utilizarse como mocks.

## 2. Estado real disponible en Test

Foto validada:

| Dato | Valor |
| --- | ---: |
| Fecha operativa | 2026-08-16 |
| Snapshot | `4868597e-f491-48ee-98f3-0f6e248f6431` |
| Corrida backlog | `a258f84f-a965-4777-aafc-350a9cf05e3b` |
| Líneas abiertas | 15.032 |
| Líneas CURRENT | 14.391 |
| Líneas INCOMPLETE | 641 |
| Fuentes atribuidas | 16.699 |
| D abierta | 1.325.851 |
| S abierta | 80.493 |
| Diferencias contra DAILY_DECAS | 0 |
| Líneas sin atribución | 0 |

E/C/A están en cero porque todavía no existen necesidades dirigidas activas.
Los mocks incluyen esos tipos para permitir que frontend termine todos los
estados antes de disponer de datos UAT.

### Disponible hoy

- tablas `stock_management.pdd_*` creadas;
- PDVB, posiciones, D/S y backlog poblados;
- identificadores, versión de fila, frescura, alertas y atribución persistidos;
- procesos Prefect idempotentes y transaccionales.

### Implementado en el backend PDD 0.11.0, pendiente de despliegue

- API HTTP definida en OpenAPI;
- consultas de resumen, backlog, detalle, explicación, filtros y corridas;
- comandos E/C/A transaccionales, versionados, auditables e idempotentes;
- control de permisos, concurrencia, cursores firmados y errores uniformes;
- servicio `systemd`, validador operativo y configuración separada de API.

### Integraciones pendientes de la plataforma Connexa

- conectar el proxy a la autenticación corporativa y a los roles;
- enriquecer códigos con nombres de artículo, sucursal y proveedor;
- implementar interfaz y conciliación Valkimia.

Frontend puede iniciar de inmediato contra los mocks. No debe conectarse
directamente a `connexa_platform_test`.

## 3. Alcance funcional de la UI

### 3.1 Pantalla Resumen

Objetivo: conocer estado y volumen de la foto vigente.

Componentes mínimos:

- fecha operativa, hora de publicación y snapshot;
- indicador CURRENT/STALE/INCOMPLETE;
- cantidades D/E/C/A/S;
- obligatoria, opcional y total;
- cantidad de líneas, artículos, sucursales y proveedores;
- distribución por frescura;
- líneas con IRQ 90/100;
- alertas más frecuentes;
- acceso al backlog filtrado desde cada indicador.

Endpoint: `GET /api/v1/pdd/dashboard/summary`.

### 3.2 Pantalla Backlog

Grano visual:

```text
CD + sucursal + artículo + proveedor
```

Columnas iniciales:

- sucursal;
- artículo;
- proveedor;
- D/E/C/A/S;
- obligatorio, opcional y total;
- IRQ y prioridad;
- fecha objetivo y antigüedad;
- stock de referencia CD;
- bultos, pallets, kg y volumen;
- frescura y alertas;
- versión de fila.

Filtros:

- sucursal, artículo y proveedor;
- uno o más tipos DECAS con saldo;
- obligatorio/opcional;
- IRQ mínimo;
- fecha objetivo;
- frescura;
- solo con alertas;
- búsqueda textual por código o nombre.

Orden predeterminado:

1. prioridad descendente;
2. IRQ descendente;
3. fecha objetivo ascendente, nulos al final;
4. antigüedad;
5. sucursal y artículo como desempate.

La tabla usa paginación por cursor. Cambiar filtros o detectar un snapshot nuevo
reinicia el cursor.

Endpoint: `GET /api/v1/pdd/backlog`.

### 3.3 Detalle explicable

Debe abrirse en no más de tres interacciones desde el resumen y mostrar:

- identidad y versión de la línea;
- cantidades DECAS y obligatoriedad;
- componentes del stock neto;
- PDVB, lead time, días objetivo y sobre-stock;
- crítico, mínimo, máximo, cobertura e IRQ;
- fórmula y redondeo aplicados;
- fuentes D/E/C/A/S y orden de imputación;
- corrida, configuración y snapshots fuente;
- alertas y datos logísticos;
- importación/ejecución cuando esa vertical esté habilitada.

Endpoints:

- `GET /api/v1/pdd/backlog/{backlogLineUuid}`;
- `GET /api/v1/pdd/backlog/{backlogLineUuid}/explanation`.

### 3.4 Necesidades dirigidas E/C/A

Vistas:

- listado filtrable por tipo, estado, vigencia, referencia y responsable;
- formulario de cabecera y múltiples líneas;
- detalle con saldo y actividad;
- historial de versiones;
- acciones activar, cancelar y cerrar según permisos.

E/C/A no son calculadas por el sistema:

- E: compromiso especial;
- C: campaña;
- A: acopio opcional.

La ausencia de stock no cancela ni cierra una necesidad.

## 4. Semántica DECAS

| Tipo | Nombre | Clase | Persistencia |
| --- | --- | --- | --- |
| D | Demanda | Obligatoria | Se reemplaza en la nueva foto diaria |
| E | Especial | Obligatoria | Persiste hasta cumplimiento/cierre |
| C | Campaña | Obligatoria | Persiste durante vigencia y hasta cierre |
| A | Acopio | Opcional | Persiste hasta cumplimiento/vencimiento/cierre |
| S | Sobre-stock | Opcional | Se reemplaza en la nueva foto diaria |

`mandatoryOpenQuantity = D + E + C`  
`optionalOpenQuantity = A + S`  
`totalOpenQuantity = mandatoryOpenQuantity + optionalOpenQuantity`

La prioridad no reserva ni asigna stock.

## 5. Estados

### 5.1 Frescura de backlog

| Estado | Presentación |
| --- | --- |
| CURRENT | Normal; dato completo y vigente |
| STALE | Advertencia; se conserva la última foto válida |
| INCOMPLETE | Advertencia; la línea se muestra con campos faltantes explícitos |

`INCOMPLETE` no significa saldo inválido. En la foto piloto corresponde
principalmente a capacidad de pallet ausente.

### 5.2 Necesidad dirigida

Estado canónico de base/API:

```text
DRAFT -> ACTIVE -> CLOSED
   |         |  \-> EXPIRED
   |         \----> CANCELLED
   \--------------> CANCELLED
```

- `DRAFT`: editable; todavía no participa del backlog;
- `ACTIVE`: aprobada y con líneas abiertas;
- `CLOSED`: sin saldo por cumplimiento o cierre autorizado;
- `CANCELLED`: cancelada con motivo;
- `EXPIRED`: vencida por política explícita.

No se permite reabrir en la primera versión. El término funcional “cumplida” se
representa como `CLOSED` en la cabecera y `FULFILLED` en cada línea.

### 5.3 Línea dirigida

- `OPEN`: saldo igual a cantidad original;
- `PARTIAL`: tiene preparación/cancelación parcial y saldo positivo;
- `FULFILLED`: saldo cero por cumplimiento;
- `CANCELLED`: saldo cero por cancelación.

## 6. Reglas E/C/A

### 6.1 Alta

- tipo exclusivamente E, C o A;
- referencia de negocio obligatoria y única por CD/tipo;
- una o más líneas;
- cantidad original mayor que cero;
- artículo–sucursal debe pertenecer al scope operativo vigente;
- `validTo >= validFrom` cuando se informa;
- DRAFT no requiere aprobador;
- actor se obtiene de la identidad autenticada, no del payload.

### 6.2 Activación

- requiere rol supervisor;
- requiere motivo y versión esperada;
- registra aprobador y timestamp;
- crea una versión append-only;
- participa en el siguiente backlog publicado.

### 6.3 Modificación

- usa bloqueo optimista `expectedVersion`/`If-Match`;
- requiere motivo;
- nunca reduce una cantidad por debajo de lo preparado más lo cancelado;
- una línea con actividad no se elimina: se cancela su saldo;
- conserva antes/después, actor y correlación.

### 6.4 Cancelación y cierre

- cancelar exige motivo y permiso;
- no se cancela cantidad ya preparada;
- cerrar exige saldo cero o autorización explícita según política;
- ninguna acción reescribe versiones anteriores.

## 7. Concurrencia e idempotencia

- respuestas de detalle incluyen `rowVersion` y `ETag`;
- mutaciones requieren `If-Match` o `expectedVersion`;
- una versión desactualizada devuelve HTTP 409 `VERSION_CONFLICT`;
- POST de alta requiere `Idempotency-Key`;
- repetir la misma clave y payload devuelve el resultado original;
- repetir la clave con otro payload devuelve 409 `IDEMPOTENCY_CONFLICT`;
- cursores pertenecen a un `snapshotVersion`;
- si cambia la foto, continuar un cursor devuelve 409 `SNAPSHOT_CHANGED`.

## 8. Permisos

| Capacidad | Viewer | Buyer | Supervisor | Auditor | Technical |
| --- | :---: | :---: | :---: | :---: | :---: |
| Ver resumen/backlog/detalle | Sí | Sí | Sí | Sí | Sí |
| Crear/modificar DRAFT E/C/A | No | Sí | Sí | No | No |
| Activar/cancelar/cerrar | No | No | Sí | No | No |
| Ver auditoría | No | Propia | Sí | Sí | Sí |
| Ver diagnóstico técnico | No | No | No | Sí | Sí |
| Reejecutar/publicar procesos | No | No | No | No | Sí |

Roles lógicos sugeridos:

- `PDD_VIEWER`;
- `PDD_BUYER`;
- `PDD_SUPERVISOR`;
- `PDD_AUDITOR`;
- `PDD_TECHNICAL`.

La identidad y los roles provienen del mecanismo corporativo de Connexa.

## 9. Convenciones API

- base path: `/api/v1/pdd`;
- JSON UTF-8 y nombres `camelCase`;
- timestamps ISO-8601 UTC;
- fechas `YYYY-MM-DD`;
- UUID como string;
- cantidades JSON number con hasta seis decimales;
- volumen con hasta nueve decimales;
- campos ausentes se envían como `null`, no como cero;
- listas vacías se envían como `[]`;
- error uniforme `ProblemDetails` con `code`, `message`, `traceId` y `fieldErrors`;
- `X-Correlation-Id` aceptado y devuelto;
- `Cache-Control: no-store` para mutaciones;
- consultas de foto pueden usar `ETag`.

## 10. Catálogos y nombres

Las tablas PDD conservan códigos. La API debe enriquecer, cuando estén
disponibles, con:

- `branchName`;
- `articleName`;
- `supplierName`.

Los nombres no forman parte de la identidad ni del cursor. Si un maestro no
responde, el código se mantiene y el nombre se devuelve `null`; la línea no se
oculta.

`GET /api/v1/pdd/catalogs/filters` devuelve únicamente valores presentes en la
foto vigente para evitar filtros sin resultados.

## 11. Mapeo físico principal

| Recurso API | Entidad principal | Complementos |
| --- | --- | --- |
| Resumen | `pdd_current_backlog_line` | `pdd_calculation_run` |
| Backlog | `pdd_current_backlog_line` | catálogos corporativos |
| Detalle | `pdd_current_backlog_line` | `pdd_backlog_source_allocation` |
| Explicación D/S | `pdd_need_snapshot` | `pdd_branch_stock_position`, PDVB/configuración |
| Dirigidas | `pdd_directed_need` | líneas y versiones |
| Corridas | `pdd_calculation_run` | `pdd_source_snapshot` |

El frontend no debe conocer IDs bigint internos. Usa UUID públicos y
`rowVersion`. `sourceEntityId` solo se expone en la vista de auditoría.

## 12. Reglas de visualización

- D/E/C usan tratamiento visual de obligatorio;
- A/S usan tratamiento visual de opcional;
- IRQ 100: crítico; 90: alto; 50: medio; 25: bajo; 0: normal;
- `INCOMPLETE` muestra advertencia no bloqueante;
- valores nulos se muestran “Sin dato”; cero se muestra `0`;
- no sumar bultos/pallets/kg/volumen si existen filas nulas sin indicar
  cobertura del agregado;
- toda exportación incluye snapshot, fecha operativa y timestamp;
- no utilizar colores como único medio para expresar estado.

## 13. Rendimiento esperado

Volumen inicial: aproximadamente 15.000 líneas vigentes.

- página predeterminada: 50;
- máximo por página: 200;
- p95 consulta común: menor a 3 segundos;
- debounce búsqueda: 300–500 ms;
- virtualización de filas recomendada;
- filtros y orden se ejecutan en servidor;
- no descargar toda la foto para paginar en navegador.

## 14. Wireframes de referencia

### 14.1 Resumen y backlog

```text
┌ PDD / Backlog ─ Fecha 16/08/2026 ─ Snapshot 4868… ─ INCOMPLETE ┐
│ Obligatorio 1.325.851 │ Opcional 80.493 │ Líneas 15.032       │
│ D 1.325.851 │ E 0 │ C 0 │ A 0 │ S 80.493 │ IRQ alto ...      │
├────────────────────────────────────────────────────────────────┤
│ Sucursal [ ] Artículo [ ] Proveedor [ ] DECAS [ ] IRQ [ ]     │
│ Frescura [ ] Con alertas [ ] Buscar [____________________]     │
├────────────────────────────────────────────────────────────────┤
│ Suc. │ Artículo │ Prov. │ D │ E │ C │ A │ S │ IRQ │ Total │ ! │
│ ...  │ ...      │ ...   │   │   │   │   │   │     │       │   │
└────────────────────────────────────────────────────────────────┘
```

### 14.2 Drawer de explicación

```text
┌ Artículo / Sucursal ─ IRQ ─ Frescura ─ versión ┐
│ DECAS: D | E | C | A | S | total              │
│ Stock: físico + OC + tránsito - compromisos    │
│ PDVB / lead time / crítico / mínimo / máximo   │
│ Fórmula y redondeo                             │
│ Fuentes e imputación: 1 E, 2 C, 3 D, ...       │
│ Corrida / configuración / timestamps / alertas │
└─────────────────────────────────────────────────┘
```

### 14.3 Edición E/C/A

```text
┌ Necesidad dirigida [E|C|A] ─ DRAFT/ACTIVE ─ v3 ┐
│ Referencia │ vigencia │ proveedor │ prioridad   │
│ Responsable │ motivo │ observaciones            │
├──────────────────────────────────────────────────┤
│ Sucursal │ Artículo │ Cantidad │ Objetivo │ SLA  │
│ ...                                              │
├──────────────────────────────────────────────────┤
│ Guardar borrador │ Activar* │ Cancelar* │ Cerrar*│
└──────────────────────────────────────────────────┘
* según estado, versión y permiso
```

## 15. Catálogo mínimo de errores

| HTTP | Código | Acción de UI |
| ---: | --- | --- |
| 400 | `INVALID_QUERY` | Marcar filtros/parámetros inválidos |
| 401 | `UNAUTHENTICATED` | Renovar sesión o redirigir a login |
| 403 | `FORBIDDEN` | Ocultar acción y mostrar falta de permiso |
| 404 | `NO_CURRENT_SNAPSHOT` | Estado vacío con diagnóstico |
| 404 | `RESOURCE_NOT_FOUND` | Cerrar detalle y refrescar lista |
| 409 | `SNAPSHOT_CHANGED` | Informar nueva foto y reiniciar paginación |
| 409 | `VERSION_CONFLICT` | Recargar E/C/A y conservar cambios locales |
| 409 | `IDEMPOTENCY_CONFLICT` | No reintentar automáticamente con otro payload |
| 409 | `DIRECTED_NEED_DUPLICATE` | Mostrar referencia existente |
| 422 | `OUT_OF_SCOPE` | Marcar artículo–sucursal no habilitado |
| 422 | `INVALID_QUANTITY` | Marcar línea y regla incumplida |
| 422 | `INVALID_STATE_TRANSITION` | Refrescar estado y acciones disponibles |
| 503 | `DATA_UNAVAILABLE` | Conservar UI, permitir reintento |

## 16. Historias sugeridas

| ID | Historia | Dependencia |
| --- | --- | --- |
| FE-01 | Ver estado y resumen de la foto vigente | Status + summary mock |
| FE-02 | Filtrar, ordenar y paginar backlog | Backlog mock |
| FE-03 | Navegar al detalle explicable | Detail/explanation mock |
| FE-04 | Mostrar alertas y datos logísticos parciales | Escenario INCOMPLETE |
| FE-05 | Listar y consultar E/C/A | Directed need mock |
| FE-06 | Crear y editar borrador E/C/A | Roles + idempotencia |
| FE-07 | Activar/cancelar/cerrar con confirmación | Supervisor + If-Match |
| FE-08 | Consultar historial de versiones | Versions endpoint |
| FE-09 | Resolver snapshot y versión en conflicto | ProblemDetails mocks |
| FE-10 | Estados loading/empty/error/degraded | Todos los endpoints |
| BE-01 | Implementar status/summary/backlog | Tablas vigentes |
| BE-02 | Implementar detalle y explicación | Atribución + posiciones |
| BE-03 | Implementar comandos E/C/A transaccionales | Versionado/auditoría |
| BE-04 | Integrar identidad, roles y catálogos | Plataforma Connexa |
| QA-01 | Automatizar contrato OpenAPI | Servicio desplegado |
| QA-02 | UAT D/E/C/A/S y conflictos | Backend + frontend |

## 17. Criterios de aceptación frontend

1. El resumen coincide con los totales de la foto vigente.
2. Cambiar un filtro reinicia el cursor.
3. Un cursor de snapshot anterior muestra aviso y refresca, sin mezclar filas.
4. Diferencia correctamente `null` de cero.
5. Una línea INCOMPLETE sigue navegable y explica la carencia.
6. D/E/C aparecen obligatorias y A/S opcionales.
7. El detalle muestra fórmula, stock, PDVB, fuentes, corrida y alertas.
8. Crear dos veces con la misma clave no duplica E/C/A.
9. Editar con versión vencida muestra conflicto recuperable.
10. Activar requiere supervisor y motivo.
11. Una E/C/A activa aparece tras republicar el backlog.
12. Cancelar no elimina la historia.
13. El usuario llega de resumen a explicación en tres interacciones o menos.
14. El diseño funciona con nombres nulos y códigos visibles.
15. La UI no ofrece viajes, rutas, vehículos, reservas ni asignación de stock.

## 18. Escenarios mock obligatorios

- D obligatoria con IRQ 100;
- D+S consolidadas en la misma línea;
- E vencida y E vigente;
- C con varias líneas;
- A opcional;
- factor de pallet faltante;
- PDVB cero sin D/S;
- snapshot cambiado durante paginación;
- conflicto de versión al editar;
- error de validación por cantidad;
- catálogo sin nombre;
- backend temporalmente sin foto vigente.

## 19. Definition of Ready para frontend

- OpenAPI importada en la herramienta del equipo;
- mocks respondiendo;
- componentes y rutas acordados;
- roles simulables;
- diseño contempla carga, vacío, error y stale;
- términos DECAS y obligatoriedad visibles;
- snapshot/rowVersion conservados en estado cliente;
- criterios de aceptación incorporados al backlog del equipo.

## 20. Fuera de alcance

No construir en esta fase:

- asignación o reserva de stock;
- órdenes de distribución;
- prorrateo;
- selección automática para camiones;
- vehículos, viajes, rutas o turnos;
- cubicaje u optimización;
- transferencias intersucursal;
- edición directa de D/S;
- reducción del backlog por una simple selección/importación.

## 21. Entregables del paquete

- esta especificación funcional;
- `backend/contracts/pdd-frontend-openapi-v1.yaml`;
- ejemplos JSON en `backend/contracts/examples/`;
- servidor mock local `backend/tools/run_frontend_mock.py`;
- validador ejecutable `backend/tools/validate_frontend_contract.py`;
- consultas de referencia en `backend/contracts/sql/frontend_reference_queries.sql`;
- contrato físico DDL v2.2 existente;
- foto Test validada para pruebas integradas.
