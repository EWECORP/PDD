# PDD — Análisis cruzado de repositorios Java Stock Management

Versión: **1.0**  
Fecha: **2026-08-19**  
Estado: **Base técnica para implementación PDD en Java**

## 1. Repositorios analizados

| Repositorio canónico | Artefacto Maven | Responsabilidad |
| --- | --- | --- |
| `connexa-platform-stock-management` | `connexa-platform-stock-management:1.0.0` | Aplicación Spring Boot ejecutable, API, servicios de aplicación, seguridad y configuración runtime |
| `connexa-platform-lib-model-stockmanagement` | `connexa-platform-lib-model-stock-management:1.0.0` | Dominio, contratos de repositorio, entidades JPA, adaptadores de persistencia y migraciones Flyway |

Los nombres anteriores de carpetas locales no forman parte de la arquitectura ni
deben utilizarse en documentación, código, CI o tickets.

## 2. Conclusión arquitectónica

Los repositorios son complementarios y se integran dentro del mismo proceso
Java. No son dos microservicios comunicándose por HTTP:

```text
HTTP/JWT
   │
   ▼
connexa-platform-stock-management
Controller -> UseCases -> Application Service
                         │
                         ▼ dependencia Maven
connexa-platform-lib-model-stockmanagement
Domain Repository -> RepositoryImpl -> Spring Data JPA -> PostgreSQL
```

El `pom.xml` del microservicio declara la librería de modelo en versión `1.0.0`.
La configuración de la aplicación escanea explícitamente:

- repositorios bajo
  `com.zeetrex.lib.model.stockmanagement.infrastructure.persistence.repository`;
- entidades bajo
  `com.zeetrex.lib.model.stockmanagement.infrastructure.persistence.entity`;
- componentes de `com.zeetrex.connexa.platform` y `com.zeetrex.lib`.

Esto permite agregar PDD a la librería sin crear una segunda aplicación ni una
conexión HTTP interna.

## 3. Patrón existente verificado

El flujo de stock actual demuestra el patrón que debe conservar PDD:

| Capa | Ejemplo existente | Repositorio |
| --- | --- | --- |
| Entrada HTTP | `StockController` | `connexa-platform-stock-management` |
| Puerto de caso de uso | `StockUseCases` | `connexa-platform-stock-management` |
| Servicio de aplicación | `StockService` | `connexa-platform-stock-management` |
| Puerto de persistencia | `StockRepository` | `connexa-platform-lib-model-stockmanagement` |
| Adaptador | `StockRepositoryImpl` | `connexa-platform-lib-model-stockmanagement` |
| Spring Data | `StockRepositoryJpa` | `connexa-platform-lib-model-stockmanagement` |
| Conversión | `StockEntityMapper` | `connexa-platform-lib-model-stockmanagement` |
| Persistencia | `StockEntity` | `connexa-platform-lib-model-stockmanagement` |

`StockController` delega en `StockUseCases`; `StockService` implementa ese
puerto y recibe repositorios de la librería por inyección. Los errores se
adaptan mediante `StockManagementBoundary`, cuya implementación
`ApiStockManagementBoundary` extiende el boundary corporativo.

## 4. Distribución obligatoria del desarrollo PDD

### 4.1 `connexa-platform-lib-model-stockmanagement`

Debe contener:

- modelos de dominio PDD;
- entidades JPA de `stock_management.pdd_*`;
- proyecciones optimizadas para backlog, resumen, explicación y catálogos;
- puertos de repositorio;
- interfaces Spring Data JPA;
- implementaciones de repositorio y mappers;
- migraciones Flyway versionadas;
- pruebas de persistencia y mapeo.

Estructura objetivo:

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

No debe contener controllers, DTO HTTP, JWT ni configuración web.

### 4.2 `connexa-platform-stock-management`

Debe contener:

- controllers del contrato OpenAPI PDD;
- DTO de request/response;
- interfaces de casos de uso;
- servicios de consulta y comandos E/C/A;
- validaciones funcionales, transacciones e idempotencia;
- autorización por roles PDD;
- adaptación uniforme de errores y correlación;
- pruebas unitarias, HTTP, seguridad y contrato.

Estructura objetivo:

```text
com.zeetrex.connexa.platform.stock.management
├── controller/pdd
├── application/dto/pdd
├── application/boundary/pdd
├── application/service/pdd
├── domain/service/pdd
└── application/config
```

## 5. Flujo objetivo de una consulta PDD

```text
PddBacklogController
  -> PddBacklogUseCases
    -> PddBacklogQueryService
      -> PddBacklogQueryRepository
        -> PddBacklogQueryRepositoryImpl
          -> PddBacklogRepositoryJpa/proyección
            -> stock_management.pdd_current_backlog_line
```

Para comandos E/C/A, el servicio de aplicación debe abrir una única
transacción que persista agregado, versión, idempotencia y auditoría antes del
commit.

## 6. Dependencias y orden de construcción

La cadena Maven local es:

```text
connexa-platform-lib-persistence-core
  -> connexa-platform-lib-model-stockmanagement
       -> connexa-platform-stock-management

connexa-platform-lib-application-core
  -------------------------------> connexa-platform-stock-management
```

Por lo tanto, el orden reproducible es:

1. instalar `connexa-platform-lib-persistence-core`;
2. instalar `connexa-platform-lib-model-stockmanagement`;
3. instalar `connexa-platform-lib-application-core`;
4. compilar y probar `connexa-platform-stock-management`.

La solución definitiva de CI debe consumir artefactos corporativos versionados;
la instalación en el repositorio Maven local es solamente la estrategia de
desarrollo inicial.

## 7. Compatibilidad constatada

| Aspecto | Resultado |
| --- | --- |
| Java/Spring Boot | Ambos declaran Java 21 y Spring Boot 3.4.3 |
| Persistencia | La aplicación ya escanea entidades y repositorios de la librería |
| Esquema | Hibernate y Flyway usan `stock_management` |
| Migraciones | La librería ya empaqueta `db/migration`; Flyway de la aplicación carga recursos del classpath |
| Seguridad | OAuth2 Resource Server/JWT ya está activo |
| Authorities | El JWT toma authorities del claim `authorities` sin prefijo |
| Frontera HTTP | Los controllers existentes usan `/v1/...` y delegan en interfaces UseCases |
| PDD existente | No se encontraron clases PDD/PDVB/DECAS/backlog en ninguno de los repositorios |
| Pruebas | La librería tiene pruebas de repositorio; la aplicación no tiene pruebas Java actualmente |

## 8. Brechas que deben resolverse al implementar PDD

1. **Autorización:** la seguridad actual sólo exige autenticación global. Se
   necesita seguridad de método y controles `PDD_VIEWER`, `PDD_BUYER`,
   `PDD_SUPERVISOR`, `PDD_AUDITOR` y `PDD_TECHNICAL`.
2. **Contrato:** implementar las 15 operaciones de
   `backend/contracts/pdd-frontend-openapi-v1.yaml` sin exponer entidades JPA.
3. **Pruebas del microservicio:** crear la base de tests antes o junto con el
   primer vertical PDD; hoy no existen tests Java en este repositorio.
4. **Migraciones:** asignar versiones Flyway sin colisionar con las migraciones
   ya empaquetadas y definir baseline para bases con tablas PDD preexistentes.
5. **Tipos numéricos:** aunque entidades históricas usan `Double`, PDD debe usar
   `BigDecimal` para cantidades, peso, volumen e importes.
6. **Secretos:** externalizar completamente el secreto JWT; no mantener un valor
   utilizable dentro de `application.yml`.
7. **Context path/gateway:** confirmar una sola composición entre la ruta interna
   Java y la base pública `/connexa/api/v1/pdd`.
8. **Consultas:** backlog y dashboard requieren proyecciones/consultas nativas;
   no conviene materializarlos como grafos JPA.
9. **Concurrencia:** implementar `ETag`/`If-Match`, versión optimista e
   idempotencia para E/C/A.
10. **Observabilidad:** incorporar correlation ID, problem details, métricas y
    auditoría sin registrar datos sensibles.

## 9. Primer corte vertical recomendado

Implementar primero un corte de sólo lectura:

1. entidades/proyecciones mínimas para corrida actual y backlog;
2. repositorio de resumen y backlog;
3. `PddStatusUseCases` y `PddBacklogUseCases`;
4. servicios de consulta;
5. `GET /status`, `GET /dashboard/summary`, `GET /backlog` y
   `GET /backlog/{uuid}`;
6. seguridad `PDD_VIEWER`;
7. tests de contrato e integración PostgreSQL.

Este corte habilita al frontend con datos reales sin bloquearse por la mayor
complejidad transaccional de E/C/A. El segundo corte incorpora explicación y
catálogos; el tercero, comandos E/C/A completos.

## 10. Resultado de la indexación

Los dos repositorios fueron reindexados desde sus nombres canónicos:

| Repositorio | Nodos | Relaciones |
| --- | ---: | ---: |
| `connexa-platform-stock-management` | 2.589 | 9.131 |
| `connexa-platform-lib-model-stockmanagement` | 2.812 | 10.067 |

El análisis cruzado automático no encontró enlaces HTTP, mensajería, gRPC o
GraphQL entre ambos. El resultado es esperado y confirma que la integración
relevante es Maven + Spring DI + JPA dentro del mismo runtime.

## 11. Reimportación en IntelliJ

1. cerrar los módulos cargados desde nombres locales anteriores;
2. abrir el `pom.xml` de `connexa-platform-lib-model-stockmanagement` como
   proyecto Maven;
3. abrir el `pom.xml` de `connexa-platform-stock-management` como proyecto
   Maven;
4. seleccionar JDK 21 como Project SDK y Maven runner;
5. recargar todos los proyectos Maven después de instalar las dependencias
   corporativas;
6. verificar que no queden módulos duplicados apuntando a rutas antiguas.

