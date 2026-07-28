# Necesidades de Distribución — Visión y Plan Fase 1

Versión: **2.1**
Fecha: **2026-07-28**
Estado: **Alineado al alcance acordado**

---

## 1. Resumen ejecutivo

DIARCO implementará en 40 días una primera capacidad útil de **planificación diaria de necesidades de distribución**.

Connexa:

- calcula la posición de cada artículo–sucursal;
- genera necesidades D/S y registra E/C/A;
- prioriza y conserva el backlog;
- muestra cobertura de Base 2;
- ofrece las líneas para consulta/importación desde Valkimia;
- registra lo efectivamente preparado y recalcula el remanente.

Valkimia continúa ejecutando oportunísticamente según stock y capacidad operativa. En esta fase Connexa no administra la distribución ni decide cargas, vehículos, viajes o rutas.

## 2. Decisión operativa

```text
Connexa calcula y prioriza necesidades
                 |
                 v
Valkimia consulta y selecciona qué importar
                 |
                 v
Valkimia informa qué preparó/despachó
                 |
                 v
Connexa mantiene saldo, tránsito y nueva foto diaria
```

La importación no equivale a cumplimiento. Solo el resultado efectivo reduce el saldo.

## 3. Principios

1. **Necesidad no es orden logística.**
2. **La posición se recalcula diariamente.**
3. **DECAS conserva su composición.**
4. **D/E/C son obligatorias; A/S son opcionales.**
5. **La prioridad informa urgencia; no asigna stock.**
6. **Valkimia selecciona oportunísticamente.**
7. **Toda cantidad se traza por línea e ID Connexa.**
8. **El remanente nunca desaparece por una importación parcial.**
9. **Peso, volumen, bultos y pallets son informativos.**
10. **El dominio se desacopla de la versión de Valkimia.**

## 4. Alcance funcional

### 4.1 Foto y cálculo diario

- stock físico del cierre anterior;
- ingresos confirmados;
- compromisos confirmados;
- Stock Neto Sucursal;
- PDVB, lead time, días stock y sobre-stock;
- crítico, mínimo, máximo y cobertura;
- NDD-D, NDD-S e IRQ.

### 4.2 Necesidades dirigidas

- E: venta especial;
- C: campaña comercial;
- A: acopio.

Tienen identidad, vigencia, cantidad, saldo, responsable y auditoría.

### 4.3 Backlog DECAS

Consolidado por fecha, CD, sucursal, artículo y proveedor, con aporte D/E/C/A/S, obligatoriedad, IRQ, prioridad, fechas y unidades logísticas.

### 4.4 Base 2

Visión de demanda consolidada, stock físico, OC pendientes on-time/vencidas e índice de cobertura. No implica reserva ni asignación.

### 4.5 Valkimia

- consulta filtrable de líneas abiertas;
- selección/importación del operador;
- referencia idempotente;
- cantidades preparadas parciales o totales;
- documentos, despacho y tránsito cuando estén disponibles;
- reconciliación y alertas.

### 4.6 Panel

Posición por proveedor–sucursal–artículo, detalle explicable, excepciones, cobertura, pipeline, saldo, SLA, frescura y próxima acción.

## 5. Fuera de Fase 1

- gestión de distribución;
- asignación, reserva y prorrateo de stock;
- transferencias intersucursal gestionadas;
- planificación de capacidad;
- vehículos, viajes, rutas y ventanas;
- cubicaje y optimización de cargas;
- picking, carga, despacho o recepción administrados por Connexa;
- simulación y reoptimización intradía;
- migración obligatoria a Valkimia WEB.

Estas capacidades conforman un programa posterior y no condicionan la entrega de 40 días.

## 6. Arquitectura funcional

```text
Fuentes diarias y maestros
          |
          v
Snapshots + motor de cálculo versionado
          |
          +----> NDD-D / NDD-S
          +----> NDD-E / NDD-C / NDD-A
          |
          v
Backlog DECAS + IRQ + cobertura Base 2
          |
          v
Puerto estable de consulta/importación
          |
          v
Adaptador Valkimia actual o WEB futura
          |
          v
Eventos de preparación/despacho
          |
          v
Imputación + panel + nueva corrida
```

No existen componentes `Allocation`, `Reservation`, `Trip`, `Route`, `Vehicle` o `LoadOptimizer` en la Fase 1.

## 7. Plan de entrega

| Tramo | Resultado demostrable |
| --- | --- |
| D1–D5 | contratos, datos y decisiones críticas |
| D6–D14 | cálculo diario y explicación |
| D10–D18 | E/C/A y parámetros |
| D15–D24 | backlog, IRQ, Base 2 y panel |
| D20–D30 | integración oportunista Valkimia |
| D31–D35 | cierre, alertas, seguridad y rendimiento |
| D36–D38 | UAT |
| D39–D40 | salida y estabilización |

Se trabaja por verticales demostrables. El contrato con Valkimia y los datos reales se prueban en los primeros cinco días.

## 8. Indicadores de éxito

- porcentaje de líneas calculadas sin error;
- frescura de fuentes;
- backlog D/E/C y A/S por antigüedad;
- líneas con IRQ crítico;
- tasa de importaciones idempotentes;
- diferencia importado–preparado;
- preparación parcial y remanente correctamente conservado;
- compromisos E/C dentro de SLA;
- porcentaje de líneas con trazabilidad completa;
- tiempo del comprador para identificar las prioridades del día.

No se utilizarán como KPI de esta fase ocupación de camiones, kilómetros, cubicaje o calidad de rutas.

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| Fórmula o parámetros ambiguos | Ratificación en D1–D5 y versión de fórmula |
| Fuentes incompletas | Controles de frescura y bloqueo por ámbito |
| Duplicación en Valkimia | ID Connexa, versión e idempotencia |
| Importado se confunde con cumplido | Estados y cantidades separados |
| Preparación parcial borra saldo | Imputación por línea y prueba de conservación |
| Estados Valkimia ambiguos | Valor original, mapping versionado y `UNKNOWN` |
| Datos logísticos faltantes | Mostrar “sin dato”; no bloquear necesidad |
| Expansión hacia logística | exclusiones y backlog Fase 2 separados |
| Plazo de 40 días | verticales pequeñas, UAT temprana y corte de alcance |

## 10. Resultado esperado

Al finalizar, DIARCO dispondrá de una foto diaria confiable y explicable de qué necesita cada sucursal, con qué urgencia, qué parte tomó Valkimia, qué preparó y qué sigue pendiente. La organización obtiene utilidad operativa sin esperar ni anticipar la futura Gestión de la Distribución.

