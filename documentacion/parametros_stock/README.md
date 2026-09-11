# Par?metros de stock de CONNEXA

Fecha: 2026-09-11. Estado: **relevamiento de TEST completado, propuesta actualizada; sin cambios en base de datos**.

La conexi?n con las credenciales actualizadas permiti? consultar `connexa_platform_test` (PostgreSQL 14.24) en modo de solo lectura.

## Documentos

- [06_implementacion_borrador_test.md](06_implementacion_borrador_test.md): migración y carga real aplicadas como DRAFT, exclusiones por cierre y comparación con stock. Actualiza el estado posterior a los relevamientos de solo lectura.
- [05_combinaciones_conflictivas.md](05_combinaciones_conflictivas.md): las 23 claves grupo/categoría con sus valores diferentes; IDs y timestamps en `conflictos_test.json`.
- [03_relevamiento_test.md](03_relevamiento_test.md): informe principal con la estructura real, conteos, problemas detectados y recomendaci?n revisada.
- [04_diccionario_catalogo.md](04_diccionario_catalogo.md): diccionario de 1047 objetos con columnas, claves, relaciones e ?ndices; incluye particiones y tablas externas.
- [catalogo_pgp_test.json](catalogo_pgp_test.json): evidencia estructurada de cat?logo y verificaciones agregadas.
- [02_propuesta_politicas_stock.md](02_propuesta_politicas_stock.md): propuesta l?gica de reglas por local/perfil y clasificaci?n. La recomendaci?n de esquema preliminar queda reemplazada por el informe 03.
- [01_relevamiento_repositorio.md](01_relevamiento_repositorio.md): antecedentes en c?digo y DDL, documentados antes de acceder a TEST.
- [relevar_base.py](relevar_base.py): extractor reproducible de cat?logo y controles agregados en transacciones de solo lectura.

## Resultado principal

`supply_planning` ya contiene 14 grupos, 100 locales asignados y 141 reglas de d?as de stock por grupo/categor?a. Es el candidato recomendado para ampliar las pol?ticas. Hay 23 combinaciones grupo/categor?a con valores diferentes que deben resolverse funcionalmente. El campo `stock_days_limit` est? en cero y su equivalencia con sobrestock no est? demostrada.

Las tablas de reposici?n por producto/local y clasificaciones de `inventory` existen pero est?n vac?as. PDD sigue leyendo los d?as del legado hasta que se modifique su integraci?n.

## Reproducci?n y alcance

Desde la ra?z del proyecto:

```powershell
PDD/backend/.venv/Scripts/python.exe PDD/documentacion/parametros_stock/relevar_base.py
```

Lee exclusivamente `PGP_TEST_*` de `PDD/backend/.env`, sin publicar credenciales. El script actualiza el JSON; el diccionario Markdown corresponde a la captura documentada. Los conteos de cat?logo son estimaciones; los de calidad espec?ficos son exactos al momento de consulta. Las consultas se ejecutan bajo una misma conexi?n de lectura, sin exigir una fotograf?a transaccional repetible entre sentencias.

El inventario refleja los permisos del usuario. No se leyeron filas de tablas externas ni datos personales de negocio. No se modificaron estructuras ni reglas. Las definiciones y defaults del cat?logo deben revisarse antes de compartir el JSON fuera del proyecto.

El primer intento fall? por autenticaci?n; el problema qued? resuelto al actualizar las credenciales. La siguiente etapa es confirmar la sem?ntica y los consumidores de las reglas para preparar una implementaci?n compatible.
