# Índice y Gobierno Documental — Planificación de Necesidades Connexa

Versión del paquete: **2.6**
Fecha de actualización: **2026-08-21**
Estado: **Base vigente — DECAS más planificación operativa de viajes**

---

## 1. Decisión rectora

La entrega inicial implementó **Planificación Diaria de Necesidades de
Distribución**. La decisión ADR-003 amplía el alcance: Connexa también
selecciona el backlog, forma y cubica viajes, reserva cantidades aprobadas y
publica a Valkimia solamente la carga operativa inmediata.

Valkimia deja de seleccionar oportunísticamente sobre el backlog completo. Es
el ejecutor logístico y validador final de stock; comunica aceptación,
preparación, despacho, cancelación y entrega. Connexa conserva decisión,
remanente y trazabilidad.

Continúan fuera la optimización matemática automática de rutas, la asignación
automática de vehículos, GPS y liquidación de transportistas.

## 2. Precedencia

Ante una contradicción:

1. decisión aprobada y fechada posterior;
2. `PDD - ADR-003 Planificacion de Viajes en Connexa.md`;
3. especificaciones de planificación/API publicadas el 2026-08-21;
4. `PDD - ALCANCE Fase 1.md`, para el alcance analítico original;
5. Especificación de Requerimiento de Software v2.0;
6. Circuito Operativo v2.0;
7. Modelo de Datos e Integración v2.0;
8. Diseño de Pantallas v2.0;
9. documentos de contexto y reuniones.

El signo normativo de NDD-D es resta de Stock Neto Sucursal. Su ratificación funcional forma parte de D1–D5.

## 3. Documentos normativos vigentes

| Documento | Propósito |
| --- | --- |
| `PDD - ALCANCE Fase 1.md` | Decisión funcional rectora, límites y entregable |
| `PDD - Especificación de Requerimiento de Software Connexa v2.0.md` | Requerimientos, aceptación, pruebas y arranque |
| `PDD - Circuito Operativo de Necesidades de Distribución Connexa v2.0.md` | Procedimiento diario y responsabilidades |
| `PDD - Modelo de Datos Conceptual Connexa v2.0.md` | Entidades, saldos y restricciones |
| `PDD - Diccionario de Datos e Identidades v1.0.md` | Contrato físico-funcional de tablas, claves y generación de IDs/UUIDs |
| `PDD - Integracion Valkimia por Adaptadores v2.2.md` | Publicación de viajes, polling legacy, idempotencia y conciliación |
| `PDD - Diseño de Pantallas Operativas Connexa v2.0.md` | MVP de pantallas y UX |
| `PDD - Vision Requerimiento y Plan Connexa v2.0.md` | Síntesis, arquitectura, plan y riesgos |
| `PDD - Guion Presentación Ejecutiva Connexa v2.0.md` | Comunicación ejecutiva alineada |
| `PDD - Inicio de Desarrollo Fase 1.md` | Épicas, historias, secuencia, gates y UAT para kickoff |
| `PDD - Especificación Frontend y Contrato API v1.1.md` | Contrato funcional consumido por frontend y backend Java |
| `PDD - Especificación Implementación API Java Stock Management v1.0.md` | Arquitectura, capas, persistencia y aceptación del backend Java |
| `backend/contracts/pdd-frontend-openapi-v1.yaml` | Fuente ejecutable OpenAPI v1.1 de las 15 operaciones PDD |
| `PDD - ADR-003 Planificacion de Viajes en Connexa.md` | Decisión de trasladar selección, cubicaje y viajes a Connexa |
| `PDD - Especificacion Funcional Planificacion de Viajes Connexa v1.0.md` | Pantalla, estados, reglas y aceptación de viajes |
| `PDD - Contrato API Planificacion y Ejecucion Valkimia v1.0.md` | Contrato Java, integración legacy y conciliación |
| `backend/contracts/pdd-planning-openapi-v1.yaml` | OpenAPI ejecutable de planificación y seguimiento Valkimia |
| `PDD - Migracion Operativa Planificacion Viajes v2.7.sql` | Entidades físicas aditivas para el nuevo alcance |
| `PDD - Despliegue y Prueba Planificacion Viajes v1.0.md` | Secuencia DESA→TEST, smoke test y gates |
| `PDD - Publicacion Operativa Diaria DESA v1.0.md` | Materialización diaria DESA sin recalcular features ni PDVB |
| `PDD - Solicitud de Correccion Contrato Estados Valkimia v1.0.md` | Corrección requerida al BACK para catálogo, eventos, mapping y transiciones Valkimia |
| `PDD - Migracion Correctiva Estados Valkimia v2.8.sql` | Catálogo canónico, FK de eventos, checks, índice y retiro de duplicaciones |
| `PDD - Validacion Correctiva Estados Valkimia v2.8.sql` | Control de catálogo, FK, columnas, índice e integridad final |
| `PDD - DDL Fuente Canonica Articulos Logistica diarco_data v1.0.sql` | Fuente SCD2 de embalaje, peso, volumen, palletización y manipulación para PDD |
| `PDD - Solicitud Ampliacion Item Logistics Snapshot v1.0.md` | Contrato solicitado al BACK para congelar peso, volumen, palletización, manipulación y calidad logística por corrida |
| `PDD - Migracion Ampliacion Item Logistics Snapshot v2.9.sql` | Migración Flyway aditiva y compatible para ampliar el snapshot logístico operacional |
| `PDD - Validacion Ampliacion Item Logistics Snapshot v2.9.sql` | Verificación posterior de columnas, checks, índices, cobertura y consistencia logística |
| `PDD - Solicitud Catalogo Tipos Vehiculo al BACK Java v1.0.md` | Contrato funcional, persistencia, API y aceptación del catálogo de capacidades de vehículos |
| `PDD - Migracion Catalogo Tipos Vehiculo v3.0.sql` | Migración Flyway aditiva del catálogo y su vínculo con el snapshot de viaje |
| `PDD - Validacion Catalogo Tipos Vehiculo v3.0.sql` | Control físico, integridad de capacidades y consistencia de viajes vinculados |
| `PDD - Grants Catalogo Tipos Vehiculo v1.0.sql` | Permisos del rol Java para consultar y administrar el catálogo sin borrado físico |
| `PDD - Seed DESA Tipos Vehiculo Simulados v1.0.sql` | Datos transitorios de desarrollo derivados de la imagen de Valkimia, identificados y restringidos a DESA |
| `PDD - Reunion Tecnica Valkimia Relevamiento e Interfaz v1.0.md` | Correo, agenda, relevamiento, preguntas, acuerdos y aceptación para la reunión con Valkimia |
| `PDD - Propuesta Interfaz SQL Server Valkimia v1.0.sql` | Borrador físico de tablas separadas para publicación, eventos y despachos Valkimia |

Los nombres físicos v2.0 se conservan para evitar romper referencias existentes;
la separación de responsabilidades API/ETL queda documentada en la revisión
**2.2**.

La API productiva pertenece al microservicio Java Stock Management. El backend
Python/Prefect se limita a ETL, cálculo y publicación; el mock HTTP local es un
artefacto de contrato y no un servicio desplegable.

## 4. Vocabulario obligatorio

| Término | Uso |
| --- | --- |
| Planificación de necesidades | Cálculo, prioridad, backlog y seguimiento |
| Planificación de viajes | Selección, reserva, cubicaje y aprobación realizada en Connexa |
| Ejecución logística | Validación final, preparación y despacho realizado en Valkimia |
| DECAS | D Demanda, E Especial, C Campaña, A Acopio, S Sobre-stock |
| Obligatorio | D/E/C visible hasta saldo cero; no obliga a Connexa a asignar stock |
| Opcional | A/S seleccionable según oportunidad |
| Importado | Viaje aprobado publicado por Connexa hacia Valkimia; no cumplido |
| Preparado | Cantidad efectiva informada por Valkimia |
| Stock Base 2 | Referencia informativa, no reserva |
| Backlog | Saldo vigente de necesidades |
| IRQ | Índice explicable de urgencia 0–100 |

No confundir planificación manual gobernada con optimización automática. La
primera está aprobada; la segunda continúa fuera de alcance.

Una reserva evita doble planificación, pero no equivale a cumplimiento ni a
stock físicamente preparado. El cumplimiento se imputa al despacho.

## 5. Control de cambios 2.1

- se incorporó el alcance acordado el 28/07/2026;
- se fijó un entregable útil en 40 días;
- se formalizó Stock Neto Sucursal;
- se formalizaron fórmulas D/S y reglas de borde;
- se adoptó DECAS y obligatoriedad D/E/C versus A/S;
- se definió IRQ inicial versionado;
- se cambió publicación Connexa por consulta/importación oportunista Valkimia;
- se separó importado de preparado;
- se eliminó transferencia intersucursal de Fase 1;
- se eliminaron gestión, capacidad, viajes, rutas y optimización;
- se redujo el modelo y las pantallas al MVP;
- se agregó orden de construcción, UAT y decisiones D1–D5.

## 6. Contexto no normativo

`Contexto/` y `Reuniones/` explican la evolución. No deben utilizarse como
contrato cuando contradigan ADR-003 o los documentos vigentes. Continúan fuera:

- motor automático de prorrateo/fair share;
- optimizador integral logístico;
- transferencias intersucursal;
- SND/API WEB como precondición;
- publicación sin aprobación humana ni idempotencia.

La selección, reserva, cubicaje manual y viajes quedaron expresamente
aprobados por ADR-003.

## 7. Control de cambios 2.3

- Connexa pasa a seleccionar el backlog y planificar viajes;
- Valkimia recibe solamente viajes aprobados para operación inmediata;
- se incorporan planes, viajes, paradas, líneas y atribuciones congeladas;
- se define publicación idempotente y polling de la interfaz legacy;
- se establece despacho como momento de cumplimiento;
- se mantiene fuera la optimización automática de rutas y vehículos.

## 8. Gobierno de cambios

Todo cambio se clasifica:

- **Aclaración:** no altera esfuerzo ni aceptación; se actualiza la especificación.
- **Corrección:** resuelve contradicción o defecto; requiere evidencia y regresión.
- **Cambio de alcance:** agrega actor, entidad, interfaz o capacidad; requiere decisión de producto y reemplazo equivalente.
- **Optimización futura:** rutas automáticas, vehículos automáticos, GPS y
  liquidación; requiere una decisión adicional.

El equipo mantiene:

- log de decisiones/ADR;
- matriz requerimiento–historia–prueba;
- contrato Valkimia versionado;
- evidencia UAT;
- lista explícita de exclusiones.

### Control de cambios 2.4

- se reconoce como válida la normalización relacional de estados Valkimia
  implementada por el equipo BACK en DESA;
- se documenta la divergencia detectada en `pdd_execution_event`;
- se exige una nueva migración Flyway correctiva sin modificar checksums
  históricos;
- se formalizan criterios de aceptación para catálogo, mapping, eventos y
  transiciones.

## 9. Criterio para comenzar planificación de viajes

El desarrollo puede iniciar con ADR-003, la migración v2.7, la especificación
funcional y el OpenAPI de planificación. Antes de implementar el adaptador
legacy deben obtenerse el DDL real de la tabla Valkimia, muestras de cada
estado, semántica de cantidades y timestamps confiables de actualización.

La falta de volumen permite comenzar con cubicaje por peso y pallets, pero debe
permanecer visible como limitación y no convertirse silenciosamente en cero.
