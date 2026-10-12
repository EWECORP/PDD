# Diagnóstico del backtest TEST de 21 orígenes — 2026-10-09

## Alcance

- Corrida analítica: `f963551d-0374-4c91-b330-35593a6ce725`.
- Orígenes: 2026-09-16 a 2026-10-06; horizonte diario 1; muestra determinística del 25%.
- Estado: `COMPLETED`, 21/21 orígenes, 1.665.804 filas de detalle y 8.208 métricas.
- Esta corrida es evidencia experimental de TEST. No modifica el modelo activo.

## Calidad comparativa

En `COMMON_VALID`/`ALL`, los siete estimadores son válidos sobre los mismos
140.399 casos. `PDVB_CANDIDATE` obtuvo WAPE **131,77%** y MAE **2,2312**;
`MEAN_28` obtuvo WAPE **128,83%** y MAE **2,1815**. La muestra común cubre
140.399 de 237.972 casos esperados (59,0%).

Para aislar el efecto de la validez de los otros cinco estimadores, también se
compararon sólo `PDVB_CANDIDATE` y `MEAN_28` sobre sus 185.351 casos válidos
pareados. El WAPE fue **131,31%** contra **128,66%**, y el MAE **2,0962** contra
**2,0539**. La desventaja del candidato persiste en esta comparación.

| Régimen | Exceso de error absoluto del candidato frente a `MEAN_28` |
| --- | ---: |
| `ERRATIC` | 4.395,6 unidades |
| `LUMPY` | 2.783,1 unidades |
| `SPARSE` | 638,1 unidades |
| `INTERMITTENT` | 26,5 unidades |

`SPARSE` tiene el WAPE relativo más llamativo, pero `ERRATIC` y `LUMPY`
explican la mayor parte del exceso absoluto de error de la corrida.

## Cobertura real

`PDVB_CANDIDATE` tiene 47.287 exclusiones `ACTUAL_COVERAGE_LOW` y 38.072
`PREDICTION_BLOCKED`. Las 47.287 exclusiones de cobertura corresponden a
`OUT_OF_STOCK` en `dm_pdd_venta_diaria`: hay 0 días elegibles de una ventana
diaria de 1 día. Reducir `actual_min_coverage` de 0,70 no recupera estos
casos. La exclusión evita evaluar demanda observada durante quiebres de stock.

## Hallazgo puntual en `SPARSE`

En los 11.105 casos válidos pareados de `SPARSE`, el WAPE del candidato fue
**164,50%** y el de `MEAN_28` **124,59%**. Los 4.508 casos `COMMON_VALID` de
los siete estimadores muestran una diferencia mayor (282,79% contra 151,55%);
la reducción de muestra cambia mucho el agregado.

De los 638,1 puntos de error absoluto adicional en el par de modelos, 639,4
proceden de 769 observaciones `SPARSE` con `fallback_level=0` y estado
`WARN`. El par artículo **18077**, sucursal **26** aporta 552,1 unidades de ese
exceso. Su ventana previa incluye una única venta de **819 unidades** el
2026-07-29, registrada como basal, sin bandera de venta especial ni promoción;
la disponibilidad se infirió por la venta aunque el stock registrado fue 0.
Para el origen 2026-09-20, la ventana previa tiene sólo 4 días elegibles y
media 204,75; el peso 0,25 aporta 51,1875 unidades al pronóstico, mientras
la venta real del día evaluado fue 0. Esto explica el sobrepronóstico puntual,
pero no demuestra que la venta de 819 unidades sea errónea.

## Contrafactual de cobertura histórica

Se recalculó el pronóstico **sólo en consulta**, sobre los mismos 185.351 casos
pareados, manteniendo pesos base 0,60/0,25/0,15 y renormalizando cuando una
ventana anterior o estacional no llega al mínimo de días elegibles. El mínimo
de 1 día reproduce exactamente el pronóstico vigente.

| Mínimo por ventana | WAPE global | WAPE `ERRATIC` | WAPE `LUMPY` | WAPE `SPARSE` |
| ---: | ---: | ---: | ---: | ---: |
| 1 (vigente) | 131,31% | 107,97% | 136,28% | 164,50% |
| 7 | 130,54% | 108,35% | 135,38% | 127,50% |
| 14 | 130,47% | 108,66% | 135,25% | 123,86% |
| `MEAN_28` pareado | 128,66% | 101,23% | 134,86% | 124,59% |

La regla mejora claramente `SPARSE` y parte de `LUMPY`, pero perjudica
`ERRATIC` y no alcanza a la referencia global. Es evidencia para un estimador
experimental segmentado, no para cambiar los pesos del modelo activo.

## Hallazgo en `ERRATIC`

El mayor par `ERRATIC` (artículo 42758, sucursal 18) aporta 665,5 unidades
adicionales de error absoluto. Una venta de 3.628 unidades del 2026-08-17
elevó la media de la ventana anterior a aproximadamente 159 unidades diarias,
frente a unas 31 en la ventana reciente. Las 28 fechas de la ventana anterior
son elegibles, por lo que un mínimo de días no resuelve este caso. La fuente
marca promoción normal; `dm_bve_ventas_enriquecidas` clasifica las 3.628
unidades como basales (3.600 + 28) y ninguna como promocional. PDD respeta esa
clasificación porque el desglose enriquecido conserva las unidades. Requiere
validar con el responsable de esa fuente si la operación y su clasificación
son correctas antes de corregir datos o reglas.

La regla que produce ese desglose está en
`ETL_DIARCO/scripts/datamart/sp_procesar_promos_mes.sql`: separa unidades
promocionales sólo si el precio cae por debajo del 90% de la mediana y las
unidades superan 1,8 veces la mediana. La transacción de 3.600 unidades tuvo
precio 461,983 frente a mediana 495,04 (93,32%) y mediana de 8 unidades;
por eso recibió `score_promo=40` pero quedó íntegra en `venta_basal`. La regla
vigente explica el resultado; decidir si debe reconocer ventas extraordinarias
sin descuento del 10% es una decisión de negocio y de la fuente ETL.

## Siguiente decisión

1. Validar con negocio si la operación de 819 unidades fue demanda regular,
   venta especial o un dato excepcional; revisar la clasificación enriquecida
   de la operación de 3.628 unidades y otros pares relevantes de `LUMPY`.
2. Probar alternativas **fuera del modelo activo** sobre los mismos orígenes y
   casos pareados: control de ventanas con pocos días elegibles y tratamiento
   explícito de ventas extremas justificadas por negocio.
3. Comparar WAPE, MAE, sesgo, cobertura y volumen por régimen antes de decidir
   cualquier cambio. El cron `PDD_MODEL_MONITORING_WEEKLY` permanece inactivo;
   su configuración actual de 56 orígenes al 100% requiere ajustarse antes de
   activarlo.
