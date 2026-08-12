# Manifiestos PDD

## Versión vigente

`pdd_scope_model_v2.2.yaml` es la fuente de verdad vigente. Scope y modelo se
encuentran en `DRAFT`, habilitados para piloto y backtest:

```text
Scope v4: 90dcd987-2ad6-4e4e-8d19-2ead45775d1f
Model v3: a0a35b25-628d-43f1-b651-82c97207fc60
```

El scope v4 está congelado en `diarco_data.datamart`: 2.604 artículos CD,
2.017 artículos distribuidos, 51.586 pares y 49 destinos. Excluye rubro 13 con
subrubros 3818 (`INSUMOS`) y 3838 (`VARIOS`) por tratarse de consumo interno
sin ventas. Sus conteos persistidos coinciden con la cabecera sellada.

El backfill v4 del 12 de agosto fue validado con 84 dias, 4.333.224 features y
51.586 estimaciones. Los bloqueados bajaron de 13.115 a 7.911 (-39,68%) y los
controles de integridad resultaron en cero inconsistencias.

El scope v3 `b710f4d6-1bd8-4c32-8b1d-a3425c252cb9` queda como antecedente del
primer backfill y fue reemplazado por el scope v4 para las nuevas corridas.

El scope v2 `c18fb653-47c3-4554-9bf3-5e983ce31145` quedó rechazado y se conserva
en `Antecedentes/manifests`; no debe reutilizarse.

El modelo v2 `dc2b38a9-dc91-443c-9b25-fe89236a225b` quedó reemplazado después
del backfill fallido `386083d2-70fb-4584-b41b-2d36d3fd5b05`: el normalizador
intentaba construir `2026-06-31`. No se generaron estimaciones con esa versión.

## Política de cambio

- Una corrida nueva no cambia estos UUID.
- Si el checksum del scope no cambia, se reutiliza la versión de scope.
- Si cambia la membresía o el filtro, se crea una nueva versión de scope con
  otro UUID.
- Si cambia un parámetro o la implementación relevante, se crea una nueva
  versión de modelo con otro UUID.
- Nunca se modifica retroactivamente el manifiesto de una versión ya utilizada;
  se agrega una versión nueva.

## Reproducción de evidencia

Desde `E:/ETL/PDD/backend`:

```bash
python -m tools.snapshot_manifest_inputs
```

El comando vuelve a calcular conteos, checksums de scope y hashes de archivos.
Una diferencia no actualiza automáticamente el manifiesto: obliga a revisar si
corresponde emitir una nueva versión.

## Uso en runtime

`pdd_runtime_ids_v4.env.example` contiene las identidades que deben incorporarse
al entorno de Prefect antes de reprocesar el piloto.
