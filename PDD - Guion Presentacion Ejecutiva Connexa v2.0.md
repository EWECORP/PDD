# Guion de Presentación Ejecutiva — Fase 1 en 40 días

Versión: **2.1**
Fecha: **2026-07-28**

---

## Mensaje central

> En 40 días entregaremos una foto diaria, priorizada y trazable de las necesidades de las sucursales. Connexa mantendrá el backlog; Valkimia elegirá qué puede ejecutar. La gestión y optimización logística quedan para una fase posterior.

## Diapositiva 1 — Objetivo

Título: **Funcionalidad útil en 40 días**

- cálculo diario;
- DECAS priorizado;
- ejecución oportunista Valkimia;
- saldo y trazabilidad.

## Diapositiva 2 — Problema

- no hay una deuda de abastecimiento única y explicable;
- las cantidades pendientes pueden perder visibilidad;
- necesidad, selección y ejecución se confunden;
- Compras necesita priorizar excepciones, no diseñar viajes.

## Diapositiva 3 — Corte de alcance

Dos columnas:

| Fase 1 | Después |
| --- | --- |
| Necesidades y backlog | Gestión de distribución |
| Stock/cobertura | Asignación y reservas |
| IRQ y prioridad | Prorrateo |
| Importación oportunista | Vehículos y viajes |
| Tracking por línea | Rutas, cubicaje y optimización |

Frase: **“Peso y volumen informan; Connexa no arma camiones.”**

## Diapositiva 4 — Ciclo diario

```text
Foto de datos
  -> Stock Neto Sucursal
  -> D/E/C/A/S + IRQ
  -> Backlog priorizado
  -> Valkimia consulta/importa
  -> Preparación real
  -> Remanente + nueva foto
```

## Diapositiva 5 — Stock Neto

```text
Stock físico
+ ingresos confirmados
- compromisos
= Stock Neto Sucursal
```

Mostrar fecha/hora y componentes explicables.

## Diapositiva 6 — DECAS

| Tipo | Descripción | Clase |
| --- | --- | --- |
| D | Demanda automática | Obligatoria |
| E | Venta especial | Obligatoria |
| C | Campaña | Obligatoria |
| A | Acopio | Opcional |
| S | Sobre-stock | Opcional |

## Diapositiva 7 — Riesgo y prioridad

- IRQ 100: quebrado;
- IRQ 90: cobertura menor a lead time;
- compromisos E/C vencidos primero;
- toda prioridad es explicable;
- priorizar no es asignar stock.

## Diapositiva 8 — Rol de Valkimia

Valkimia:

- filtra por sucursal, DECAS, prioridad, IRQ, peso o volumen;
- visualiza totales estimados;
- selecciona según stock y capacidad;
- importa con ID Connexa;
- informa lo efectivamente preparado.

## Diapositiva 9 — No se pierde el saldo

Ejemplo:

```text
Necesidad 100
Importado 80
Preparado 50
Saldo vigente 50
```

Mensaje: importar no borra; preparar imputa.

## Diapositiva 10 — Producto visible

- panel diario;
- stock y necesidades;
- detalle de fórmula;
- gestión E/C/A;
- backlog Valkimia;
- cobertura Base 2;
- ejecución, alertas y auditoría.

## Diapositiva 11 — Plan

| Días | Hito |
| --- | --- |
| 1–5 | datos, decisiones y contrato |
| 6–14 | cálculo |
| 10–18 | E/C/A |
| 15–24 | backlog, IRQ y panel |
| 20–30 | Valkimia |
| 31–35 | cierre y calidad |
| 36–38 | UAT |
| 39–40 | salida |

## Diapositiva 12 — Éxito

- cálculo reproducible;
- backlog sin duplicación;
- parcialidad correctamente conservada;
- compromisos visibles;
- trazabilidad punta a punta;
- cero funciones de gestión/optimización logística infiltradas.

## Diapositiva 13 — Decisiones inmediatas

- ratificar fórmulas y redondeos;
- confirmar fuentes;
- cerrar prioridad/imputación;
- certificar ID e integración Valkimia;
- fijar calendario, volumen y UAT.

## Diapositiva 14 — Cierre

> La Fase 1 no intenta resolver todo el transporte. Resuelve primero, y bien, qué se necesita, con qué urgencia, qué se ejecutó y qué sigue pendiente.

## Notas para presentación

- evitar imágenes de ruteo o algoritmos de carga;
- usar un ciclo diario y una tabla DECAS;
- etiquetar stock Base 2 como referencia;
- no afirmar que la versión WEB es precondición;
- no presentar transferencias intersucursal;
- usar “planificación de necesidades”, no “planificador logístico integral”.

