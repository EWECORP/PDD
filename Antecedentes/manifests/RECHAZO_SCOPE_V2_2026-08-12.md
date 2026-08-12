# Rechazo técnico del scope v2

- UUID: `c18fb653-47c3-4554-9bf3-5e983ce31145`
- Estado final: `REJECTED`
- Manifiesto: `pdd_scope_model_v1.3.yaml`
- Conteo manifestado: 58.137 pares y 2.204 artículos distribuidos.
- Conteo materializado en el piloto del 2026-08-11: 58.092 pares y 2.203
  artículos distribuidos.
- Nuevo snapshot vivo posterior: 58.092 pares y 2.203 artículos distribuidos.

La fuente `src.base_productos_vigentes` cambió durante el día 2026-08-12. El
backend consultaba la membresía viva en cada proceso, por lo que el UUID no
representaba una fotografía reproducible. Los datos del piloto no se admiten
como evidencia de backtest y deberán reprocesarse después de capturar un scope
congelado.
