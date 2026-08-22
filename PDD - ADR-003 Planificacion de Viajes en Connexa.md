# ADR-003 — Planificación de viajes en Connexa y ejecución acotada en Valkimia

Fecha: **2026-08-21**  
Estado: **APROBADA**  
Decisor: **Equipo de proyecto PDD / DIARCO–CONNEXA**

## Contexto

La primera fase construyó estimación PDVB, necesidades DECAS y un backlog
operativo en `stock_management.pdd_current_backlog_line`. El alcance anterior
suponía que Valkimia consultaría o importaría necesidades de manera
oportunista.

Valkimia se encuentra en una versión antigua y no debe recibir ni administrar
un backlog voluminoso. El proyecto necesita que el planificador del Centro de
Distribución seleccione, priorice y cubique en Connexa los viajes que se
prepararán. Valkimia debe recibir solamente las líneas de viajes aprobados para
la operación inmediata, validar existencia de stock y ejecutar preparación y
despacho.

Mientras Valkimia no consuma APIs, la integración continuará mediante su tabla
legacy de interfaz: Connexa escribe registros con identificadores propios y un
adaptador consulta periódicamente los cambios de estado.

## Decisión

1. **Connexa es el sistema de decisión y trazabilidad** para backlog, planes,
   viajes, paradas, cubicaje, reservas e imputación DECAS.
2. **Valkimia es ejecutor logístico**. Puede aceptar parcial o rechazar por stock
   o regla, pero no decide qué backlog planificar ni elimina necesidades.
3. `pdd_current_backlog_line` sigue siendo una proyección de saldo; no es un
   viaje, orden ni interfaz externa.
4. Los borradores y viajes se persisten en entidades `pdd_dispatch_*` nuevas.
5. `pdd_valkimia_import` y `pdd_valkimia_import_line` se crean únicamente a
   partir de un viaje aprobado. Representan lo publicado, no el plan editable.
6. Una línea se identifica de extremo a extremo mediante UUID de plan, viaje,
   línea de viaje, importación, línea de importación y backlog de origen.
7. La selección firme se valida contra `snapshot_version` y `row_version`. Al
   aprobar se congela también la imputación E vencida, E, C, D, A y S.
8. Seleccionar o preparar no cumple la necesidad. El cumplimiento se imputa al
   **despacho**; un rechazo o cancelación libera el remanente al backlog.
9. La publicación usa outbox/idempotencia. El polling legacy crea eventos
   append-only deduplicados y mantiene un checkpoint durable.
10. El frontend usa exclusivamente el backend Java Stock Management. Python y
    Prefect continúan produciendo datos analíticos y no atienden comandos
    interactivos del planificador.

## Límites de la primera entrega de viajes

Incluido:

- selección manual y parcial del backlog;
- separación de obligatorio D/E/C y opcional A/S;
- planes, viajes y paradas;
- cubicaje por bultos, pallets y peso;
- volumen cuando exista el dato canónico;
- aprobación, reserva firme y publicación;
- escritura y polling de una interfaz legacy;
- aceptación parcial, preparación, despacho, cancelación y conciliación;
- auditoría e idempotencia.

No incluido inicialmente:

- optimización matemática automática de rutas;
- asignación automática de vehículos;
- telemetría o seguimiento GPS;
- liquidación de transportistas;
- edición directa de datos en las tablas por el frontend;
- considerar una selección como cumplimiento antes del despacho.

## Consecuencias

### Positivas

- Connexa conserva control y explicación de cada decisión.
- Valkimia recibe un volumen pequeño y operacionalmente inmediato.
- no se pierde saldo ante falta de stock o preparación parcial;
- puede medirse fill rate planificado, aceptado, preparado y despachado;
- se elimina la selección oportunista no gobernada.

### Trabajo adicional obligatorio

- migración operativa v2.7;
- endpoints Java de planes y viajes;
- pantalla Connexa de planificación/cubicaje;
- adaptador de salida a la tabla legacy Valkimia;
- polling y catálogo de estados externos;
- conciliación de importaciones activas con el backlog;
- reemplazo del bloqueo temporal del publicador ante importaciones activas;
- fuente canónica de volumen/dimensiones para cubicaje completo.

## Reglas de seguridad e integridad

- el frontend nunca escribe PostgreSQL ni la interfaz Valkimia;
- solamente un plan `APPROVED` puede publicarse;
- el mismo viaje se publica una sola vez mediante clave idempotente;
- artículo y sucursal son datos de control, no claves de correlación;
- un estado externo desconocido queda en cuarentena `UNKNOWN`;
- los eventos no se eliminan ni se aplican dos veces;
- ninguna corrección puede reducir cantidades ya despachadas sin un evento
  explícito `CORRECTED` y auditoría.

## Documentos relacionados

- `PDD - Migracion Operativa Planificacion Viajes v2.7.sql`;
- `PDD - Especificacion Funcional Planificacion de Viajes Connexa v1.0.md`;
- `PDD - Contrato API Planificacion y Ejecucion Valkimia v1.0.md`;
- `backend/contracts/pdd-planning-openapi-v1.yaml`.
