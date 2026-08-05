# ADR-002 — Esquema operativo de planificación de distribución

Fecha: **2026-08-05**  
Estado: **Aprobado**

## Decisión

Todos los objetos operativos de planificación de la distribución en Connexa se
alojarán en:

```text
connexa_platform_ms.stock_management
```

No se creará el esquema `pdd` en `connexa_platform_ms`.

PDD continúa siendo el nombre funcional del proyecto y el prefijo de las
entidades analíticas. Por lo tanto, permanecen sin cambios:

```text
diarco_data.datamart.dm_pdd_stock_diario
diarco_data.datamart.dm_pdd_venta_diaria
diarco_data.datamart.dm_pdd_pdvb_estimate_detail
diarco_data.datamart.dm_pdd_pdvb_backtest_detail
```

## Alcance

La decisión comprende las entidades operativas de:

- configuración y modelos;
- scope distribuible CD41;
- corridas y snapshots de fuentes;
- publicación y proyección PDVB;
- posiciones de stock;
- necesidades DECAS;
- backlog;
- integración y ejecución Valkimia;
- mensajería y auditoría.

## Consecuencias

1. Los DDL operativos califican todas las tablas y FK con
   `stock_management`.
2. Las migraciones deben incorporarse al historial Flyway ya existente del
   esquema `stock_management`.
3. No es necesario migrar objetos: al aprobar esta decisión, el esquema `pdd`
   no existía en `connexa_platform_ms`.
4. Los UUID de scope y modelo se conservan porque la ubicación física no cambia
   la membresía, los parámetros ni la implementación analítica.
5. Las referencias cross-database desde `diarco_data` apuntan lógicamente a
   `connexa_platform_ms.stock_management` y continúan sin FK física.

## No decidido por este ADR

Este cambio no renombra el proyecto PDD ni las tablas `dm_pdd_*`. Tampoco cambia
los nombres de las tablas operativas, sus fórmulas o estados. Una eventual
adopción de prefijos adicionales para las tablas de `stock_management` requiere
una decisión separada antes de convertir los DDL en migraciones Flyway.
