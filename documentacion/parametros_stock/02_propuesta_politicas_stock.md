# Propuesta de mantenimiento de días de stock desde CONNEXA

> Documento histórico. Para el estado actual y la decisión de reutilizar `inventory`, consultar la [auditoría de TEST del 14/09/2026](07_auditoria_inventory_test_20260914.md). Los conteos y recomendaciones siguientes corresponden a su fecha original.

Estado: diseño lógico preliminar. Los nombres son propuestos; no representan tablas verificadas en TEST.

## Ubicación recomendada

El concepto es una **política de reposición y cobertura**. Recomiendo evaluar primero `replenishment`, porque hay un antecedente explícito en el repositorio. `stock_management` también es coherente si CONNEXA concentra allí las políticas de inventario y la distribución. `procurement` es válido si el dominio de abastecimiento ya es dueño de estas políticas, pero no debería elegirse sólo porque existe una clasificación de compra: los parámetros también gobiernan transferencias desde CD.

La decisión final debe reutilizar el dominio desplegado y su auditoría, evitando dos maestros de políticas. Los parámetros utilizados por cada corrida permanecen en `stock_management.pdd_branch_stock_position` como evidencia histórica.

## Modelo recomendado

La clave propuesta `c_sucursal, c_familia, c_rubro, c_clasificacion_compra` es una buena primera granularidad. Para mantener grupos de locales sin duplicar filas, separar el ámbito de aplicación de la regla.

| Entidad lógica | Contenido y responsabilidad |
|---|---|
| Perfil de local | Código, descripción; agrupa una combinación acordada de zona, tipo y tamaño. Reutilizar atributos maestros existentes. |
| Asignación local–perfil | Local, perfil, vigencia desde/hasta. Un único perfil efectivo por local y fecha en la primera versión. |
| Versión de política | Identificador, estado BORRADOR/PUBLICADA/RETIRADA, vigencia, autor, fecha de publicación y motivo. Las versiones publicadas son inmutables. |
| Regla de stock | Versión, ámbito GLOBAL/PERFIL/LOCAL, referencia al perfil o local, familia, rubro, clasificación de compra, días objetivo y días de sobrestock. |
| Resolución por artículo/local | Corrida, fecha, artículo, local, versión y regla ganadora, días efectivos, atributos de clasificación/perfil usados y procedencia CONNEXA/LEGACY. Puede integrarse a la fotografía existente de PDD. |

Si la base es multiempresa, todas las identidades, unicidades y relaciones deben respetar empresa/tenant. Reutilizar las claves canónicas, manteniendo códigos SGM como códigos externos para integración.

Campos mínimos propuestos para la regla:

```text
policy_version_id, rule_id
scope_type                  GLOBAL | PROFILE | LOCAL
site_profile_id             sólo para PROFILE
site_id                     sólo para LOCAL
c_familia, c_rubro           filtros opcionales; rubro requiere familia
c_clasificacion_compra      filtro opcional
q_dias_stock                número >= 0, obligatorio
q_dias_sobre_stock          número >= 0, obligatorio
priority                   desempate explícito entre filtros solapados
```

NULL en un filtro significa «cualquiera», no «clasificación desconocida». Un artículo sin clasificación sólo coincide con reglas que no la exigen. No usar 0 como comodín. Ambos días siempre se resuelven desde la misma regla: no mezclar el stock de una regla y el sobrestock de otra. Definir si la UI admite fracciones; el cálculo actual admite decimales, aunque la carga del legado convierte esos campos a enteros.

## Clasificación de compra, ABC y rotación

Comenzar con clasificación de compra y familia/rubro satisface la estructura sugerida. Para políticas diferentes según A, sensible o alta rotación, confirmar antes si son dimensiones independientes. Un artículo puede ser simultáneamente A y sensible; la rotación puede variar entre locales y fechas.

Si se requiere esa capacidad desde la primera versión, añadir filtros tipados `abc_class`, `rotation_class`, `is_sensitive` y resolver sus fuentes y vigencias. Para un booleano, NULL significa cualquiera y false significa no sensible. Todos los filtros de una regla se combinan con AND. Una condición OR se expresa con varias reglas. No convertir A/SENSIBLE/ALTA_ROTACION en una sola enumeración excluyente.

## Resolución determinista

Propuesta de precedencia, a validar funcionalmente:

1. Seleccionar la versión publicada para la fecha de negocio y la empresa; fijarla al inicio de la corrida.
2. Obtener perfil y clasificación vigentes del artículo/local y conservar la fotografía de esos atributos.
3. Seleccionar reglas cuyos filtros coinciden.
4. Priorizar LOCAL sobre PROFILE sobre GLOBAL. Dentro del mismo ámbito, usar `priority` descendente explícita. La UI puede sugerir prioridades mayores para reglas específicas, pero no inferir silenciosamente un orden entre familia y clasificación.
5. Si dos reglas ganadoras tienen el mismo ámbito y prioridad, bloquear publicación o resolución con error de ambigüedad. No desempatar por ID o fecha de creación.
6. Si no hay regla, aplicar el tratamiento de cobertura faltante definido para la transición; en operación final, bloquear ese cálculo y reportar el faltante.

Esto implica que una regla LOCAL genérica vence a una regla PROFILE específica: mostrar esa consecuencia en la previsualización. Si el negocio prefiere lo contrario, cambiar y versionar la precedencia antes de implementar.

Ejemplo ilustrativo, no valores recomendados:

| Ámbito | Familia/rubro | Compra | Prioridad | Stock | Sobrestock |
|---|---|---|---:|---:|---:|
| GLOBAL | cualquiera | cualquiera | 0 | 10 | 2 |
| PROFILE: zona sur/grande | F1/R1 | cualquiera | 10 | 14 | 3 |
| PROFILE: zona sur/grande | F1/R1 | sensibles | 20 | 14 | 6 |
| LOCAL: L1 | F1/R1 | sensibles | 20 | 12 | 4 |

Un sensible F1/R1 de L1 obtiene 12/4. Otro local del perfil obtiene 14/6. Para PDVB=10 y stock neto=50, la regla 12/4 produce M=120, O=40, D=70 y S=40 antes del redondeo logístico.

## Integridad y mantenimiento

- Días obligatorios y no negativos; vigencias con inicio anterior a fin, usando intervalos [desde, hasta). Cero es una decisión válida.
- Exigir exactamente la referencia correspondiente a cada ámbito; impedir un local y un perfil simultáneos.
- Referencias a catálogos reales; verificar familia/rubro como relación y no como dos códigos independientes.
- Una versión efectiva por política/empresa y fecha; un perfil efectivo por local y fecha. Bloquear solapamientos de vigencia.
- Impedir duplicados incluso cuando los filtros son NULL. El mecanismo SQL depende de la versión PostgreSQL real; no confiar en UNIQUE convencional para ese caso.
- Validar ambigüedades y cobertura de todos los pares activos antes de publicar. Volver a validar cuando cambien perfiles, clasificaciones o surtido, porque pueden aparecer nuevas colisiones.
- Conservar auditoría de autor, antes/después, motivo y publicación. Edición concurrente con control de versión. Una modificación crea nueva versión; no reescribe corridas anteriores.
- UI de CONNEXA con edición por perfil/local, filtros de familia/rubro/clasificación, carga masiva validada y previsualización del valor efectivo con explicación de la regla ganadora.
- Simular diferencias de D/S antes de publicar: locales y artículos afectados, días anteriores/nuevos y variación de unidades/bultos. Mayor sobrestock no implica automáticamente una mejor política: revisar restricciones de capacidad y vida útil ya disponibles en el producto.

## Integración con PDD y transición

1. Relevar TEST y decidir qué entidades existentes extender. Confirmar significado de `safety_stock_days` antes de reutilizarlo para S.
2. Crear el maestro de reglas y la resolución con versionado. Iniciar con la clasificación de compra existente y perfiles simples; incorporar ABC/rotación cuando estén definidas sus fuentes.
3. Preparar una carga inicial desde valores legados reconciliados. Si dentro de una combinación propuesta hay distintos días por artículo, registrar las excepciones; no promediar ni sobrescribir silenciosamente.
4. Ejecutar resolución CONNEXA en paralelo al cálculo vigente y comparar días, D, S y redondeos sobre la misma fotografía de PDVB/stock/logística.
5. Modificar la orquestación de `daily_decas.py`: seguir leyendo existencias y movimientos de su fuente, pero entregar los días resueltos desde CONNEXA a `build_branch_position`. Crear tablas sin cambiar esa lectura no cambia el comportamiento actual.
6. Como las fuentes analítica y operativa son bases diferentes, resolver mediante una lectura de aplicación o una fotografía replicada/versionada en el datamart. No asumir un JOIN SQL entre bases. Fijar versión y completar todos los pares antes de publicar la corrida; si falla la obtención, no publicar un resultado parcial.
7. Guardar IDs de regla/versión, origen, días efectivos y atributos usados en la evidencia de corrida. Verificar la relación con la configuración operativa ya versionada para no duplicar responsabilidades.
8. Durante una transición explícita se puede usar fallback al legado únicamente en pares sin política, guardando origen y alertas. No usarlo ante errores de conexión o reglas ambiguas, ni mezclar uno de los días de cada fuente. Al cerrar la migración, eliminar el fallback y exigir cobertura CONNEXA.
9. Mantener las tablas `src` como reflejo del origen para conciliación; el CDC no debe sobrescribir las políticas editadas en CONNEXA. Revertir activando una nueva versión válida o el modo transitorio acordado, sin alterar historia.

## Criterios de aceptación

- Un mismo artículo puede obtener días diferentes según local/perfil.
- Una excepción local vence al perfil y una clasificación específica se aplica con prioridad explícita.
- Reglas ambiguas, versiones superpuestas y pares sin cobertura producen un diagnóstico visible.
- Ceros, stock negativo, PDVB cero y límites de vigencia conservan el comportamiento esperado de D/S.
- Cambiar una regla publicada no cambia la reproducción de una corrida histórica.
- Para los mismos valores efectivos, PDVB, stock y logística, el nuevo flujo produce las mismas D/S y redondeos que el actual.

La selección definitiva de esquema, claves físicas, restricciones SQL y migración queda pendiente del catálogo de PGP_TEST_DB. El fallo de autenticación impide afirmar que hoy falten estas capacidades en esa base.
