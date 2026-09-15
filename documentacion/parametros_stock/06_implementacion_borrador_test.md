# Primera implementación de políticas en TEST

> Documento histórico. Para el estado actual y la decisión de reutilizar `inventory`, consultar la [auditoría de TEST del 14/09/2026](07_auditoria_inventory_test_20260914.md). Los conteos y recomendaciones siguientes corresponden a su fecha original.

Fecha: 2026-09-11. Estado: migración y carga inicial **aplicadas en TEST como DRAFT**. No se activó un cambio de fuente en PDD.

## Decisiones confirmadas por el usuario

- `spl_supply_cluster_category` contiene datos dummy, sin uso del frontend. Los conflictos del informe 05 no requieren conciliación como datos definitivos.
- Fuente inicial: `diarco_data.src.t055_articulos_param_stock`.
- `c_rubro=0` significa todos los rubros de la familia; en la regla canónica se representa con `category_id=NULL`.
- Los locales 83 y 84 están cerrados. Se conserva su evidencia de importación y se excluyen sus reglas operativas.
- Los grupos actuales son una prueba. Zona y formato M/P/B deben revisarse antes de generar políticas de grupo.

## Cambios aplicados

Se crearon en `supply_planning`:

| Tabla | Función | Carga |
|---|---|---:|
| `spl_stock_policy_version` | Cabecera de versión, origen, checksum y estado | 1 borrador |
| `spl_stock_purchase_classification` | Códigos de compra normalizados usados en T055 | 4 códigos: 1, 2, 3, 6 |
| `spl_stock_policy_rule` | Local o grupo, familia, rubro opcional, clasificación, ambos días | 605 reglas |
| `spl_stock_policy_import_row` | Evidencia de importación y exclusiones | 627 filas |

Versión: `46271d2f-0d1e-4bcc-ae68-6c6f964cb447`.

Las reglas cubren los 55 locales mapeados de T055. Las 22 filas de los locales cerrados quedaron `EXCLUDED_CLOSED`, sin regla operativa. Se verificó antes del COMMIT que todas las reglas coincidan con su evidencia en claves y ambos días; diferencias: 0.

La tabla dummy permanece físicamente intacta como antecedente; el nuevo nombre refleja el ámbito ampliado local/grupo. No hay consumidores migrados todavía. Las FKs utilizan maestros de `supply_planning`; la jerarquía familia/rubro se comprobó durante la preparación. No se creó una pantalla de mantenimiento.

## Particularidades reales de T055

627 filas, 57 locales, sin claves duplicadas. Familias 2, 7 y 8; rubros 0 y 2528. La columna real se llama `c_claisificacion_compra` (errata del origen), no `c_clasificacion_compra`. Los scripts CDC anteriores del repositorio mencionan el segundo nombre y deberán revisarse antes de utilizarlos sobre esta estructura.

Todos los días de sobrestock son 0. Los días objetivo varían entre 15 y 65. Se preservaron sin completar ni inferir valores. Los códigos de familia se mapearon a 2=Frescos, 7=Limpieza, 8=Perfumería; el rubro 2528 a `2-2528`. No se reutilizó la agrupación dummy NON FOOD.

## Comparación con el stock actual

Consulta agregada sobre la última fecha disponible en `src.base_stock_sucursal`: **2026-08-27**. Universo completo de stock, no scope operativo PDD.

| Métrica | Pares artículo/local |
|---|---:|
| Total | 1.278.480 |
| Con regla T055 aplicable | 74.373 |
| Sin regla T055 aplicable | 1.204.107 |
| Cubiertos con días iguales | 16.598 |
| Cubiertos con días diferentes | 57.775 |
| Sin artículo / clasificación ambigua por artículo | 0 / 0 |

Se utilizó `src.t050_articulos` para familia/rubro/clasificación y la última extracción por artículo/local en la fecha. Rubro específico precede al comodín de familia. Esta comparación consulta T055 completa, incluyendo locales cerrados si tienen stock; no constituye una simulación de D/S ni certifica cobertura de las 605 reglas dentro del scope PDD.

## Alcance del DDL actual y trabajo previo a publicación

El DDL establece FKs, días no negativos, ámbito excluyente local/grupo, claves únicas con rubro NULL compatible con PostgreSQL 14 y conservación de exclusiones. Es una primera estructura de borrador. **Todavía no implementa el servicio de publicación**, inmutabilidad de reglas publicadas, auditoría de ediciones, control de vigencias superpuestas, ni resolución conectada a `daily_decas.py`. No se debe cambiar manualmente el estado a PUBLISHED.

Antes de activar:

1. Determinar cobertura y diferencias dentro del scope PDD elegido, con la misma fecha/PDVB/logística.
2. Decidir el tratamiento de pares sin T055: nuevas reglas de CONNEXA o fallback transitorio explícito al stock legado. No se puede inferir que correspondan a días cero.
3. Revisar diferencias de días con el negocio y simular el impacto en D y S.
4. Completar publicación, auditoría y resolución versionada; después integrar el lector de PDD.

## Artefactos

- `PDD/backend/contracts/sql/stock_policy_v1.sql`: DDL aplicado.
- `carga_inicial_test.sql`: SQL exacto de creación y carga; de una sola ejecución, no reejecutar sobre objetos existentes.
- `preparar_carga_test.py`: preparación con validación de claves, días, locales y jerarquía.
- `aplicar_borrador_test.py`: aplicación transaccional con controles previos al COMMIT.
- `resultado_carga_test.json`: resultado de la carga.
- `comparar_t055_stock.py` y `comparacion_t055_stock.json`: comparación reproducible y resultados.
- `t055_snapshot.json`: última extracción de la fuente; fue actualizada durante la inspección de columnas después de preparar la carga. El checksum de la versión corresponde a la extracción inicial, cuyo contenido importado queda preservado en el SQL y en `spl_stock_policy_import_row`.

El catálogo y diccionario del informe 03 son anteriores a esta migración; este documento registra los objetos añadidos.
