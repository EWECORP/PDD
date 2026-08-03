# Addendum — Universo CD 41 y stock diario canónico

Versión: **1.1**  
Fecha: **2026-08-02**  
Estado: **Propuesta para ratificación funcional y técnica**  
Complementa y, donde exista diferencia, prevalece sobre: `PDD - Especificacion de Demanda Basal y Tablas v1.0.md`.

---

## 1. Decisiones incorporadas

1. La demanda D/S de Fase 1 se calcula sólo para productos potencialmente distribuibles desde el CD/local 41.
2. El conteo de artículos es dinámico: no se hardcodea 2.975 ni ningún otro valor.
3. La elegibilidad del artículo en el CD y la ruta CD–sucursal se versionan por separado.
4. `src.t710_estadis_stock` se normaliza una sola vez a stock diario canónico.
5. Una venta positiva prueba que el día fue servible.
6. En un día sin venta, el stock diario decide si el cero es observable o está censurado.

## 2. Universo de cálculo

### 2.1 Artículo elegible en CD 41

La regla informada es:

```sql
SELECT DISTINCT c_articulo
FROM src.base_productos_vigentes
WHERE c_sucu_empr = 41
  AND active_for_purchase = 1;
```

Esta consulta define el conjunto de artículos que el CD puede adquirir para su circuito. En la fotografía consultada el 2026-08-02 devolvió 2.915 artículos, mientras que el valor funcional informado fue 2.975. La diferencia es consistente con el proceso de reconstrucción en curso y confirma que el valor debe capturarse como snapshot, no como parámetro fijo.

### 2.2 Par distribuible CD–sucursal–artículo

La pertenencia del artículo al surtido del local 41 es necesaria, pero no suficiente para generar NDD en una sucursal. El artículo también debe estar habilitado en la sucursal destino y su ruta de abastecimiento debe corresponder al CD 41.

Regla candidata para ratificar:

```sql
WITH cd_articles AS (
    SELECT DISTINCT c_articulo
    FROM src.base_productos_vigentes
    WHERE c_sucu_empr = 41
      AND active_for_purchase = 1
)
SELECT
    41 AS origin_cd,
    p.c_sucu_empr AS destination_branch,
    p.c_articulo,
    p.c_proveedor_primario,
    p.cod_cd,
    p.abastecimiento
FROM src.base_productos_vigentes p
JOIN cd_articles a USING (c_articulo)
WHERE p.c_sucu_empr <> 41
  AND p.habilitado = 1
  AND p.active_for_sale = 1
  AND p.active_on_mix = 1
  AND p.cod_cd = '41CD';
```

En la foto relevada:

- `cod_cd = '41CD'` tenía 86.551 pares antes de aplicar todas las habilitaciones;
- 61.828 estaban `habilitado = 1`;
- 59.512 cumplían simultáneamente `habilitado`, `active_for_sale` y `active_on_mix`;
- el universo estricto cubría 49 sucursales.

Debe confirmarse si `cod_cd = '41CD'` y `abastecimiento = 0` son la regla normativa o si existe otra equivalencia. Hasta esa ratificación, el filtro queda como candidato y no como verdad definitiva.

### 2.3 Versionado del scope

Cada corrida referencia una versión inmutable con:

- artículos habilitados en el CD;
- pares CD–sucursal–artículo distribuibles;
- consulta/filtros utilizados;
- fecha de extracción;
- conteos y checksum.

Un cambio de 2.915 a 2.975 artículos genera una nueva versión. No reescribe corridas anteriores.

## 3. Fuente histórica de stock

### 3.1 Estado actual

`src.t710_estadis_stock` tiene grano:

```text
año + mes + sucursal + artículo
```

y 31 columnas de cantidad. Su PK es `(c_anio, c_mes, c_sucu_empr, c_articulo)`.

Perfil observado:

- cobertura desde enero de 2024 hasta agosto de 2026;
- aproximadamente 33,46 millones de filas y 13 GB;
- último mes: 1.185.090 filas, 15.687 artículos y 109 sucursales;
- intersección del último mes con el surtido actual del CD 41: 242.222 pares mensuales, 2.915 artículos y 109 sucursales.

La tabla no debe ser desarmada repetidamente dentro de cada algoritmo: recorrer filas y columnas en Python es costoso, duplica reglas y dificulta el backtest.

### 3.2 Advertencias de calidad

- `procesado_ok` aparece `false` en todos los meses inspeccionados. No puede usarse como rechazo hasta aclarar su semántica.
- El stock admite valores negativos; se preservan como cantidad observada, pero para servibilidad equivalen a no disponible.
- En agosto, `q_dia1` estaba poblado y `q_dia2` todavía estaba íntegramente en cero al momento del relevamiento. Los días deben materializarse sólo cuando estén cerrados.
- `fecha_proceso` y `fuente_origen` se conservan como linaje.

## 4. Stock diario canónico

Se agrega `datamart.dm_pdd_stock_diario`, particionada mensualmente, a grano:

```text
fecha_stock + artículo + sucursal
```

El proceso SQL usa `CROSS JOIN LATERAL VALUES` para convertir `q_dia1..q_dia31` en filas, descartando días inexistentes del mes.

Reglas de materialización:

1. incluir sólo fechas válidas;
2. incluir sólo fechas `<= fecha_corte`;
3. provisionalmente, considerar cerrado hasta `fecha_proceso::date - 1`; esta regla requiere ratificación del horario del LEGACY;
4. preservar cantidad negativa, cero o positiva;
5. hacer upsert idempotente por fecha–artículo–sucursal;
6. recalcular mes vigente y cualquier mes reprocesado;
7. registrar checksum y timestamp de la fila mensual fuente;
8. restringir inicialmente a artículos/pares del scope CD 41 para contener volumen.

No materializar una fila futura con cero: ausencia de fila significa `UNKNOWN`, no stock cero.

## 5. Regla de día servible

La venta diaria y el stock diario se combinan así:

| Venta del día | Fila stock | Cantidad stock | Disponibilidad | ¿En denominador PDVB? |
| ---: | --- | ---: | --- | --- |
| > 0 | cualquiera | cualquiera | `INFERRED_FROM_SALE` | Sí |
| = 0 | presente | > 0 | `IN_STOCK` | Sí, con venta basal 0 |
| = 0 | presente | = 0 | `OUT_OF_STOCK` | No |
| = 0 | presente | < 0 | `OUT_OF_STOCK` | No |
| = 0 | ausente | — | `UNKNOWN` | No; alerta si supera umbral |
| cualquiera | fuera de surtido | — | `NOT_ASSORTED` | No |

Fórmula de la media de una ventana:

```text
días_servibles = días INFERRED_FROM_SALE + días IN_STOCK

media_basal =
  sum(venta_basal en días servibles) / días_servibles
```

Esto evita dos sesgos opuestos:

- contar como cero los días sin stock, que subestima demanda;
- eliminar todos los días sin venta, que sobreestima demanda.

## 6. Flujo revisado

```text
base_productos_vigentes
    └─► versión de scope CD41

t710_estadis_stock
    └─► dm_pdd_stock_diario

base_ventas_extendida + dm_bve_ventas_enriquecidas
    └─► dm_pdd_venta_diaria
            + stock diario
            + scope vigente
                └─► pdvb_estimate
                        └─► pdvb_current
                                └─► D/S
```

Orden operativo:

1. cerrar/reconstruir fuentes;
2. capturar versión de scope;
3. normalizar/reprocesar stock diario;
4. preparar venta diaria;
5. ejecutar gates de frescura y cobertura;
6. estimar PDVB sólo para pares del scope;
7. publicar proyección atómicamente;
8. calcular posición de stock y D/S.

## 7. Cambios al modelo físico v1.0

Se agregan:

| Tabla | Grano |
| --- | --- |
| `pdd.distribution_scope_version` | una versión del universo de un CD |
| `pdd.distribution_scope_article` | versión + artículo elegible en CD |
| `pdd.distribution_scope_pair` | versión + sucursal destino + artículo |
| `datamart.dm_pdd_stock_diario` | fecha + sucursal + artículo |

Se modifican:

- `calculation_run`: referencia obligatoria a la versión de scope para corridas PDVB/Daily DECAS;
- `dm_pdd_venta_diaria`: snapshot de cantidad/hash de stock usado;
- `pdvb_estimate`: CD origen y versión de scope;
- `pdvb_current`: CD origen y versión de scope.

El SQL incremental está en `PDD - DDL Addendum CD41 y Stock Canonico v1.1.sql` y se aplica después del DDL v1.0.

## 8. Gates específicos

### Scope

- conteo de artículos y pares no nulo;
- variación contra versión anterior dentro de umbral o aprobada;
- cero duplicados;
- toda pareja referencia un artículo de la misma versión;
- ruta CD 41 válida.

### Stock

- fecha máxima canónica >= fecha de corte;
- cero fechas inválidas/futuras;
- una fila por fecha–artículo–sucursal;
- cobertura medida sobre pares y días esperados;
- negativos reportados, no convertidos silenciosamente;
- `procesado_ok` monitoreado, pero no usado como gate hasta aclaración;
- caída anómala del porcentaje de stock positivo genera alerta.

### Publicación

- sólo pares presentes en `distribution_scope_pair`;
- scope, stock, venta y estimación comparten fecha de corte;
- ausencia de stock por encima del umbral bloquea o degrada según versión aprobada;
- cambios de scope no eliminan historia, sólo la proyección vigente.

## 9. Decisiones pendientes

1. Confirmar `cod_cd = '41CD'` y `abastecimiento = 0` como ruta desde el CD 41.
2. Confirmar si se exigen simultáneamente `habilitado`, `active_for_sale` y `active_on_mix`.
3. Aclarar semántica y ciclo de `procesado_ok`.
4. Confirmar si `q_diaN` es stock de cierre y el timezone de `fecha_proceso`.
5. Definir porcentaje mínimo de cobertura de stock para `OK`, `WARN` y `BLOCKED`.
6. Definir retención: para la ventana estacional se recomiendan al menos 15 meses; para auditoría, 30 meses.

