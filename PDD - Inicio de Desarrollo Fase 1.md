# Inicio de Desarrollo — Fase 1 en 40 días

Versión: **1.0**
Fecha: **2026-07-28**
Estado: **Backlog inicial para kickoff**
Referencia: SRS v2.1

---

## 1. Objetivo del equipo

Demostrar en producción o entorno acordado un ciclo completo:

```text
datos diarios
-> cálculo D/S e IRQ
-> alta E/C/A
-> backlog DECAS
-> consulta/importación Valkimia
-> preparación parcial
-> saldo y nueva corrida
```

Todo trabajo de asignación, reservas, transferencias, vehículos, viajes, rutas, cubicaje u optimización se etiqueta `FASE-2` y no ingresa al compromiso.

## 2. Equipo mínimo sugerido

- Product Owner/Responsable funcional con disponibilidad diaria;
- líder técnico;
- 2–3 desarrolladores backend/datos;
- 1–2 desarrolladores frontend;
- QA con automatización;
- referente de integración Valkimia;
- referente de datos/operación.

Una persona puede cubrir más de un rol, pero las responsabilidades deben quedar asignadas en el kickoff.

## 3. Tablero inicial

### Épica E0 — Fundaciones y contrato

| ID | Historia | Prioridad | Dependencia | Evidencia |
| --- | --- | --- | --- | --- |
| DEV-001 | Crear ADR de arquitectura y límites | P0 | ninguna | ADR aprobado |
| DEV-002 | Obtener fixtures de todas las fuentes | P0 | responsables de datos | lote controlado |
| DEV-003 | Ratificar fórmulas/redondeos | P0 | PO | ejemplos firmados |
| DEV-004 | Cerrar diccionario y unidades | P0 | Datos/PO | contrato de datos |
| DEV-005 | Probar conectividad Valkimia | P0 | VKM/IT | evidencia técnica |
| DEV-006 | Validar ID Connexa e idempotencia | P0 | DEV-005 | prueba repetida |
| DEV-007 | Definir delta/acumulado y estados | P0 | DEV-005 | mapping aprobado |
| DEV-008 | Preparar CI/CD, observabilidad y ambientes | P0 | Infra | pipeline verde |

### Épica E1 — Foto y cálculo

| ID | Historia | Prioridad | Referencia |
| --- | --- | --- | --- |
| DEV-101 | Ingestar lotes con control de frescura | P0 | RF-001–003 |
| DEV-102 | Persistir corrida y snapshots | P0 | RF-010 |
| DEV-103 | Calcular Stock Neto Sucursal | P0 | RF-011 |
| DEV-104 | Calcular umbrales/cobertura | P0 | RF-012 |
| DEV-105 | Calcular D y S | P0 | RF-013–014 |
| DEV-106 | Calcular IRQ/prioridad | P0 | RF-015 |
| DEV-107 | Exponer detalle explicable | P0 | RF-016 |
| DEV-108 | Resolver bordes y rechazados | P0 | RF-017 |

Demo E1: cargar fixture, ejecutar corrida y explicar cinco líneas, incluyendo `PDVB=0`, stock negativo y parámetro faltante.

### Épica E2 — Necesidades dirigidas

| ID | Historia | Prioridad | Referencia |
| --- | --- | --- | --- |
| DEV-201 | Alta/edición E | P0 | RF-020 |
| DEV-202 | Alta/edición C | P0 | RF-021 |
| DEV-203 | Alta/edición A | P0 | RF-022 |
| DEV-204 | Identidad, versiones y saldo | P0 | RF-023–024 |
| DEV-205 | Advertencia de duplicado | P1 | RF-025 |
| DEV-206 | Cierre/cancelación auditada | P0 | RF-026 |

Demo E2: E/C/A sobreviven a dos corridas, cambian con versión y no se duplican.

### Épica E3 — Backlog y panel

| ID | Historia | Prioridad | Referencia |
| --- | --- | --- | --- |
| DEV-301 | Consolidar DECAS por grano acordado | P0 | RF-030 |
| DEV-302 | Clasificar obligatorio/opcional | P0 | RF-031 |
| DEV-303 | Ordenar prioridad determinística | P0 | RF-032 |
| DEV-304 | Recalcular sin duplicación | P0 | RF-033 |
| DEV-305 | Imputar preparado a fuentes | P0 | RF-034 |
| DEV-306 | Conservar remanente | P0 | RF-035 |
| DEV-307 | Incorporar Base 2 | P0 | RF-036 |
| DEV-308 | Convertir unidades logísticas | P1 | RF-037 |
| DEV-309 | Construir panel y detalle | P0 | RF-051 |

Demo E3: una línea D+E+A muestra composición, prioridad, Base 2, unidades y saldo trazable.

### Épica E4 — Valkimia

| ID | Historia | Prioridad | Referencia |
| --- | --- | --- | --- |
| DEV-401 | API/puerto de consulta paginada | P0 | RF-040–041 |
| DEV-402 | Confirmación idempotente de importación | P0 | RF-042–043 |
| DEV-403 | Inbox de eventos de ejecución | P0 | RF-044 |
| DEV-404 | Preparación parcial | P0 | RF-045 |
| DEV-405 | Mapping de estados | P0 | RF-046 |
| DEV-406 | Adaptador físico certificado | P0 | IF-02–04 |
| DEV-407 | Contingencia controlada | P1 | RF-047 |

Demo E4: Valkimia consulta, importa 80 de 100, reintenta sin duplicar, prepara 50 y Connexa conserva saldo 50.

### Épica E5 — Operación y salida

| ID | Historia | Prioridad | Referencia |
| --- | --- | --- | --- |
| DEV-501 | Cierre y nueva corrida | P0 | RF-050 |
| DEV-502 | Alertas mínimas | P0 | RF-052 |
| DEV-503 | Auditoría punta a punta | P0 | RF-053 |
| DEV-504 | Parámetros versionados | P0 | RF-054 |
| DEV-505 | Permisos | P0 | RF-055 |
| DEV-506 | Monitor técnico | P0 | RNF-06 |
| DEV-507 | Rendimiento/recuperación | P0 | RNF-03/07 |
| DEV-508 | UAT y capacitación | P0 | aceptación SRS |

## 4. Secuencia de iteraciones

| Iteración | Días | Objetivo |
| --- | ---: | --- |
| I0 | 1–5 | E0 y esqueletos verticales |
| I1 | 6–14 | E1 demostrable |
| I2 | 10–18 | E2 y UI base |
| I3 | 15–24 | E3 |
| I4 | 20–30 | E4 |
| I5 | 31–35 | E5 y endurecimiento |
| UAT | 36–38 | escenarios completos |
| Salida | 39–40 | despliegue y estabilización |

Los solapamientos requieren ramas/feature flags y contratos acordados; no deben producir integraciones tardías.

## 5. Primeras 48 horas

1. asignar responsables y calendario;
2. revisar alcance/exclusiones en 30 minutos;
3. cargar decisiones D1–D5 en tablero;
4. confirmar ambientes y accesos;
5. conseguir dos fixtures completos y un caso por DECAS;
6. crear repositorio/módulos y pipeline;
7. definir esquemas de entrada y contrato lógico Valkimia;
8. escribir primero las pruebas de fórmula e idempotencia;
9. programar demos de D5, D14, D24, D30, D35 y D38;
10. bloquear etiqueta `FASE-2` fuera del sprint.

## 6. Gates

### Gate D5 — Viabilidad

- fuentes y fixtures disponibles;
- fórmula y unidades ratificadas;
- conectividad Valkimia;
- ID/idempotencia posibles;
- volumen y ventana conocidos;
- arquitectura y riesgos aprobados.

Si falla Valkimia, se activa contingencia controlada sin ampliar funcionalidad.

### Gate D14 — Cálculo

- corrida reproducible;
- bordes probados;
- explicación visible;
- rendimiento preliminar.

### Gate D30 — Integración

- consulta/importación y parcialidad certificadas;
- tres reintentos sin duplicación;
- mapping real;
- reconciliación observable.

### Gate D38 — Go/No-Go

- UAT completa;
- tres días simulados;
- seguridad y permisos;
- monitor y alertas;
- runbook y rollback;
- cero bloqueantes;
- exclusiones verificadas.

## 7. Escenarios UAT obligatorios

1. D con stock suficiente: cantidad cero.
2. D con IRQ 100.
3. S opcional separada de D.
4. E vencida priorizada.
5. C con vigencia.
6. A opcional.
7. mezcla DECAS consolidada.
8. importación parcial.
9. preparación parcial.
10. importado sin preparación.
11. evento duplicado.
12. versión vencida.
13. estado externo desconocido.
14. fuente diaria faltante.
15. nueva corrida sin duplicación.

## 8. Definición de listo

Una historia entra al desarrollo si tiene:

- actor y valor;
- referencia RF;
- datos de ejemplo;
- criterios Given/When/Then;
- permisos;
- observabilidad;
- tratamiento de error;
- confirmación de que no incorpora Fase 2.

## 9. Definición de terminado

- código revisado;
- pruebas automatizadas;
- migración/versionado de datos;
- contrato y documentación actualizados;
- métricas/logs;
- seguridad aplicada;
- demo con fixture;
- aceptación del PO;
- sin deuda crítica ni dependencia oculta.

