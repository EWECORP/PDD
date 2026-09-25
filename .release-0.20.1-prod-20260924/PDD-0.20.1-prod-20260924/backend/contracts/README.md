# Contratos PDD para frontend

- `pdd-frontend-openapi-v1.yaml`: contrato HTTP fuente para frontend y backend
  Java Stock Management. El backend Python no implementa esta API.
- `pdd-planning-openapi-v1.yaml`: extensión contract-first para selección de
  backlog, planes, viajes, cubicaje, publicación y seguimiento Valkimia. Su
  runtime productivo también es Java; Python/Prefect permanece analítico.
- `examples/dashboard-summary.json`: resumen sintético que conserva los totales
  DECAS y de frescura de la foto Test validada. Los nombres, cantidad de
  proveedores e indicador IRQ son ilustrativos hasta que el adaptador API
  implemente sus consultas definitivas.
- `examples/backlog-page.json`: página sintética con D, S y datos incompletos.
- `examples/backlog-detail.json`: detalle sintético con fuentes atribuidas.
- `examples/directed-need.json`: E activa sintética para desarrollar el flujo E/C/A.
- `examples/problem-details.json`: conflictos y validaciones esperadas.
- `examples/planning-backlog-page.json`: saldo planificable con compromisos.
- `examples/dispatch-plan.json`: plan borrador, viaje, parada y cubicaje.
- `examples/valkimia-import-detail.json`: ejecución parcial reconciliada.
- `sql/frontend_reference_queries.sql`: consultas de referencia para implementar
  el adaptador; no son consultas a ejecutar desde el navegador.

Los ejemplos son mocks y no deben cargarse en la base. Para evitar acoplamiento,
el frontend consume exclusivamente el contrato HTTP y nunca nombres de tablas o
IDs bigint internos.

El OpenAPI puede importarse en Swagger UI, Postman o un servidor de mocks
compatible con OpenAPI 3.1.

El contrato de planificación no presupone que Valkimia exponga una API. El
backend implementa un puerto de ejecución y el primer adaptador puede escribir
y consultar la tabla legacy, conservando los mismos UUID, estados e
idempotencia del contrato.

Validación local:

```bash
python tools/validate_frontend_contract.py
```

Servidor mock sin dependencias adicionales:

```bash
python tools/run_frontend_mock.py --port 4010
```

Base URL: `http://127.0.0.1:4010/connexa/api/v1/pdd`. El header de respuesta
`X-PDD-Mock: true` evita confundirlo con un servicio real. Los filtros del
listado se aceptan pero se ignoran en el mock estático.
