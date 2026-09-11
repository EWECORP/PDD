# Combinaciones conflictivas de stock en TEST

Captura UTC: 2026-09-11T12:39:10.699316+00:00. Consulta de solo lectura en `connexa_platform_test`.

Conflicto: una misma clave grupo/categoría tiene más de un par distinto `(stock_days, stock_days_limit)`. No se modificó ninguna regla.

| Grupo | Código categoría | Categoría | Días de stock distintos | Límites distintos | Filas |
|---|---|---|---|---|---:|
| AMBA-M | 10 | NON FOOD                       | 25, 30, 40, 45, 50 | 0 | 10 |
| CENTRO-M | 10 | NON FOOD                       | 30, 35, 40, 45, 50, 55 | 0 | 12 |
| CENTRO-M | 2-2528 | Sector - Fiambreria Congelados | 18, 21, 23, 25, 30, 35 | 0 | 6 |
| CENTRO-P | 10 | NON FOOD                       | 40, 45, 55 | 0 | 6 |
| CENTRO-P | 2-2528 | Sector - Fiambreria Congelados | 18, 23, 30 | 0 | 3 |
| CUYO-M | 10 | NON FOOD                       | 40, 45, 55 | 0 | 6 |
| CUYO-M | 2-2528 | Sector - Fiambreria Congelados | 21, 25, 35 | 0 | 3 |
| LOG-C | 10 | NON FOOD                       | 25, 30, 40, 45 | 0 | 8 |
| LOG-C | 2-2528 | Sector - Fiambreria Congelados | 15, 20, 25 | 0 | 3 |
| NEA-M | 10 | NON FOOD                       | 35, 40, 45, 50, 55 | 0 | 10 |
| NEA-M | 2-2528 | Sector - Fiambreria Congelados | 18, 23, 30 | 0 | 3 |
| NEA-P | 10 | NON FOOD                       | 40, 45, 55 | 0 | 6 |
| NEA-P | 2-2528 | Sector - Fiambreria Congelados | 18, 23, 30 | 0 | 3 |
| NOA-M | 10 | NON FOOD                       | 30, 35, 40, 45, 50 | 0 | 10 |
| NOA-M | 2-2528 | Sector - Fiambreria Congelados | 18, 23, 30 | 0 | 3 |
| NOA-P | 10 | NON FOOD                       | 25, 30, 40, 45 | 0 | 8 |
| NOA-P | 2-2528 | Sector - Fiambreria Congelados | 15, 20, 25 | 0 | 3 |
| SUR-M | 10 | NON FOOD                       | 35, 40, 45, 50, 55, 60 | 0 | 12 |
| SUR-M | 2-2528 | Sector - Fiambreria Congelados | 21, 25, 35 | 0 | 3 |
| SUR-P | 10 | NON FOOD                       | 40, 45, 50, 55, 60 | 0 | 10 |
| SUR-P | 2-2528 | Sector - Fiambreria Congelados | 21, 25, 35 | 0 | 3 |
| TDF-M | 10 | NON FOOD                       | 55, 60, 65 | 0 | 6 |
| TDF-M | 2-2528 | Sector - Fiambreria Congelados | 25, 30, 40 | 0 | 3 |

Total: 23 combinaciones, 140 filas.

El límite no se interpreta como sobrestock: su semántica está pendiente de confirmar. Los IDs y timestamps de todas las filas se conservan en [conflictos_test.json](conflictos_test.json).

La consulta reproducible se encuentra en [detallar_conflictos.py](detallar_conflictos.py). No se infiere una regla ganadora a partir del timestamp.
