# Índice y Gobierno Documental — Planificación de Necesidades Connexa

Versión del paquete: **2.1**
Fecha de actualización: **2026-07-28**
Estado: **Base vigente para desarrollo Fase 1**

---

## 1. Decisión rectora

La entrega de 40 días implementa **Planificación Diaria de Necesidades de Distribución**, no Gestión de la Distribución.

Connexa calcula, clasifica, prioriza y conserva DECAS. Valkimia consulta/importa oportunísticamente y comunica la ejecución efectiva. Connexa mantiene el remanente y recalcula diariamente.

Quedan fuera asignación de stock, reservas, prorrateo, transferencias intersucursal gestionadas, vehículos, viajes, rutas, cubicaje y optimización de carga.

## 2. Precedencia

Ante una contradicción:

1. decisión aprobada y fechada posterior;
2. `PDD - ALCANCE Fase 1.md`;
3. Especificación de Requerimiento de Software v2.1;
4. Circuito Operativo v2.1;
5. Modelo de Datos e Integración v2.1;
6. Diseño de Pantallas v2.1;
7. Visión y Plan v2.1;
8. documentos de contexto y reuniones.

El signo normativo de NDD-D es resta de Stock Neto Sucursal. Su ratificación funcional forma parte de D1–D5.

## 3. Documentos normativos vigentes

| Documento | Propósito |
| --- | --- |
| `PDD - ALCANCE Fase 1.md` | Decisión funcional rectora, límites y entregable |
| `PDD - Especificacion de Requerimiento de Software Connexa v2.0.md` | Requerimientos, aceptación, pruebas y arranque |
| `PDD - Circuito Operativo de Necesidades de Distribucion Connexa v2.0.md` | Procedimiento diario y responsabilidades |
| `PDD - Modelo de Datos Conceptual Connexa v2.0.md` | Entidades, saldos y restricciones |
| `PDD - Integracion Valkimia por Adaptadores v2.0.md` | Contrato lógico oportunista e idempotencia |
| `PDD - Diseno de Pantallas Operativas Connexa v2.0.md` | MVP de pantallas y UX |
| `PDD - Vision Requerimiento y Plan Connexa v2.0.md` | Síntesis, arquitectura, plan y riesgos |
| `PDD - Guion Presentacion Ejecutiva Connexa v2.0.md` | Comunicación ejecutiva alineada |
| `PDD - Inicio de Desarrollo Fase 1.md` | Épicas, historias, secuencia, gates y UAT para kickoff |

Los nombres físicos v2.0 se conservan para evitar romper referencias existentes; su metadata interna identifica la revisión **2.1**.

## 4. Vocabulario obligatorio

| Término | Uso |
| --- | --- |
| Planificación de necesidades | Cálculo, prioridad, backlog y seguimiento |
| Gestión de distribución | Asignación, reservas, transporte y ejecución; fuera de Fase 1 |
| DECAS | D Demanda, E Especial, C Campaña, A Acopio, S Sobre-stock |
| Obligatorio | D/E/C visible hasta saldo cero; no obliga a Connexa a asignar stock |
| Opcional | A/S seleccionable según oportunidad |
| Importado | Seleccionado por Valkimia; no cumplido |
| Preparado | Cantidad efectiva informada por Valkimia |
| Stock Base 2 | Referencia informativa, no reserva |
| Backlog | Saldo vigente de necesidades |
| IRQ | Índice explicable de urgencia 0–100 |

No usar en Fase 1:

- “Connexa arma la distribución”;
- “Connexa completa camiones”;
- “orden optimizada”;
- “stock asignado/reservado”;
- “transferencia intersucursal” como capacidad del producto.

## 5. Control de cambios 2.1

- se incorporó el alcance acordado el 28/07/2026;
- se fijó un entregable útil en 40 días;
- se formalizó Stock Neto Sucursal;
- se formalizaron fórmulas D/S y reglas de borde;
- se adoptó DECAS y obligatoriedad D/E/C versus A/S;
- se definió IRQ inicial versionado;
- se cambió publicación Connexa por consulta/importación oportunista Valkimia;
- se separó importado de preparado;
- se eliminó transferencia intersucursal de Fase 1;
- se eliminaron gestión, capacidad, viajes, rutas y optimización;
- se redujo el modelo y las pantallas al MVP;
- se agregó orden de construcción, UAT y decisiones D1–D5.

## 6. Contexto no normativo

`Contexto/` y `Reuniones/` explican la evolución. No deben usarse para construir Fase 1 cuando incluyan:

- Connexa como asignador de stock;
- motor de prorrateo;
- planificador integral logístico;
- transferencias intersucursal;
- cubicaje, camiones, viajes o rutas;
- SND/API WEB como precondición;
- publicación automática decidida por Connexa.

Esas ideas podrán recuperarse en Fase 2 mediante nueva aprobación.

## 7. Gobierno de cambios durante los 40 días

Todo cambio se clasifica:

- **Aclaración:** no altera esfuerzo ni aceptación; se actualiza la especificación.
- **Corrección:** resuelve contradicción o defecto; requiere evidencia y regresión.
- **Cambio de alcance:** agrega actor, entidad, interfaz o capacidad; requiere decisión de producto y reemplazo equivalente.
- **Fase 2:** cualquier gestión/optimización logística; se registra fuera del backlog comprometido.

El equipo mantiene:

- log de decisiones/ADR;
- matriz requerimiento–historia–prueba;
- contrato Valkimia versionado;
- evidencia UAT;
- lista explícita de exclusiones.

## 8. Criterio para comenzar

El desarrollo puede iniciar con la SRS v2.1. Durante D1–D5 deben cerrarse fórmula/redondeo, fuentes, unidad, prioridad/imputación, contrato Valkimia, volumen, calendario y estados. Ninguna de esas definiciones habilita ampliar a Gestión de la Distribución.
