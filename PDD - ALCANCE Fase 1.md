# Planificación Diaria de Necesidades de Distribución — Alcance Fase 1

Versión: **1.1 integrada**
Fecha: **2026-07-28**
Estado: **Alcance rector para construcción**
Horizonte de entrega: **40 días desde el inicio**

---

## 1. Objetivo

Entregar una primera capacidad útil para calcular, priorizar y seguir diariamente las necesidades de abastecimiento de las sucursales, sin construir todavía la gestión logística de la distribución.

En esta fase:

- **Connexa** calcula el stock neto de sucursal, genera y consolida necesidades DECAS, las prioriza y mantiene el backlog.
- **Valkimia** consulta/importa oportunísticamente las líneas que decide procesar según stock y capacidad operativa.
- **Connexa** recibe el resultado real de preparación y despacho, conserva la trazabilidad y recalcula el saldo al día siguiente.

> Una necesidad expresa deuda de abastecimiento. No constituye una orden de distribución, una reserva de stock, un viaje ni un plan de carga.

## 2. Límite explícito

No forman parte de la Fase 1:

- gestión de la distribución;
- asignación o prorrateo de stock entre sucursales;
- reserva de stock;
- transferencias intersucursal como circuito gestionado;
- planificación de vehículos, viajes, rutas o ventanas;
- cubicaje, armado u optimización de carga de camiones;
- optimización intradía;
- ejecución de picking, carga, despacho o recepción;
- migración obligatoria a Valkimia WEB.

Los pesos, volúmenes, bultos y pallets se utilizan únicamente como **datos informativos y filtros** para que el operador de Valkimia seleccione. Connexa no decide cómo completar un camión.

## 3. Stock Neto Sucursal

Para cada fecha operativa, sucursal y artículo:

```text
Stock Neto Sucursal =
  Stock físico al cierre del día anterior
  + Ingresos pendientes confirmados
  - Stock comprometido
```

Ingresos pendientes confirmados:

- entregas directas de órdenes de compra;
- mercadería en tránsito desde Base 2/CD.

Stock comprometido:

- ventas especiales confirmadas;
- transferencias ya confirmadas y pendientes de envío.

Las transferencias se leen como dato de pipeline existente; Connexa no administra su ciclo logístico en esta fase.

Cada componente debe conservar fuente, fecha/hora de corte y cantidad para que el cálculo sea explicable.

## 4. Parámetros y cálculos

La base de cálculo es el **Promedio Diario de Venta Basal (PDVB)**. Los parámetros se versionan por artículo–sucursal o por el nivel de herencia que se acuerde:

- `Lead Time`: días desde Base 2/CD hasta la sucursal;
- `Días Stock`: cobertura objetivo;
- `Días Sobre Stock`: pulmón adicional permitido.

Cálculos:

```text
Stock Crítico = PDVB × Lead Time
Stock Mínimo  = PDVB × 2 × Lead Time
Stock Máximo  = PDVB × Días Stock
Sobre Stock   = PDVB × Días Sobre Stock
```

Reglas de borde:

- cantidades negativas se normalizan a cero donde corresponda;
- si `PDVB = 0`, no se genera NDD-D ni NDD-S automática y se informa la condición;
- parámetros faltantes o inválidos impiden calcular la línea y generan una alerta;
- toda corrida conserva la versión de fórmula y parámetros utilizados.

## 5. Necesidades DECAS

### 5.1 Automáticas

**NDD-D — Demanda (obligatoria)**

```text
NDD-D = max((PDVB × Días Stock) - Stock Neto Sucursal, 0)
```

La fórmula original recibida contenía un signo `+`; se corrige a `-` porque el texto acordado indica “menos el stock neto” y porque sumar stock incrementaría incorrectamente la necesidad. Esta corrección debe ratificarse con el responsable funcional antes de cerrar UAT.

**NDD-S — Sobre-stock (opcional)**

```text
NDD-S = max((Stock Máximo + Sobre Stock) - max(Stock Neto Sucursal, 0), 0) - NDD-D
NDD-S = max(NDD-S, 0)
```

Representa únicamente el tramo adicional sobre NDD-D que la sucursal podría almacenar. Es una oportunidad informativa; no habilita optimización de carga en Connexa.

### 5.2 Dirigidas y persistentes

- **NDD-E — Venta especial (obligatoria):** negocio especial, licitación o venta con fecha/SLA comprometido.
- **NDD-C — Campaña (obligatoria):** acción comercial con vigencia y cantidades definidas por el área comercial.
- **NDD-A — Acopio (opcional):** necesidad puntual por negociación, capacidad comercial y almacenamiento.

Las necesidades dirigidas tienen ID estable, vigencia, cantidad original, saldo, responsable, estado y auditoría. No se recrean en cada corrida ni se eliminan por falta de stock.

## 6. Índice de Riesgo de Quiebre (IRQ)

El IRQ se expresa entre 0 y 100; un valor mayor implica mayor urgencia. Para Fase 1 se implementará como regla versionada y explicable:

| Situación de la línea | IRQ inicial |
| --- | ---: |
| Stock neto menor o igual a cero | 100 |
| Cobertura mayor a 0 y menor a 1 Lead Time | 90 |
| Cobertura entre 1 Lead Time y Stock Mínimo | 50 |
| Cobertura mayor al mínimo y menor al máximo | 25 |
| Cobertura igual o mayor al máximo | 0 |

La prioridad final ordena primero compromisos E/C vencidos o próximos y luego IRQ, antigüedad y fecha objetivo. Los umbrales podrán parametrizarse sin cambiar la identidad de la necesidad.

## 7. Backlog consolidado

Se recalcula diariamente por:

```text
fecha operativa + Base 2/CD + sucursal + artículo + proveedor
```

Debe preservar el aporte y saldo de cada origen DECAS:

- **D, E y C:** obligatorios;
- **A y S:** opcionales.

Reglas:

- la foto D/S se reemplaza en cada corrida; no se acumula ciegamente;
- E/C/A permanecen hasta cumplimiento, vencimiento o cancelación autorizada;
- importar una línea en Valkimia no la elimina;
- solo una cantidad efectivamente informada como preparada/despachada reduce su saldo;
- un remanente vuelve a participar en el siguiente ciclo sin duplicarse;
- toda línea expone ID Connexa, tipo DECAS, prioridad, IRQ, fechas, cantidades y trazabilidad.

## 8. Stock y cobertura de Base 2

Connexa mostrará:

- demanda consolidada del CD;
- stock físico de referencia;
- ingresos pendientes de órdenes de compra, clasificados en on-time y vencidos;
- índice de cobertura;
- backlog obligatorio y opcional;
- antigüedad, criticidad y fechas comprometidas;
- unidades, bultos, pallets, peso y volumen cuando los maestros lo permitan.

El stock de Base 2 es informativo en Fase 1. No representa una reserva ni habilita a Connexa a asignar mercadería.

## 9. Ejecución oportunista en Valkimia

1. Valkimia consulta/importa desde Connexa líneas abiertas y priorizadas.
2. El operador puede filtrar por sucursal, prioridad, IRQ, DECAS, proveedor, peso, volumen, bultos o pallets.
3. Antes de confirmar, visualiza totales estimados y el carácter obligatorio u opcional.
4. Valkimia selecciona según intención, stock disponible y capacidad operativa.
5. Cada línea importada conserva el ID Connexa y una referencia idempotente.
6. Valkimia informa cantidades efectivamente preparadas y, si están disponibles, documento, remito, despacho, tránsito y entrega estimada.
7. Connexa registra eventos por línea y descuenta solo cantidades confirmadas.
8. Una selección/importación no satisfecha permanece en backlog.

Connexa no arma lotes logísticos, no propone viajes y no optimiza cargas.

## 10. Cierre y nuevo ciclo

Al cierre:

1. se consolidan movimientos y eventos recibidos;
2. se controla la integridad de preparados, despachos y referencias;
3. se actualiza el pipeline;
4. se toma la nueva foto de stock;
5. se ejecuta una nueva corrida;
6. se publica una única versión vigente del backlog.

El ciclo debe poder reejecutarse de forma idempotente y auditable.

## 11. Entregable verificable a 40 días

La entrega se considera útil cuando:

- calcula Stock Neto Sucursal y NDD-D/NDD-S con explicación por línea;
- permite crear, editar y cerrar NDD-E/NDD-C/NDD-A;
- consolida y prioriza DECAS con IRQ;
- muestra stock/cobertura de Base 2 y unidades logísticas informativas;
- permite a Valkimia consultar/importar líneas sin duplicarlas;
- recibe preparación parcial o total por línea;
- mantiene correctamente el remanente y el tránsito;
- ofrece panel operativo, alertas, auditoría y monitor de integración;
- demuestra el ciclo completo con datos acordados en UAT;
- no contiene funciones de gestión u optimización logística excluidas.

## 12. Supuestos que no bloquean el inicio

- Se usa “Base 2” como CD origen inicial; el modelo admite más CD sin ampliar el MVP.
- El plazo se planifica como Día 1 a Día 40; el calendario exacto debe fijarse en el kickoff.
- La fórmula NDD-D utiliza resta de stock neto.
- El IRQ inicial es escalonado según la tabla anterior.
- Peso, volumen, bultos y pallets dependen de calidad de maestros y pueden mostrar “sin dato”.
- El contrato técnico definitivo con Valkimia se cierra mediante pruebas tempranas; el dominio no depende de un endpoint particular.

