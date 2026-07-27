# Índice y gobierno documental — Planificación de la Distribución Connexa

Versión del paquete: **2.0**
Fecha de actualización: **2026-07-24**
Estado: **Base funcional para validación y estimación**

---

## 1. Decisión rectora

La primera entrega implementará en Connexa el **Módulo de Necesidades de Distribución** mediante un corte **Big‑Bang**, sin convivencia operativa ni doble carga con SGM.

Desde la fecha de salida:

- Connexa será el único sistema donde se originen, modifiquen y consulten nuevas necesidades de distribución.
- SGM no generará, publicará ni modificará necesidades o transferencias alcanzadas por el nuevo módulo.
- Los pendientes previos al corte se incorporarán una sola vez mediante un inventario inicial conciliado.
- Valkimia continuará decidiendo oportunísticamente qué cantidad puede preparar con el Stock Neto Disponible real.
- Connexa conservará la necesidad, el backlog y la visión integral del pipeline.

La migración a la nueva versión WEB de Valkimia, basada en APIs y webservices, se mantiene como dirección tecnológica, pero **no es una precondición para la Fase 1**.

---

## 2. Documentos normativos vigentes

| Documento | Propósito | Estado |
| --- | --- | --- |
| `PDD - Vision Requerimiento y Plan Connexa v2.0.md` | Visión, alcance, decisiones, fases, riesgos y resultados | Normativo |
| `PDD - Especificacion de Requerimiento de Software Connexa v2.0.md` | Requerimientos funcionales, datos, integraciones, calidad y aceptación | Normativo |
| `PDD - Circuito Operativo de Necesidades de Distribucion Connexa v2.0.md` | Operación diaria, excepciones de Compras, Valkimia y transferencias entre sucursales | Normativo |
| `PDD - Diseno de Pantallas Operativas Connexa v2.0.md` | Navegación, panel del comprador, formularios y torre de control | Normativo |
| `PDD - Modelo de Datos Conceptual Connexa v2.0.md` | Entidades, relaciones, saldos y límites del modelo | Normativo conceptual |
| `PDD - Integracion Valkimia por Adaptadores v2.0.md` | Contratos internos, capacidades actuales/futuras e idempotencia | Normativo lógico |
| `PDD - Infografia Proyecto Connexa.html` | Síntesis ejecutiva visual del modelo | Normativo |

En caso de contradicción, prevalece este orden:

1. Decisiones formalmente aprobadas con fecha posterior.
2. Especificación de Requerimiento v2.0.
3. Visión y Plan v2.0.
4. Circuito Operativo v2.0.
5. Modelo de Datos e Integración v2.0 en sus respectivos dominios.
6. Diseño de Pantallas v2.0.

---

## 3. Documentos de contexto

Los archivos de `Contexto/` y `Reuniones/` explican cómo se llegó al modelo actual. No constituyen especificación vigente cuando:

- proponen una transición gradual o *shadow mode*;
- permiten que SGM siga originando o publicando necesidades;
- requieren reconciliación permanente de ejecuciones externas;
- asignan o prorratean stock en Connexa durante la Fase 1;
- suponen APIs de Stock Neto Disponible aún no confirmadas;
- incluyen cubicaje, rutas o planificación logística inteligente dentro del primer alcance.

La minuta del 02/07/2026 y la documentación de servicios WMS-VKM son fuentes relevantes, pero sus capacidades deben validarse en ambiente antes de considerarse contrato definitivo.

---

## 4. Vocabulario obligatorio

| Término | Uso acordado |
| --- | --- |
| Necesidad | Demanda de mercadería para una sucursal, identificada por artículo, origen, cantidad y horizonte |
| Necesidad regular | Necesidad calculada diariamente por Connexa a partir de demanda y posición de stock |
| Necesidad excepcional | Registro explícito por Venta Especial, Acuerdo Comercial o Acopio |
| Backlog | Saldo vigente aún no preparado por Valkimia ni cancelado |
| Oferta a Valkimia | Consolidado que Connexa deja disponible para que Valkimia procese |
| Cantidad preparada | Cantidad que Valkimia informa como efectivamente preparada |
| Stock CD de referencia | Stock recibido por Connexa para cálculo y visibilidad; puede no equivaler al SND operativo |
| Stock Neto Disponible | Stock operativo que Valkimia considera utilizable al momento de preparar |
| Transferencia intersucursal | Requerimiento de rebalanceo entre sucursales, fuera del circuito del CD |
| Fase 1 | Necesidades de Distribución y visibilidad operativa |
| Fase 2 | Gestión de la Distribución Inteligente |

No usar “planificación inteligente”, “asignación de stock” o “cubicaje” como capacidades de la Fase 1.

---

## 5. Control de cambios v2.0

- Se reemplazó la transición gradual por un corte Big‑Bang del módulo.
- Se eliminó a SGM como origen transitorio o publicador dentro del flujo futuro.
- Se separó la Fase 1 de Necesidades de la Fase 2 de Gestión Inteligente.
- Se reemplazó la asignación previa de stock por procesamiento oportunista de Valkimia.
- Se incorporaron Venta Especial, Acuerdo Comercial, Acopio y sus fechas/SLA/vigencias.
- Se incorporó el circuito intersucursal por fuera del CD.
- Se definió el recálculo diario del backlog sin acumulación duplicada.
- Se priorizó el panel del comprador por proveedor, sucursal y artículo.
- Se desacopló el dominio de Connexa de la versión actual o WEB de Valkimia.
- Se mantuvo la migración WEB como evolución tecnológica.
- Se reemplazó el modelo de convivencia por un modelo de datos de snapshots, ofertas y eventos.
- Se definió una estrategia de idempotencia compatible con la integración vigente.

---

## 6. Paquete archivado

Los entregables v1.0 fueron movidos a:

```text
Contexto/Version 1 - Reemplazada/
```

Se conservan para trazabilidad, incluyendo las correcciones editoriales que estaban sin confirmar en Git. No deben utilizarse como base de construcción.

