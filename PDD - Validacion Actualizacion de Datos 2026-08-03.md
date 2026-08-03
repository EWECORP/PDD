# Validación de actualización de datos — cierre mensual

Fecha de validación: **2026-08-03**  
Estado: **Frescura recuperada; observabilidad pendiente**

## Resultado

La brecha de diez días identificada durante el relevamiento inicial quedó resuelta. Las fuentes necesarias para comenzar el prototipo PDVB llegan hasta el mismo último día cerrado:

| Entidad | Fecha máxima | Fecha de cálculo observada |
| --- | --- | --- |
| `src.base_ventas_extendida` | 2026-08-01 | carga fuente vigente |
| `datamart.dm_bve_ventas_enriquecidas` | 2026-08-01 | 2026-08-03 00:11:26 |
| `datamart.dm_bve_baseline_mensual` | 2026-08-01 | 2026-08-03 00:11:26 |

La incidencia de frescura se considera cerrada. El gate de frescura definido en la especificación permanece como control permanente.

## Reconciliación de julio de 2026

`dm_bve_ventas_enriquecidas` contiene los 31 días de julio:

- 3.408.989 registros;
- 0 registros con `venta_basal` o `venta_promocional` nula;
- 0 diferencias en `unidades = venta_basal + venta_promocional` con tolerancia 0,001;
- 162.845 registros con `score_promo >= 70`;
- 27.467 registros con `promo_fuerte_detectada = true`;
- 23.029.864,391 unidades observadas;
- 19.251.883,5015 unidades basales;
- 3.777.980,8895 unidades promocionales.

El baseline de julio quedó en:

- 223.642 pares mensuales;
- 9.237 artículos;
- 93 sucursales;
- 154.706 filas con menos de cinco registros;
- mediana de tres registros por artículo–sucursal.

La reconstrucción confirma la conservación de unidades, pero no cambia la decisión arquitectónica: `dm_bve_baseline_mensual` sigue siendo un apoyo promocional y no el PDVB, porque sus `registros` no representan días servibles.

## Scope CD 41 después de la actualización

El universo aprobado permanece sin cambios en la fotografía validada:

- 2.915 artículos comprables en el local 41;
- 59.512 pares distribuibles;
- 2.237 artículos efectivamente ruteados;
- 49 sucursales destino.

## Pendiente de observabilidad

`datamart.dm_bve_proceso_log` no incorporó la ejecución recién finalizada: su último proceso productivo registrado continúa siendo el 2026-05-25. Esto no invalida los datos reconciliados, pero impide demostrar por log qué ejecución los produjo.

Antes de automatizar el consumo diario se debe asegurar que todo camino de actualización —procedimiento, script o ejecución manual— registre:

- rango procesado;
- inicio y fin;
- estado;
- conteos de baseline, enriquecidas y promociones;
- checksum o totales de control;
- error, si corresponde.

