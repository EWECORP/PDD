# Estado de los documentos de Contexto

Fecha de clasificación: **2026-07-28**

Esta carpeta contiene antecedentes que permitieron construir la propuesta. Se conserva para trazabilidad y no debe utilizarse como especificación vigente cuando contradiga el paquete v2.1 ubicado en la raíz de `PDD/`.

## Regla de lectura

La versión vigente está definida en:

```text
../PDD - Indice y Gobierno Documental.md
```

En particular, quedaron reemplazadas las siguientes ideas de los documentos de contexto:

| Idea anterior | Decisión vigente v2.1 |
| --- | --- |
| Transición gradual / shadow mode | Corte Big‑Bang del módulo |
| SGM como origen transitorio | SGM fuera del circuito desde el corte |
| Reconciliación permanente SGM–Connexa | Inventario inicial único y conciliado |
| `ExternalExecution` para convivencia | No forma parte del modelo v2.0 |
| Connexa asigna SND en la primera etapa | Valkimia procesa oportunísticamente |
| Connexa publica o asigna qué ejecutar | Valkimia consulta/importa oportunísticamente; Connexa conserva el backlog |
| API de SND como dependencia obligatoria | Capacidad opcional; no bloquea la Fase 1 |
| Simulación, fair share y prorrateo en MVP | Reservados para Fase 2 |
| Cubicaje como siguiente sprint | Evolución de Gestión Inteligente |
| Transferencias intersucursal en Fase 1 | Fuera del alcance de 40 días |
| Connexa gestiona distribución, viajes o cargas | Fase 1 solo planifica necesidades y sigue resultados |

## Clasificación

| Documento | Clasificación |
| --- | --- |
| `PDD - 1) PLANIFICACIÓN de la DISTRIBUCIÓN CONNEXA (New).md` | Antecedente conceptual |
| `PDD - 2) Rediseño Conceptual Transferencias v1.0.md` | Reemplazado en alcance y transición |
| `PDD - 3) Maquina de Estados y Transiciones.md` | Referencia parcial; estados v2.1 son normativos |
| `PDD - 4) Matriz RACI.md` | Reemplazada por Circuito Operativo v2.1 |
| `PDD - 5) Plan de Transición.md` | Reemplazado por el plan Día 1–40 v2.1 |
| `PDD - 6) Modelo de Backlog Necesidades.md` | Referencia algorítmica de Fase 2 |
| `PDD - 7) Pseudocódigo implementable.md` | Referencia de Fase 2; no MVP |
| `PDD - 8) Catálogo de Reglas.md` | Referencia de Fase 2; revisar antes de reutilizar |
| `PDD - 9) Paquete de Integración v1.0 - TRANSFERENCIAS.md` | Reemplazado por el contrato oportunista v2.1 |
| `PDD - 10) Especificación de Interfaces Valkimia v1.0.md` | Diseño objetivo, no contrato confirmado |
| `PDD - 11) Modelo ER físico preliminar (PostgreSQL).md` | Reemplazado por el modelo conceptual v2.1; requiere nuevo modelo físico |
| `Version 1 - Reemplazada/` | Entregables v1.0 archivados, no vigentes |

## Uso permitido

Estos documentos pueden utilizarse para:

- entender problemas detectados;
- recuperar reglas candidatas;
- preparar la Fase 2;
- comparar decisiones;
- mantener trazabilidad histórica.

No deben utilizarse para estimar o desarrollar la Fase 1 sin contrastarlos con el Alcance rector y la Especificación v2.1.

