# Paquete backend: entidades de políticas de stock

Entrega: 2026-09-11. PostgreSQL 14+. Alcance: **migraciones de entidades para integrar en el Flyway del backend**. No incluye frontend, publicación de políticas ni cambio de fuente de PDD.

## Archivos

| Archivo | Función |
|---|---|
| `migrations/V2026091101__stock_policy_entities.sql` | Crea las cuatro entidades o conserva el borrador manual de TEST |
| `migrations/V2026091102__stock_policy_optional_category.sql` | Categoría opcional, unicidad de reglas generales e integridad entre versión e importación |
| `verification/preflight.sql` | Inspección de maestros y estructura previa |
| `verification/postflight.sql` | Verificación posterior, conteos y jerarquía |
| `verification/validate_migrations.py` | Prueba transaccional contra TEST con rollback obligatorio |
| `verification/results.json` | Resultado de validación de esta entrega |
| `CONTRATO_ENTIDADES.md` | Campos, semántica y obligaciones del servicio backend |
| `ESPECIFICACION_PANTALLAS.md` | Pantallas de mantenimiento, campos, validaciones, permisos, flujos y criterios QA |
| `openapi-stock-policy.yaml` | Contrato API propuesto: 21 operaciones, schemas, ETag e idempotencia |
| `DISENO_PUBLICACION.md` | Algoritmo transaccional, auditoría, validación, calendario y responsabilidades backend |
| `migrations/V2026091103__stock_policy_publication_support.sql` | Revisión, dominio, validaciones/incidencias, auditoría y registro idempotente |

## Integración con Flyway

1. Asignar a los tres archivos las siguientes versiones disponibles en el historial Flyway que administra `supply_planning`, manteniendo su orden. Los números de esta entrega son propuestos; no se inspeccionó ni modificó el historial del backend. No cambiar nombres/contenido después de aplicarlos.
2. Copiar únicamente los SQL de `migrations/` a la ubicación de migraciones configurada por el equipo. Usar migración transaccional para PostgreSQL; los archivos no contienen BEGIN/COMMIT ni operaciones concurrentes.
3. Ejecutar `preflight.sql`. Deben existir `supply_planning` y los maestros `spl_site`, `spl_supply_cluster`, `spl_category`, con PK `id uuid`. Para un esquema completamente vacío se requieren primero las migraciones de esos maestros.
4. En TEST ya existen las cuatro tablas del borrador. Comparar su estructura con la primera migración: `IF NOT EXISTS` conserva datos pero no reconcilia estructuras arbitrarias. Si hay drift distinto del borrador conocido, detener y preparar la reconciliación correspondiente.
5. Ejecutar los comandos habituales `info`, `validate` y `migrate` del pipeline del equipo con su configuración. No se suministran credenciales ni se prescribe `baseline`/`repair`: la existencia de tablas manuales no autoriza alterar el historial.
6. Ejecutar `postflight.sql`. En el TEST relevado se esperan 605 reglas, 627 filas de importación (605 MAPPED y 22 EXCLUDED_CLOSED), versión DRAFT. En una instalación nueva estas tablas estarán vacías.

No se toca `spl_supply_cluster_category`: el usuario confirmó que contiene datos dummy sin consumidor frontend. La nueva entidad se llama `spl_stock_policy_rule` porque también admite reglas por local. No migrar los 141 registros dummy. El retiro físico de la tabla anterior queda fuera del paquete para no romper dependencias no revisadas.

La primera migración no inserta las 605 reglas ni los códigos de clasificación: conserva lo existente en TEST. Para otro entorno se requiere una carga de datos separada con IDs y maestros propios. No copiar UUID de TEST. El antecedente de carga está en `PDD/documentacion/parametros_stock/06_implementacion_borrador_test.md`.

## Validación realizada

Los tres SQL se ejecutaron exitosamente mediante psycopg2 contra PostgreSQL de TEST:

- Instalación nueva en un esquema efímero con maestros mínimos UUID.
- Incorporación sobre las entidades del borrador existente, conservando el conteo de reglas.
- Inserción de regla general sin familia/rubro.
- Rechazo de una segunda regla general duplicada para la misma versión/local/clasificación.
- Confirmación de nulabilidad de familia.

Todas las transacciones terminaron con ROLLBACK. **El ajuste de categoría opcional no quedó aplicado en TEST**: se entrega para que lo ejecute Flyway. No se ejecutó el binario Flyway ni el pipeline Java del equipo; esa validación queda a cargo de su integración.

El validador incluido usa el helper local `PDD/documentacion/parametros_stock/relevar_base.py` y las variables `PGP_TEST_*` de `PDD/backend/.env`; requiere ejecutar desde este repositorio. Los SQL y el contrato son independientes de Python.

Actualización del entregable API: la migración 03 también fue revertida tras verificar ambos caminos. Se verificaron YAML, referencias internas, parámetros de rutas, IDs únicos y formato decimal con `verification/validate_openapi.py`. No se ejecutó un validador integral OpenAPI ni un generador Java; el equipo debe incorporarlos al pipeline. Tampoco se implementó ni ejecutó el servicio descrito. `DISENO_PUBLICACION.md` concreta las responsabilidades antes señaladas como pendientes en los contratos iniciales; no cambia el alcance a una aplicación terminada.

## Recuperación

Si falla una migración, conservar ejecución transaccional y revisar la causa (drift, duplicados, FK o permisos); no eliminar filas para forzar su aplicación. Si ya se confirmó una migración, corregir mediante una nueva versión hacia adelante. No se incluye rollback destructivo: volver a exigir familia NOT NULL puede perder compatibilidad con reglas generales creadas después.
