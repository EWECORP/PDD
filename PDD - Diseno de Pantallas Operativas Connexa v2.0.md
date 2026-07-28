# Diseño de Pantallas Operativas — Fase 1

Versión: **2.1**
Fecha: **2026-07-28**
Estado: **Alcance UX para construcción**

---

## 1. Objetivo

Permitir que Compras entienda qué necesita cada sucursal y por qué, gestione E/C/A y siga lo que Valkimia importó y preparó. Las pantallas no administran distribución, viajes ni cargas.

## 2. Principios UX

- mostrar siempre fecha y frescura;
- distinguir necesidad, importado y preparado;
- mantener visibles D/E/C obligatorias y A/S opcionales;
- explicar fórmula, IRQ y saldo;
- priorizar excepciones y compromisos;
- no presentar stock Base 2 como reservado;
- usar unidades logísticas solo como estimación;
- ocultar de Fase 1 toda acción de vehículos, viajes, rutas o carga.

## 3. Roles y navegación

```text
Inicio
  +-- Panel diario
  +-- Stock y necesidades
  +-- Excepciones E/C/A
  +-- Backlog para Valkimia
  +-- Ejecución Valkimia
  +-- Alertas
  +-- Administración
        +-- Corridas y fuentes
        +-- Parámetros
        +-- Monitor
        +-- Auditoría
```

## 4. Pantalla 1 — Panel diario

Pregunta: **¿Qué requiere atención hoy?**

```text
+--------------------------------------------------------------------------------+
| Necesidades de Distribución                 Foto: 28/07 06:10   [Datos frescos] |
+--------------------------------------------------------------------------------+
| IRQ 100 | E/C vencidas | Parciales | Sin avance | Datos faltantes              |
|   128   |      19      |    34     |     11     |        7                     |
+--------------------------------------------------------------------------------+
| Filtros: Comprador | Proveedor | Sucursal | DECAS | Oblig./Opc. | SLA          |
+--------------------------------------------------------------------------------+
| Pri | IRQ | Prov | Suc | Artículo | D | E | C | A | S | Preparado | Saldo     |
+--------------------------------------------------------------------------------+
```

Acciones:

- abrir posición;
- crear E/C/A;
- reconocer/escalar alerta;
- guardar filtro;
- exportar vista autorizada.

No incluye “solicitar rebalanceo”, “armar carga” ni “crear viaje”.

## 5. Pantalla 2 — Stock y necesidades

Pregunta: **¿Cuál es la posición completa por proveedor–sucursal–artículo?**

Columnas mínimas:

- proveedor, sucursal, artículo;
- stock físico, ingresos, compromisos y stock neto;
- PDVB, lead time y cobertura;
- crítico, mínimo, máximo;
- D/E/C/A/S;
- obligatoriedad;
- IRQ y prioridad;
- Base 2 físico, OC on-time/vencidas y cobertura;
- importado, preparado, despacho/tránsito;
- saldo, fecha objetivo, SLA;
- frescura y alertas;
- bultos, pallets, kg y volumen estimados.

Reglas visuales:

- rojo: IRQ 90/100 o SLA vencido;
- ámbar: IRQ 50, parcial o dato próximo a vencer;
- azul: importado/en proceso;
- verde: preparado/cubierto con evidencia;
- gris: opcional o dato logístico ausente;
- etiqueta permanente: “Stock Base 2 informativo; no reservado”.

## 6. Pantalla 3 — Detalle artículo–sucursal

Pregunta: **¿Cómo se calculó y qué ocurrió con la línea?**

```text
+----------------------------------------------------------------------------+
| Sucursal 041 / Artículo 1234                         IRQ 90 / Obligatoria    |
+----------------------------------------------------------------------------+
| Físico 20 + Ingresos 15 - Compromisos 5 = Stock Neto 30                    |
| PDVB 10 | LT 2 | Máximo 70 | D 40 | S 20                                   |
+----------------------------------------------------------------------------+
| E 10 | C 0 | A 0 | Total abierto 70 | Preparado 25 | Saldo 45              |
+----------------------------------------------------------------------------+
| Base 2: físico 300 | OC on-time 100 | vencidas 20 | actualizado 05:55      |
+----------------------------------------------------------------------------+
| Fuentes | Fórmula | Excepciones | Importaciones | Ejecución | Timeline      |
+----------------------------------------------------------------------------+
```

Debe mostrar:

- versión de corrida y fórmula;
- valores fuente;
- composición DECAS;
- regla de prioridad/IRQ;
- imputación de cantidades preparadas;
- IDs Connexa y Valkimia;
- historial append-only.

## 7. Pantallas 4–6 — E, C y A

### NDD-E — Venta especial

Campos: sucursal, artículo, cantidad, fecha/SLA, cliente/referencia, prioridad, responsable, observación y evidencia.

### NDD-C — Campaña

Campos: campaña, proveedor, vigencia, artículos, sucursales, cantidades, fechas objetivo y responsable. Debe soportar carga masiva controlada.

### NDD-A — Acopio

Campos: sucursal, artículo, cantidad, motivo, vigencia, fecha requerida y responsable.

Comportamiento común:

- mostrar posición e impacto;
- advertir posibles duplicados;
- guardar borrador;
- activar/aprobar según permiso;
- versionar cambios;
- cancelar/cerrar con motivo;
- mostrar cantidad original, imputada y saldo.

## 8. Pantalla 7 — Excepciones DECAS dirigidas

Listado filtrable por tipo, referencia, proveedor, sucursal, artículo, responsable, vigencia, SLA, estado y posible duplicado.

Columnas: ID, tipo, cantidad original, preparada, cancelada, saldo, prioridad, fechas, estado y última modificación.

## 9. Pantalla 8 — Backlog para Valkimia

Pregunta: **¿Qué líneas están disponibles para selección?**

```text
+--------------------------------------------------------------------------------+
| Backlog vigente — Foto 2026-07-28 / versión 07                                 |
+--------------------------------------------------------------------------------+
| Filtros: CD | Suc | Prov | DECAS | Oblig./Opc. | IRQ | Peso | Vol. | Pallets  |
+--------------------------------------------------------------------------------+
| ID | Tipo | O/O | IRQ | Suc | Art | Saldo | Kg | m3 | Pallets | Fecha/SLA      |
+--------------------------------------------------------------------------------+
| Totales visibles: líneas, unidades, bultos, pallets, kg, volumen               |
+--------------------------------------------------------------------------------+
```

Para usuarios Connexa es de consulta. La selección operativa ocurre en Valkimia. No se incluye botón “optimizar”, “completar camión” o “crear viaje”.

## 10. Pantalla 9 — Ejecución Valkimia

Debe distinguir:

- disponible;
- importado;
- preparado;
- despachado/tránsito si hay evidencia;
- remanente.

Filtros: referencia Connexa/Valkimia, estado, sucursal, artículo, fecha, parcialidad, sin avance y error.

El detalle muestra eventos originales, normalización, cantidades, timestamps, imputación DECAS y reintentos técnicos.

## 11. Pantalla 10 — Stock y cobertura Base 2

Pregunta: **¿Cómo se relaciona la demanda consolidada con la disponibilidad informada del CD?**

Incluye:

- D/E/C obligatorias;
- A/S opcionales;
- stock físico;
- OC pendientes on-time/vencidas;
- índice de cobertura;
- antigüedad y criticidad;
- unidades logísticas estimadas.

Incluye un aviso: **“Vista informativa. No asigna ni reserva stock.”**

## 12. Pantalla 11 — Alertas

Grupos:

- abastecimiento: IRQ, cobertura y quiebre;
- comercial: E/C vencida o próxima;
- datos: fuente o parámetro inválido;
- ejecución: parcial o sin avance;
- integración: timeout, duplicado, estado desconocido;
- control: cantidad inconsistente o evento pendiente.

Cada alerta tiene severidad, entidad, responsable, SLA de atención, estado, recomendación y comentarios.

## 13. Pantalla 12 — Corridas y fuentes

Muestra fecha, fórmula, estado, versión vigente, fuentes, frescura, conteos, rechazados, totales DECAS y errores.

Acciones autorizadas:

- ver diferencias;
- descargar rechazados;
- reejecutar ámbito;
- promover corrida válida;
- conservar la anterior si falla.

## 14. Pantalla 13 — Parámetros

Secciones:

- PDVB y fuente;
- lead time, días stock y sobre-stock;
- redondeos;
- umbrales IRQ;
- prioridad e imputación;
- frescura;
- unidades logísticas;
- mapping Valkimia;
- polling y alertas.

Todo cambio requiere vigencia, motivo, versión y permiso.

## 15. Pantalla 14 — Monitor y auditoría

Monitor:

- ingestas;
- corrida;
- consulta/importación Valkimia;
- eventos de ejecución;
- cola y reintentos;
- referencias ambiguas;
- estados desconocidos;
- latencia y frescura.

Auditoría: búsqueda por fecha, sucursal, artículo, proveedor, DECAS, ID Connexa/Valkimia, corrida, usuario y evento.

## 16. MVP Día 1–40

Imprescindibles:

1. Panel diario.
2. Stock y necesidades.
3. Detalle explicable.
4. Formularios y listado E/C/A.
5. Backlog para Valkimia.
6. Ejecución Valkimia.
7. Cobertura Base 2.
8. Alertas.
9. Corridas/fuentes.
10. Parámetros básicos.
11. Monitor/auditoría.

Postergar:

- personalización avanzada;
- analítica histórica compleja;
- notificaciones multicanal;
- importadores comerciales no esenciales.

Reservar para Fase 2:

- transferencias intersucursal;
- asignación y fair share;
- reservas;
- capacidad, vehículos y viajes;
- rutas, cubicaje y optimización.

## 17. Criterios de aceptación UX

- Compras identifica las cinco prioridades en menos de dos minutos.
- El cálculo y el IRQ de una línea son explicables sin consultar base de datos.
- D/E/C se distinguen de A/S.
- “Importado” nunca aparece como “cumplido”.
- Una preparación parcial muestra preparado, imputación y saldo.
- Todas las cantidades muestran unidad y timestamp.
- Base 2 se identifica como información no reservada.
- Datos logísticos faltantes se muestran sin ocultar la línea.
- No existe ninguna acción de gestión u optimización logística.

