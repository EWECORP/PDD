# Especificación de Demanda Basal (PDVB) y modelo físico

Versión: **1.0 — propuesta para decisión D1–D5**  
Fecha: **2026-08-02**  
Estado: **Diseño técnico y funcional para revisión; no autoriza aún el despliegue del DDL**  
Referencia rectora: `PDD - ALCANCE Fase 1.md`

---

## 1. Decisión propuesta

El **Promedio Diario de Venta Basal (PDVB)** debe ser una estimación diaria, por artículo–sucursal, de la demanda que se habría observado sin venta especial, campaña, promoción extraordinaria ni quiebre de stock.

El PDVB no es la venta observada de un día, la mediana de registros vendidos de un mes, el forecast total de una ventana, la venta promocional ni una necesidad de distribución. Es un insumo común e inmutable de la corrida que luego calcula:

```text
NDD-D = max((PDVB × Días Stock) - Stock Neto Sucursal, 0)

NDD-S = max(
          max((PDVB × Días Stock + PDVB × Días Sobre Stock)
              - max(Stock Neto Sucursal, 0), 0)
          - NDD-D,
          0
        )
```

La propuesta separa cuatro responsabilidades:

```text
fuentes existentes
    │
    ▼
venta diaria preparada ──► corrida/versiones/frescura
    │
    ▼
estimación PDVB inmutable ──► proyección PDVB vigente
    │
    ▼
pdd_branch_stock_position ──► pdd_need_snapshot D/S
```

## 2. Evidencia relevada

### 2.1 Base PostgreSQL `diarco_data`

Perfil observado el 2026-08-02:

| Entidad | Filas estimadas | Tamaño total | Cobertura observada |
| --- | ---: | ---: | --- |
| `src.base_ventas_extendida` | 100.506.952 | 40 GB | 2024-01-02 a 2026-08-01 |
| `datamart.dm_bve_ventas_enriquecidas` | 62.647.040 | 26 GB | 2025-04-01 a 2026-07-22 |
| `datamart.dm_bve_baseline_mensual` | 5.680.400 | 1.199 MB | 2025-04-01 a 2026-07-01 |

La fuente estaba actualizada hasta el 2026-08-01, mientras que la venta enriquecida terminaba el 2026-07-22. Existía una brecha de diez días. Una corrida PDVB no debe mezclar silenciosamente ambas coberturas.

### 2.2 Grano real

Las dos tablas de venta tienen clave `fecha + codigo_articulo + sucursal + precio`; no tienen grano diario artículo–sucursal. En el último día de la fuente se observaron 221.567 registros, 120.904 pares artículo–sucursal, 8.112 artículos y 91 sucursales.

Promediar directamente filas ponderaría los días por la cantidad de precios/registros. Antes de estimar PDVB es obligatorio agregar a `fecha_operativa + codigo_articulo + sucursal`.

### 2.3 Calidad de señales

En el último día de `src.base_ventas_extendida`:

- `con_stock = true` en las 221.567 filas; las estadísticas de PostgreSQL también muestran un solo valor distinto. Hoy no permite identificar quiebres;
- `venta_especial = true` en 0 filas;
- `promo_normal = true` en 9.142 filas;
- `promo_fuerte = true` en 0 filas;
- `precio_prefijado` era nulo en todas las filas, aunque `factor_precio` estaba informado. Esa combinación requiere reconciliación de contrato y linaje.

En el último día disponible de `dm_bve_ventas_enriquecidas`:

- 89.555 filas correspondían a 72.870 pares artículo–sucursal;
- 5.041 filas tenían `score_promo >= 70`;
- 1.636 tenían `promo_fuerte_detectada = true`;
- se cumplía `unidades = venta_basal + venta_promocional` en todas las filas evaluadas.

La conservación de unidades es positiva. La diferencia entre `score_promo >= 70` y `promo_fuerte_detectada` debe conservarse: el proceso recorta venta basal desde 70, mientras la bandera fuerte sólo identifica el umbral máximo.

### 2.4 Baseline mensual

Para julio de 2026 había 291.466 filas. De ellas, 130.631 (44,8 %) tenían menos de cinco registros y la mediana de `registros` era cinco.

`dm_bve_baseline_mensual` es útil como estadística auxiliar de precio y cantidad, pero no como PDVB porque:

1. cuenta filas de venta/precio, no días calendario ni días servibles;
2. no materializa los días con venta cero;
3. se calcula con el mismo mes del registro evaluado;
4. el mes vigente puede estar incompleto;
5. para evaluación histórica puede usar observaciones posteriores al día estimado;
6. una mediana de unidades por registro no equivale a una tasa diaria.

`factor_elasticidad` tampoco es una elasticidad precio estadística: es el cociente entre dos razones puntuales. Puede ser señal heurística, no coeficiente causal.

### 2.5 Operación actual del enriquecimiento

`datamart.sp_procesar_promos_mes` elimina y regenera el baseline y la venta enriquecida del rango. Calcula medianas mensuales por artículo–sucursal, asigna scores 0/40/70/100 por umbrales de precio y unidades, limita `venta_basal` a `unidades_mediana` con score 70 o 100 y deja el excedente como `venta_promocional`.

El log sólo contenía una ejecución productiva registrada (2026-05-25), aunque las tablas tenían datos posteriores. La observabilidad no cubre todos los caminos de actualización y debe ser un gate.

## 3. Reutilización de `FORECAST`

### 3.1 Componentes valiosos

Se reutilizan como conocimiento y casos de prueba:

- agregación diaria por artículo–sucursal;
- ventanas reciente, anterior y comparable del año previo;
- concepto de día servible según stock;
- separación entre `Average` diario y `Forecast` de ventana;
- `dias_servibles`, `factor_disponibilidad` y motivo;
- redondeo diferenciado para pesables;
- políticas explícitas ante stock faltante.

`ALGO_01` es el antecedente más cercano; `ALGO_05` aporta la media reciente stock-aware; `ALGO_08`, una variante plana sin stock.

### 3.2 Componentes que no deben copiarse sin corregir

- `generar_datos` mezcla consultas, CSV, transformación y dominio, y lee ventas por caminos diferentes.
- Las funciones consultan la base internamente. La nueva función debe ser pura: recibe features/parámetros y devuelve resultados.
- `ALGO_01` declara normalizar pesos, pero no divide por la suma. Con 0,8 + 0,1 + 0,2 infla el resultado 10 %.
- `ALGO_01` trae pocos meses de stock aunque estima una ventana del año anterior.
- `asume_disponible` convierte stock desconocido en servible y puede subestimar demanda.
- `ALGO_05` combina `CURRENT_DATE` en SQL con la fecha recibida; no permite backtest histórico confiable.
- Existe depuración para un artículo/sucursal fijo dentro de producción.
- `MIN_AVG_DAILY` crea un piso aun con evidencia insuficiente; en PDD debe ser regla versionada y visible.
- `ALGO_08` usa factores no normalizados por diseño; puede representar uplift, no demanda basal.
- Hay copias versionadas, LAB y OLD. PDD debe tener una implementación canónica con versión y commit.

Se reutiliza el enfoque, las pruebas y parte de la transformación; no se recomienda importar `funciones_forecast.py` como dependencia de dominio.

## 4. Fuentes y autoridad

| Prioridad | Fuente | Uso propuesto |
| ---: | --- | --- |
| 1 | `src.base_ventas_extendida` | Venta observada, precio, maestro snapshot y banderas comerciales |
| 2 | `datamart.dm_bve_ventas_enriquecidas` | Separación basal/promocional si está fresca y reconciliada |
| 3 | `datamart.dm_bve_baseline_mensual` | Features/control de promoción; nunca PDVB final |

Las tres entidades no bastan para demanda censurada por falta de stock. Se requieren surtido/vigencia artículo–sucursal, stock histórico o `con_stock` confiable, calendario comercial, unidad/pesables y campañas/ventas especiales.

Hasta corregir `con_stock`, un cero sin stock conocido será `AVAILABILITY_UNKNOWN`, no venta cero ni quiebre asumido.

## 5. Contrato de la venta diaria preparada

`datamart.dm_pdd_venta_diaria` tendrá una fila por fecha–artículo–sucursal, construida desde el calendario de surtido activo con left join de ventas.

1. `unidades_observadas = sum(unidades)` de todos los precios.
2. Unidades negativas se separan; no son demanda negativa.
3. Basal/promocional se suma desde la enriquecida sólo con cobertura y checksum válidos.
4. Sin enriquecimiento válido se usa contingencia identificada y baja la confianza.
5. Venta positiva prueba día servible aunque stock diga cero.
6. Surtido activo, sin venta y con stock positivo: cero elegible.
7. Día sin stock: censurado, fuera del denominador.
8. Disponibilidad desconocida: no elegible en modo conservador.
9. Venta especial/campaña se excluye o ajusta mediante regla aprobada.
10. Debe cumplirse `observada_no_negativa = basal + promocional` dentro de tolerancia.

## 6. Algoritmo PDVB v1 propuesto

### 6.1 Corte y frescura

Para fecha operativa `T`, `fecha_corte = T - 1 día cerrado`. Nunca se usa el día intradiario. Si una fuente obligatoria no llega al corte, la corrida queda `BLOCKED` o mantiene la última proyección válida con alerta; no publica mezcla parcial.

### 6.2 Ventanas iniciales configurables

Valores para backtest, aún no aprobados:

| Componente | Ventana | Peso inicial |
| --- | ---: | ---: |
| Reciente | últimos 28 días | 0,60 |
| Anterior | 28 días anteriores | 0,25 |
| Estacional | 28 días comparables del año anterior | 0,15 |

```text
media_w = sum(unidades_basal elegibles) / días_elegibles
PDVB_raw = sum(peso_w × media_w) / sum(peso_w disponible)
```

Los ceros con stock cuentan; días censurados no. Sólo participan ventanas con evidencia mínima y los pesos se renormalizan.

### 6.3 Evidencia y fallback

1. `SKU_BRANCH_WEIGHTED`: tres ventanas suficientes.
2. `SKU_BRANCH_RECENT`: sólo ventanas recientes suficientes.
3. `SKU_NETWORK_SHRINKAGE`: mismo artículo en sucursales comparables, sólo artículo nuevo y regla aprobada.
4. `INSUFFICIENT_DATA`: no publicar automáticamente y generar excepción.

No se recomienda fallback automático por categoría en el MVP. Para demanda intermitente, el promedio incluye ceros servibles. ADI y CV² quedan como diagnóstico para futura evaluación Croston/SBA.

### 6.4 Ajustes, estado y precisión

- La corrección promocional ocurre antes de estimar.
- Un tope robusto puede probarse, conservando original, ajustada y motivo.
- No se elimina una venta alta sólo por ser outlier.
- Toda regla se versiona.
- Estados: `OK`, `WARN`, `BLOCKED`, `ZERO_VALID`.
- Confianza 0–100 resume cobertura, frescura, promoción, stock y fallback; no oculta causas.
- PDVB se guarda `numeric(18,6)`. El redondeo logístico ocurre al crear `pdd_need_snapshot`.

## 7. Tablas a crear

El DDL detallado está en `PDD - DDL Demanda Basal PostgreSQL v1.0.sql`.

| Tabla | Propósito y grano |
| --- | --- |
| `stock_management.pdd_pdvb_model_version` | Configuración inmutable, vigencia, parámetros, checksum, commit y aprobación |
| `stock_management.pdd_calculation_run` | Tipo + fecha operativa + ámbito + intento; cabecera común del modelo conceptual |
| `stock_management.pdd_source_snapshot` | Una fuente consumida por corrida, con rango, frescura, filas y checksum |
| `datamart.dm_pdd_venta_diaria` | Feature incremental: fecha + artículo + sucursal |
| `stock_management.pdd_pdvb_estimate` | Resultado inmutable por corrida + artículo + sucursal, con componentes explicativos |
| `stock_management.pdd_pdvb_current` | Proyección vigente por artículo + sucursal, publicada atómicamente |
| `stock_management.pdd_pdvb_quality_issue` | Excepciones y resolución, sin copiar líneas correctas |
| `datamart.dm_pdd_pdvb_backtest_run` | Cabecera y estado de una evaluación rolling-origin |
| `datamart.dm_pdd_pdvb_backtest_detail` | Fecha origen + fecha evaluación + estimador + artículo + sucursal |
| `datamart.dm_pdd_pdvb_backtest_metric` | Métrica analítica comparativa por estimador, muestra y segmento |
| `stock_management.pdd_pdvb_backtest_metric` | Métrica por versión, período, horizonte y segmento |

`dm_pdd_venta_diaria` se actualiza idempotentemente cuando upstream reprocesa 14 días. `pdd_pdvb_estimate` nunca se muta y guarda sumas, días, medias, pesos, PDVB raw/publicado, ADI/CV², confianza, fallback, explicación y linaje.

## 8. Integración con DECAS

`pdd_branch_stock_position` agregará `pdvb_business_date`, `pdvb_estimate_id`, `pdvb_value` snapshot, `pdvb_status`, confianza y versión. El snapshot mantiene explicable D/S aunque cambie la proyección.

- `OK`, `WARN` aprobado o `ZERO_VALID` pueden alimentar D/S.
- `BLOCKED`/`INSUFFICIENT_DATA` no generan D/S automática y alertan.
- Una corrección crea nueva corrida; no muta `pdd_need_snapshot` anterior.
- Nunca se consume `pdd_pdvb_current` sin verificar fecha/frescura.

## 9. Particionado, índices y volumen

- Feature y estimación: partición mensual.
- Índice de feature `(codigo_articulo, sucursal, sales_date desc)` y BRIN por fecha.
- Índices de estimación por corrida/estado y par/fecha.
- `pdd_pdvb_current`: PK `(codigo_articulo, sucursal)`.
- Crear particiones tres meses hacia adelante; evitar default que oculte fallas.
- Retención propuesta de features: 30 meses, pendiente de política.
- Estimaciones/snapshots siguen auditoría y no se truncan con features.
- No propagar tipo `money`; usar `numeric`.

## 10. Controles obligatorios

Antes: fuentes hasta el corte, sin duplicados diarios, surtido/calendario, stock medido, conservación basal/promocional, modelo aprobado y cero observaciones futuras.

Después: PDVB finito/no negativo, pesos suman 1, días dentro de ventana, `ZERO_VALID` con evidencia, `BLOCKED` nunca como cero, cobertura contra surtido, saltos explicados y publicación atómica.

## 11. Backtest y aceptación

Backtest rolling-origin: para `T` sólo datos disponibles hasta `T-1`. Cubrir alta/baja rotación, intermitentes, pesables, Diarco/Barrio, promociones, quiebres, nuevos/discontinuados y estacionalidad.

La comparación implementada conserva `PDVB_CANDIDATE`, media simple de 28
días y dos variantes explícitas de `ALGO_01`: `ALGO_01_GROWTH` usa
0,8/0,1/0,2 sin normalizar porque el total 1,1 representa crecimiento
intencional; `ALGO_01_NORMALIZED` divide por los pesos disponibles y permite
aislar el efecto estadístico de ese uplift. La fase experimental agrega
`OCCURRENCE_SIZE`, `CROSTON_SBA` y `HYBRID_EXPERIMENTAL`. Ninguno sustituye al
PDVB publicado sin una nueva versión de modelo aprobada.

La evaluación admite `POINT_DAILY` para el día `T+h` y `CUMULATIVE` para la
demanda total de `T+1..T+h`. El modo acumulado registra días elegibles,
cobertura real y demanda observada estandarizada a la ventana completa; el
umbral inicial de cobertura es 70%. Los resultados se segmentan también por
régimen ADI/CV², rubro y subrubro de nivel 1.

Las métricas se calculan sobre dos muestras. `OWN_VALID` refleja cobertura y precisión propia de cada estimador. `COMMON_VALID` usa exclusivamente observaciones válidas para todos los candidatos y es la muestra rectora para comparar algoritmos sin sesgo de selección. BIAS positivo significa subpronóstico (`real - pronóstico`) y BIAS negativo, sobrepronóstico.

Criterios: cero fuga temporal; resultados explicables; reconciliación; idempotencia; ningún bloqueado convertido en cero; bias/WAPE no peores que media simple por segmentos acordados; impacto D/S validado; SLA cumplido. MAPE no es métrica rectora por demanda cero.

## 12. Secuencia

### D1–D2

Ratificar definición/corte; identificar surtido, calendario y stock oficiales; corregir `con_stock`; certificar enriquecimiento/logging; congelar fixtures.

### D3–D5

Construir muestra diaria; implementar estimadores puros; backtest; aprobar ventanas/pesos/mínimos/fallback/stock desconocido; aprobar DDL/particiones.

### D6–D14

Migraciones; carga incremental/reproceso; persistencia de corrida/snapshots/estimaciones/excepciones; publicación atómica; integración con `pdd_branch_stock_position` y pruebas D/S.

## 13. Decisiones abiertas

| Decisión | Recomendación inicial | Dueño |
| --- | --- | --- |
| Día cerrado/timezone | `T-1`, America/Buenos_Aires | Datos/Operación |
| Stock desconocido | excluir y alertar | Datos/PO |
| Ventanas/pesos | 28/28/año; 0,60/0,25/0,15 | Forecast/PO |
| Evidencia mínima | configurable por ventana/segmento | Forecast |
| Piso PDVB | ninguno implícito | PO |
| Fallback artículo-red | sólo nuevo y aprobado | PO/Compras |
| Score promo 70 | ajustar basal, conservar nivel | Comercial/Datos |
| Especial/campaña | excluir de basal | Comercial |
| Devoluciones | separar de demanda | Finanzas/Datos |
| Retención | 30 meses features | Arquitectura |

## 14. Resultado

Si se aprueba, D/S consumirá `stock_management.pdd_pdvb_current`, conservando vínculo a `stock_management.pdd_pdvb_estimate`. `dm_bve_baseline_mensual` seguirá como insumo auxiliar del detector de promoción y no se expondrá como PDVB.
