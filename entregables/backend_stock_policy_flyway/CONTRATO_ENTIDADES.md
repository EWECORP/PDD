# Contrato de entidades para backend

Actualización: `V2026091103__stock_policy_publication_support.sql` agrega revisión y soporte de publicación/auditoría. Ver `DISENO_PUBLICACION.md` y `openapi-stock-policy.yaml` para el contrato técnico que completa este documento. Las obligaciones del servicio siguen requiriendo implementación; las tablas por sí solas no garantizan inmutabilidad ni publicación segura.

## Modelo

`spl_stock_policy_version` 1:N `spl_stock_policy_rule`.
Cada regla referencia un local **o** un grupo, una clasificación de compra y opcionalmente categorías.
`spl_stock_policy_import_row` conserva los códigos del origen y, cuando está mapeada, referencia una regla de su misma versión.

| Entidad | Campos principales | Restricciones |
|---|---|---|
| `spl_stock_policy_version` | UUID id; status; valid_from/to; source_system; source_checksum; created_at/by; change_reason | PK, checksum único, estados DRAFT/PUBLISHED/RETIRED, vigencia fin > inicio; publicada/retirada requiere inicio |
| `spl_stock_purchase_classification` | integer code; text name | PK por código |
| `spl_stock_policy_rule` | UUID id/version/site/cluster/family/category; integer purchase_classification_code; numeric(10,4) target_stock_days/overstock_days; integer priority; códigos legacy | PK/FK; local XOR grupo; días no negativos; rubro requiere familia; clave única por versión/ámbito/filtros, incluso con categorías NULL |
| `spl_stock_policy_import_row` | versión, códigos legacy de local/familia/rubro/compra, ambos días, rule_id, mapping_status/reason | PK de origen; MAPPED exige regla; PENDING/EXCLUDED_CLOSED sin regla; FK compuesta impide cruzar versiones |

UUID los genera el backend: no se requiere extensión de PostgreSQL. Días se representan con `BigDecimal` o equivalente, no flotantes. Las fechas son de negocio, intervalo [desde,hasta); `created_at` es `timestamptz`.

## Categorías opcionales

| family_category_id | category_id | Significado |
|---|---|---|
| NULL | NULL | Todas las categorías |
| Familia | NULL | Todos los rubros de esa familia |
| Familia | Rubro | Sólo ese rubro |
| NULL | Rubro | Inválido; rechazado por CHECK |

El servicio debe comprobar que `spl_category.parent_id` del rubro corresponda a la familia. Las FKs por separado no validan esa jerarquía; se incluye diagnóstico en `postflight.sql`. Se reservó UUID cero para normalizar NULL en índices y se prohíbe como referencia de categoría.

Clasificación de compra sigue siendo **obligatoria**: el cambio aprobado de opcionalidad afecta a categoría, no a clasificación. No usar un código ficticio para «todas». La incorporación futura de ABC/rotación requiere otra migración y una fuente definida.

## Resolución que debe implementar el servicio

Para fecha y versión efectiva:

1. Buscar reglas coincidentes del local; si no hay, buscar reglas del grupo efectivo.
2. Dentro del ámbito, elegir rubro específico antes que familia y familia antes que general.
3. Obtener ambos días de la misma regla. La clasificación siempre debe coincidir.
4. Si hay empate, informar inconsistencia; si no hay regla, informar falta de cobertura. No usar cero ni legado silenciosamente.

`priority` se conserva por compatibilidad con el borrador y se mantiene en 0; no altera la precedencia anterior. Los índices impiden duplicados exactos, pero el servicio debe validar asignaciones de grupo y versiones para evitar ambigüedades más amplias. No se modificó `spl_supply_site` ni se agregó una política general sin local/grupo.

## Publicación y auditoría: responsabilidades explícitas

Este paquete implementa entidades, **no un servicio completo de políticas**. Antes de habilitar publicación, el backend debe implementar:

- Control de edición sólo en DRAFT, inmutabilidad de reglas publicadas y copia a nueva versión para cambios.
- Publicación atómica con exclusión mutua y validación de que no haya versiones efectivas solapadas en el ámbito de negocio. No basta con consultar y luego actualizar sin bloqueo.
- Validación de cobertura del scope y de importaciones PENDING; EXCLUDED_CLOSED se conserva como exclusión explícita.
- Auditoría de cambios y control de concurrencia. `created_by` no reemplaza el historial de ediciones.
- Regla para generar `source_checksum` en versiones manuales: no reutilizar el de una versión anterior, dado que es único. Para importación conservar el checksum del lote.
- Validación de fechas finitas y días finitos no negativos en la API; publicar un contrato de errores de validación.
- Definición del alcance empresa/tenant usando los maestros y controles actuales; este paquete no introduce aislamiento multiempresa nuevo.

No cambiar manualmente DRAFT a PUBLISHED para activar PDD: `daily_decas.py` todavía lee `src.base_stock_sucursal`. La integración posterior debe fijar versión, resolver parámetros y guardar versión/regla junto con los días de cada cálculo. El fallback al legado no está autorizado ni implementado por estas migraciones.

## Fuente y carga existente

El campo real del legado es `c_claisificacion_compra`, normalizado aquí a `purchase_classification_code`. `c_rubro=0` se normaliza a rubro NULL; los datos importados preservan familia. Los locales 83/84 fueron confirmados cerrados: las 22 filas quedan EXCLUDED_CLOSED.

La carga existente en TEST contiene 605 reglas para 55 locales, con ambos días iguales a la evidencia importada. Las diferencias de T055 respecto de `base_stock_sucursal` deben evaluarse por scope antes de activar el nuevo cálculo. Los datos dummy de grupos no representan valores definitivos.
