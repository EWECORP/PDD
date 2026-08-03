# Manifiestos PDD

## Versión vigente

`pdd_scope_model_v1.yaml` es la fuente de verdad para las primeras identidades
lógicas del scope CD41 y del modelo PDVB.

Identidades:

```text
Scope v1: 96a3775e-de50-4bac-919f-95132ad195d9
Model v1: 4bf8d74b-a3da-4385-af02-dccbbc055548
```

El scope está funcionalmente aprobado porque el filtro fue confirmado. El
identificador corporativo del aprobador queda pendiente antes de persistir el
estado `APPROVED` en `connexa_platform_ms`.

El modelo está en `DRAFT`: puede utilizarse para backfill y backtest, pero no
debe publicarse como modelo operativo aprobado hasta superar los gates del
manifiesto.

## Política de cambio

- Una corrida nueva no cambia estos UUID.
- Si el checksum del scope no cambia, se reutiliza la versión de scope.
- Si cambia la membresía o el filtro, se crea scope v2 con otro UUID.
- Si cambia un parámetro o la implementación relevante, se crea model v2 con
  otro UUID.
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

`pdd_runtime_ids_v1.env.example` contiene las dos variables no secretas que
deben incorporarse al entorno del deployment Prefect.
