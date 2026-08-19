# PDD — Especificación de implementación API Java en Stock Management

Versión: **1.0**  
Fecha: **2026-08-19**  
Estado: **Lista para estimación e implementación por el equipo backend Java**

## 1. Decisión de arquitectura

El backend Python `diarco-pdd-backend` es exclusivamente el motor analítico y
de movimiento de datos: normaliza fuentes, calcula PDVB y DECAS, publica las
entidades `stock_management.pdd_*` y se orquesta con Prefect.

La API consumida por el frontend Connexa debe implementarse en Java dentro del
backend de Stock Management. La API no ejecuta Python ni dispara flujos
Prefect. Ambos componentes se integran mediante el contrato persistente de
PostgreSQL.

```text
diarco_data                         connexa_platform_*.stock_management
fuentes -> Python/Prefect  ──────►  pdd_*  ◄──── Java/Spring Boot API
                                                      │
                                                      ▼
                                                Frontend Connexa
```

Esta separación permite recalibrar el algoritmo sin cambiar la API y permite
evolucionar la UI sin acoplarla a tablas analíticas de `diarco_data`.

## 2. Resultado de la revisión de `PDD_BACK`

`E:\ETL\PDD_BACK` no es un microservicio ejecutable. Es la librería:

- `com.zeetrex.connexa.platform:connexa-platform-lib-model-stock-management`;
- Spring Boot 3.4.3 y Java 21;
- Spring Data JPA, MapStruct 1.6.3, Lombok, PostgreSQL y Flyway;
- arquitectura hexagonal con modelo, puertos de repositorio y adaptadores JPA;
- paquete raíz `com.zeetrex.lib.model.stockmanagement`.

Por lo tanto, la solución requiere dos entregas Java:

1. **Librería `PDD_BACK`:** modelos de dominio, entidades JPA, proyecciones,
   puertos, repositorios, mappers y migraciones de `stock_management.pdd_*`.
2. **Microservicio Stock Management:** controllers, DTO HTTP, boundaries,
   servicios de aplicación/casos de uso, seguridad JWT, manejo de errores y
   publicación SpringDoc.

No deben agregarse controllers ni configuración web a `PDD_BACK`.

## 3. Tecnologías y convenciones obligatorias

| Tema | Decisión |
| --- | --- |
| Runtime | Java 21, de acuerdo con el `pom.xml` real de `PDD_BACK` |
| Framework | Spring Boot 3.4.3 |
| Persistencia | Spring Data JPA/PostgreSQL; consultas nativas o proyecciones para lecturas agregadas |
| Mapeo | MapStruct; no exponer entidades JPA como respuestas HTTP |
| Migraciones | Flyway desde la librería de modelo Stock Management |
| Seguridad | Spring Security OAuth2 Resource Server/JWT corporativo |
| Contrato | OpenAPI 3.1 `backend/contracts/pdd-frontend-openapi-v1.yaml` |
| Documentación | SpringDoc en los endpoints estándar del microservicio |
| Base pública | `/connexa/api/v1/pdd` |
| Base interna | Puede ser `/api/v1/pdd` si `/connexa` es `context-path` o prefijo del gateway; nunca duplicarlo |
| Fechas | `LocalDate` |
| Timestamps | `Instant` y JSON ISO-8601 UTC |
| Cantidades | `BigDecimal`; no usar `Double` para unidades, peso, volumen o importes |
| UUID públicos | `UUID` en persistencia y DTO; nunca exponer bigint internos |
| JSONB | `JsonNode` o tipo acordado, con `@JdbcTypeCode(SqlTypes.JSON)` |
| Arrays PostgreSQL | mapear `text[]` o proyectar a `List<String>` de forma probada |

## 4. Estructura propuesta

### 4.1 En `PDD_BACK`

Agregar subpaquetes `pdd` para no mezclar planificación con las entidades
históricas `stk_*`:

```text
com.zeetrex.lib.model.stockmanagement
├── domain/model/pdd
├── domain/repository/pdd
├── domain/repository/dto/pdd
└── infrastructure/persistence
    ├── entity/pdd
    ├── mapper/pdd
    ├── repository/pdd
    ├── repository/dto/pdd
    └── repository/jpa/pdd
```

Mantener el patrón existente:

- puerto de dominio basado en `GenericRepository` cuando corresponda;
- implementación basada en `GenericJpaRepository` para agregados mutables;
- interfaz `JpaRepository<Entidad, TipoId>`;
- mapper `GenericEntityMapper` con `componentModel = "spring"`;
- repositorios de consulta específicos para filtros, cursores y agregados.

### 4.2 En el microservicio ejecutable

Usar el package raíz real del microservicio Stock Management y organizar PDD:

```text
...stockmanagement
├── controller/pdd
├── application/dto/pdd
├── application/boundary/pdd
├── application/service/pdd
├── domain/service/pdd
└── application/config
```

Los DTO definidos por el OpenAPI pertenecen al microservicio, no a la librería
de modelo. Si Connexa utiliza `GenericBoundary`/`GenericApiBoundary`, los
controllers PDD deben integrarlos sin cambiar el contrato HTTP.

## 5. Modelo de persistencia requerido por la API

### 5.1 Proyecciones de solo lectura

| Recurso | Tablas principales |
| --- | --- |
| Estado y resumen | `pdd_current_backlog_line`, `pdd_calculation_run` |
| Listado backlog | `pdd_current_backlog_line` |
| Detalle y fuentes | `pdd_current_backlog_line`, `pdd_backlog_source_allocation` |
| Explicación | `pdd_need_snapshot`, `pdd_branch_stock_position`, `pdd_item_logistics_snapshot` |
| Corrida y frescura | `pdd_calculation_run`, `pdd_source_snapshot` |
| Validación de scope | `pdd_distribution_scope_pair`, versión vigente |

Para backlog conviene una proyección de consulta y no cargar un grafo JPA.
Debe preservar el orden estable:

```text
priority_score DESC, irq_score DESC, target_date NULLS LAST,
oldest_need_date, sucursal, codigo_articulo, backlog_line_uuid
```

El cursor debe incluir `snapshotVersion`, orden y filtros normalizados. Nunca se
continúa una página usando otro snapshot.

### 5.2 Agregado transaccional E/C/A

| Agregado/soporte | Tabla |
| --- | --- |
| Cabecera | `pdd_directed_need` |
| Líneas | `pdd_directed_need_line` |
| Historial append-only | `pdd_directed_need_version` |
| Idempotencia/integración | `pdd_integration_message` |
| Auditoría | `pdd_business_event_log` |

La cabecera es la raíz del agregado. Crear, reemplazar, activar, cancelar y
cerrar se ejecutan cada uno en una única transacción. La versión histórica y el
evento de negocio se insertan antes del commit.

Los campos `row_version`/`version_no` implementan concurrencia optimista. Los
campos generados por PostgreSQL (`mandatory_open_quantity`,
`optional_open_quantity`, `total_open_quantity`, `net_stock`) deben mapearse
como no insertables/no actualizables.

## 6. Catálogo de endpoints y casos de uso

| Método y ruta relativa | operationId | Caso de uso | Rol mínimo |
| --- | --- | --- | --- |
| GET `/status` | `getPddStatus` | Estado funcional y snapshot actual | PDD_VIEWER |
| GET `/dashboard/summary` | `getDashboardSummary` | Totales y frescura | PDD_VIEWER |
| GET `/backlog` | `listBacklog` | Filtros, orden y cursor | PDD_VIEWER |
| GET `/backlog/{uuid}` | `getBacklogLine` | Detalle vigente | PDD_VIEWER |
| GET `/backlog/{uuid}/explanation` | `getBacklogExplanation` | Fórmula, stock y fuentes | PDD_VIEWER |
| GET `/directed-needs` | `listDirectedNeeds` | Listado E/C/A | PDD_VIEWER |
| POST `/directed-needs` | `createDirectedNeed` | Crear DRAFT idempotente | PDD_BUYER |
| GET `/directed-needs/{uuid}` | `getDirectedNeed` | Cabecera y líneas | PDD_VIEWER |
| PUT `/directed-needs/{uuid}` | `replaceDirectedNeed` | Versionar DRAFT | PDD_BUYER |
| POST `/{uuid}/activate` | `activateDirectedNeed` | Aprobar y activar | PDD_SUPERVISOR |
| POST `/{uuid}/cancel` | `cancelDirectedNeed` | Cancelar saldo | PDD_SUPERVISOR |
| POST `/{uuid}/close` | `closeDirectedNeed` | Cerrar | PDD_SUPERVISOR |
| GET `/{uuid}/versions` | `listDirectedNeedVersions` | Auditoría de versiones | PDD_AUDITOR |
| GET `/calculation-runs/{uuid}` | `getCalculationRun` | Linaje de corrida | PDD_AUDITOR |
| GET `/catalogs/filters` | `getPddFilterCatalogs` | Valores de la foto vigente | PDD_VIEWER |

Las rutas abreviadas `/{uuid}/...` de la tabla pertenecen a
`/directed-needs`. El OpenAPI es la fuente exacta de verdad.

### 6.1 Clases sugeridas en el microservicio

| Capa | Clases/responsabilidad |
| --- | --- |
| Controller | `PddStatusController`, `PddDashboardController`, `PddBacklogController`, `PddDirectedNeedController`, `PddCalculationRunController`, `PddCatalogController` |
| Boundary de consulta | `PddStatusBoundary`, `PddBacklogQueryBoundary`, `PddRunQueryBoundary`, `PddCatalogBoundary` |
| Boundary de comando | `DirectedNeedCommandBoundary` |
| Servicios | `PddBacklogQueryService`, `PddExplanationService`, `DirectedNeedApplicationService`, `PddAuthorizationService` |
| Repositorios | `PddBacklogQueryRepository`, `PddRunQueryRepository`, `PddScopeQueryRepository`, `PddDirectedNeedRepository`, `PddAuditRepository`, `PddIdempotencyRepository` |

Los nombres pueden adaptarse a la convención exacta del microservicio, pero la
separación consulta/comando y las responsabilidades no deben perderse. Los
controllers validan el contrato y delegan; no construyen SQL, no administran
transacciones y no contienen transiciones de estado.

## 7. Contratos transversales

### 7.1 Identidad y autorización

- Validar el JWT corporativo con Spring Security.
- Obtener usuario y roles del `SecurityContext`; ignorar cualquier actor
  enviado por el cliente.
- Aplicar autorización en boundary o método (`@PreAuthorize`).
- `PDD_TECHNICAL` no habilita automáticamente mutaciones funcionales.

### 7.2 Idempotencia

`POST /directed-needs` requiere `Idempotency-Key`:

1. normalizar y hashear el payload;
2. buscar por interfaz, dirección y clave;
3. misma clave y hash: devolver el resultado original;
4. misma clave y otro hash: HTTP 409 `IDEMPOTENCY_CONFLICT`;
5. crear necesidad, versión, evento y registro de idempotencia en una
   transacción.

### 7.3 Concurrencia

- GET de detalle devuelve `ETag` basado en `rowVersion`.
- PUT y acciones requieren `If-Match`.
- Actualizar con condición `uuid AND version_no = expectedVersion`.
- Cero filas modificadas devuelve 409 `VERSION_CONFLICT`.
- No resolver conflictos con last-write-wins.

### 7.4 Errores y observabilidad

- `application/problem+json` con los campos definidos en OpenAPI.
- Reutilizar el `ApiRestExceptionHandler` corporativo mediante un adaptador PDD.
- Aceptar y devolver `X-Correlation-Id`; generar uno si no se recibe.
- Incluir `traceId` de observabilidad sin exponer SQL ni datos sensibles.
- Registrar duración, operationId, resultado, usuario y correlationId.

## 8. Reglas de negocio que no deben quedar en el controller

- D y S son calculadas y de solo lectura.
- Solo E/C/A se crean manualmente.
- E/C son obligatorias; A es opcional.
- DRAFT puede editarse; ACTIVE no se reescribe como borrador.
- No reducir una línea por debajo de lo preparado más lo cancelado.
- Cancelar no elimina historia ni cantidad ya preparada.
- Activar requiere supervisor, motivo y par artículo–sucursal dentro del scope.
- CLOSED/CANCELLED/EXPIRED no se reabren en v1.
- La ausencia de stock no cancela una necesidad dirigida.

Estas reglas deben residir en servicios de dominio/aplicación y cubrirse con
pruebas unitarias independientes de HTTP y JPA.

## 9. Migraciones y propiedad del esquema

Los DDL normativos actuales son:

- `PDD - DDL Operativo Core connexa_platform_ms v2.2.sql`;
- `PDD - DDL Operativo DECAS connexa_platform_ms v2.2.sql`;
- migraciones complementarias v2.4–v2.6.

Antes de incorporar esos DDL a Flyway se debe definir un baseline para los
ambientes que ya tienen las tablas. No copiar un `CREATE TABLE` sin estrategia
de adopción: produciría diferencias entre Test y ambientes nuevos.

La librería Java será propietaria de las migraciones del esquema. Python puede
insertar/publicar según el contrato, pero no debe administrar migraciones del
runtime Java.

## 10. Contrato entre Python y Java

| Python/Prefect produce | Java API consume |
| --- | --- |
| PDVB vigente | explicación y linaje |
| posiciones sucursal/CD | detalle de stock |
| snapshots D/S | explicación de necesidades |
| backlog vigente | resumen, lista y detalle |
| corridas y snapshots fuente | estado técnico |
| datos logísticos | bultos, pallets, peso y volumen |

Java produce E/C/A y su auditoría. El orquestador Python las incorpora en la
siguiente publicación de backlog. No existe llamada síncrona Java→Prefect en
v1; la UI informa que la necesidad participará en la próxima foto.

## 11. Pruebas mínimas de aceptación backend

1. Contract test contra las 15 operaciones OpenAPI.
2. Integración PostgreSQL para filtros, cursor y snapshot cambiado.
3. Test de roles por operación.
4. Alta idempotente concurrente sin duplicados.
5. Conflicto de versión con dos escritores.
6. Rollback total si falla versión o auditoría.
7. Reglas de transición DRAFT/ACTIVE/CLOSED/CANCELLED.
8. Validación de scope vigente.
9. Totales del resumen iguales a la foto de base.
10. p95 menor a 3 segundos con volumen piloto y página de 50.
11. SpringDoc publicado y validado contra el archivo OpenAPI fuente.
12. La aplicación Java no requiere paquetes Python ni acceso a `diarco_data`.

## 12. Definition of Done de la entrega Java

- modelos/repositorios PDD publicados desde `PDD_BACK`;
- migraciones Flyway con baseline aprobado;
- microservicio consume la librería y expone `/connexa/api/v1/pdd`;
- JWT, roles, errores, correlación, idempotencia y ETag operativos;
- pruebas unitarias, integración y contrato en CI;
- Swagger/SpringDoc disponible;
- rol PostgreSQL de mínimo privilegio aplicado;
- frontend integrado sin acceso directo a PostgreSQL;
- sin servicio `pdd-api` Python en producción.
