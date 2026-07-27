# Necesidades de Distribución — Connexa como fuente única

Versión: **2.0**
Fecha: **2026-07-24**
Estado: **Base funcional para validación**
Reemplaza: `PDD - Vision Requerimiento y Plan Connexa v1.0.md`

---

## 1. Resumen ejecutivo

DIARCO necesita mejorar rápidamente la actividad de los compradores y la visibilidad del abastecimiento sin esperar la migración completa a la nueva versión WEB de Valkimia.

La decisión es implementar una primera fase acotada y de alto impacto:

> Connexa será la única fuente de necesidades de distribución. SGM dejará de intervenir en este circuito desde el corte productivo.

La Fase 1 no intenta construir todavía un planificador logístico integral. Su objetivo es:

- calcular diariamente la necesidad regular de cada sucursal;
- permitir que Compras registre únicamente excepciones comerciales;
- consolidar y ofrecer esas necesidades a Valkimia;
- registrar qué pudo preparar Valkimia con su Stock Neto Disponible;
- recalcular al día siguiente el saldo todavía necesario;
- exponer a Compras una visión única de stock, necesidades y ejecución;
- registrar transferencias intersucursal para su posterior ejecución logística.

Valkimia conservará en esta etapa su comportamiento oportunista: tomará del consolidado únicamente lo que pueda procesar. Connexa no perderá el remanente; lo mantendrá visible y lo recalculará con la nueva posición del día.

La Fase 2 queda explícitamente reservada para la futura **Gestión de la Distribución Inteligente**, cuando la empresa decida actualizar Valkimia y delegar en Connexa asignación, prorrateo, capacidad, viajes y optimización.

---

## 2. Motivo del cambio

### 2.1 Hallazgos

El proceso actual presenta:

- dos fuentes de ingreso y modificación de datos;
- riesgo de duplicación y desincronización;
- decisiones dispersas entre SGM, Connexa y Valkimia;
- trabajo manual repetitivo para Compras;
- poca visibilidad del stock y del avance de cada necesidad;
- dificultad para conocer qué quedó pendiente y por qué.

### 2.2 Restricción tecnológica

La versión WEB de Valkimia ofrece una dirección de integración más ágil mediante APIs y webservices. Sin embargo, su migración puede demorarse por presupuesto, calendario y dependencias de implementación.

El proyecto no debe quedar bloqueado por esa migración. La solución debe:

- poder operar con el mecanismo de integración actual confirmado;
- aislar las particularidades de Valkimia detrás de adaptadores;
- conservar un modelo de dominio estable;
- permitir sustituir el adaptador por APIs WEB sin rediseñar el proceso funcional.

### 2.3 Restricción operativa

No se implementará convivencia funcional con SGM. Mantener dos orígenes, aunque sea temporalmente, reintroduciría el problema que se busca resolver.

El cambio será Big‑Bang para el alcance del módulo:

- antes del corte: preparación, limpieza y carga inicial;
- desde el corte: toda nueva necesidad se gestiona en Connexa;
- después del corte: SGM queda fuera de creación, publicación y modificación del circuito.

---

## 3. Principios del modelo

### P1. Una sola fuente

Connexa es la fuente única de verdad de las necesidades, excepciones, backlog y visión funcional.

### P2. Automatización de lo regular

La demanda regular se calcula todos los días. El comprador no debe cargar manualmente reposiciones normales.

### P3. Compras opera por excepción

Compras registra Ventas Especiales, Acuerdos Comerciales, Acopio y rebalanceos intersucursal; analiza alertas y gestiona desvíos.

### P4. Necesidad y ejecución son conceptos distintos

La necesidad expresa lo que una sucursal requiere. Valkimia informa cuánto pudo preparar. La falta de stock no elimina la necesidad.

### P5. Backlog recalculado, no acumulado ciegamente

La necesidad regular se reemplaza cada día con una nueva foto que descuenta stock en sucursal e ingresos activos. Las excepciones se conservan por identidad y vigencia.

### P6. Valkimia es oportunista en la Fase 1

Valkimia decide qué puede procesar con el SND real. Connexa no asigna ni prorratea stock escaso en esta fase.

### P7. Integración desacoplada

El dominio no depende de nombres de tablas, endpoints ni estados particulares de una versión de Valkimia.

### P8. Trazabilidad por línea

Cada estado debe poder explicarse por sucursal, artículo, cantidad, origen, fecha y evento.

---

## 4. Alcance de la Fase 1

### 4.1 Cálculo diario de necesidad regular

Connexa ejecutará una corrida diaria para cada combinación relevante de:

```text
CD + sucursal + artículo
```

La fórmula funcional base será:

```text
stock_proyectado_sucursal =
  stock_disponible_sucursal
  + ingresos_confirmados_no_recibidos
  - compromisos_confirmados

necesidad_regular_bruta =
  max(stock_objetivo_horizonte - stock_proyectado_sucursal, 0)
```

El cálculo deberá considerar, según disponibilidad y parametría:

- demanda o forecast del horizonte;
- stock disponible de sucursal;
- stock mínimo, objetivo o cobertura;
- ventas y velocidad de consumo;
- pedidos/transferencias en tránsito;
- necesidades excepcionales vigentes;
- stock CD de referencia;
- múltiplos o unidades logísticas.

El stock CD de referencia se utilizará para mostrar factibilidad y alertas, pero no debe hacer desaparecer la necesidad bruta. Se conservarán, como mínimo:

- `qty_required`: necesidad total vigente;
- `qty_cd_reference`: stock CD conocido para visibilidad;
- `qty_offerable`: cantidad que puede ofrecerse según reglas de Fase 1;
- `qty_prepared`: cantidad confirmada por Valkimia;
- `qty_backlog`: saldo vigente.

La fórmula definitiva, horizonte y fuentes deberán parametrizarse y validarse con Abastecimiento.

### 4.2 Excepciones de Compras

El comprador podrá registrar:

#### Venta Especial

- sucursal;
- artículo;
- cantidad;
- fecha objetivo;
- SLA;
- cliente/campaña o referencia;
- prioridad;
- observaciones y adjuntos/referencia documental.

#### Acuerdo Comercial

- proveedor;
- artículos alcanzados;
- sucursales o grupo de sucursales;
- cantidad o regla acordada;
- fecha de inicio y fin;
- SLA o condición de llegada;
- referencia del acuerdo.

#### Acopio

- sucursal o destino;
- artículo;
- cantidad;
- motivo;
- fecha requerida;
- vigencia;
- prioridad.

Las excepciones no deben duplicarse con el cálculo regular. El motor diario deberá identificarlas por un ID estable y aplicar la política configurada: adicional, mínimo garantizado o reemplazo.

### 4.3 Transferencias intersucursal

Compras podrá registrar requerimientos de rebalanceo:

```text
sucursal origen -> sucursal destino -> artículo -> cantidad -> fecha requerida
```

Este circuito:

- no consume ni pasa por el CD;
- no se incluye en el consolidado CD -> sucursal enviado a Valkimia;
- queda pendiente de aceptación y ejecución logística posterior;
- debe ser visible en el stock proyectado de origen y destino cuando sea aprobado;
- debe conservar estados y auditoría propios.

### 4.4 Consolidado para Valkimia

Connexa generará el consolidado vigente por destino y artículo, preservando la relación con sus orígenes.

Características:

- publicación con referencia externa estable;
- reenvío seguro sin duplicar;
- cantidades y fechas objetivo por línea;
- separación entre necesidad regular y excepciones;
- estado de envío y última actualización;
- adaptación al contrato actual de Valkimia;
- posibilidad de reemplazar el adaptador por la integración WEB futura.

### 4.5 Registro de ejecución

Connexa incorporará los estados y cantidades que Valkimia pueda informar.

Mínimo requerido para la Fase 1:

- documento o referencia Valkimia;
- estado de documento;
- cantidad requerida;
- cantidad confirmada/preparada;
- fecha de última actualización;
- motivo de rechazo o incidencia, cuando exista.

Estados normalizados sugeridos:

- `OFFER_PENDING`
- `OFFER_SENT`
- `VKM_RECEIVED`
- `VKM_IN_PROCESS`
- `VKM_PREPARED_PARTIAL`
- `VKM_PREPARED`
- `VKM_DISPATCHED`
- `VKM_CANCELLED`
- `TECHNICAL_ERROR`

El mapping se parametrizará contra los estados reales. La documentación disponible menciona estados como `GEN`, `ACO`, `CUR`, `TER`, `REV`, `PRG`, `EXP`, `CAR`, `ANU` y `AGR`; deben validarse en el ambiente DIARCO antes de cerrar el contrato.

### 4.6 Panel del comprador

El comprador dispondrá de una vista por:

```text
proveedor -> sucursal -> artículo
```

La vista deberá integrar:

- stock disponible de sucursal;
- cobertura o días de stock;
- stock CD de referencia;
- necesidad regular vigente;
- excepciones vigentes;
- ofrecido a Valkimia;
- en proceso;
- preparado;
- despachado/en tránsito;
- recibido, cuando la fuente exista;
- backlog;
- SLA y antigüedad;
- alertas y próxima acción.

Las acciones principales serán investigar, registrar una excepción, ajustar una excepción autorizada, crear un rebalanceo intersucursal y gestionar una alerta.

---

## 5. Recálculo diario y control de duplicados

### 5.1 Regla de reemplazo para demanda regular

Cada corrida diaria creará una versión del cálculo y actualizará la posición regular vigente. No se sumará el resultado del día a los resultados anteriores.

```text
regular_need[t] = cálculo con foto t
regular_need[t+1] = nuevo cálculo con foto t+1
```

La historia se conserva para auditoría, pero solo la versión vigente alimenta el backlog operativo.

### 5.2 Regla para cantidades en pipeline

El cálculo deberá descontar cantidades que ya están:

- aceptadas o en proceso en Valkimia;
- preparadas;
- despachadas o en tránsito;
- aprobadas en una transferencia intersucursal.

No debe descontar:

- ofertas con error técnico que nunca llegaron a Valkimia;
- documentos cancelados;
- cantidades rechazadas o no confirmadas cuando el estado final demuestre que no serán preparadas.

### 5.3 Regla para excepciones

Las excepciones son entidades persistentes y no se reemplazan por el cálculo diario. Permanecen activas hasta:

- cumplimiento;
- vencimiento;
- cancelación autorizada;
- cierre manual justificado.

### 5.4 Regla de identidad

Cada corrida, necesidad, excepción, oferta y línea tendrá identificadores estables. El adaptador deberá usar una clave externa determinística o una tabla de correspondencia para impedir la creación repetida del mismo documento en Valkimia.

---

## 6. Arquitectura funcional

```text
Ventas / Forecast / Stock sucursal / Stock CD / En tránsito
                           |
                           v
             Motor diario de necesidades Connexa
                           |
           +---------------+----------------+
           |                                |
           v                                v
Excepciones de Compras             Rebalanceos intersucursal
           |                         (circuito separado)
           v
Consolidado CD -> sucursal
           |
           v
Adaptador Valkimia actual o WEB
           |
           v
Valkimia toma lo procesable según SND
           |
           v
Estados y cantidades preparadas
           |
           v
Visión Connexa + recálculo del backlog diario
```

Componentes lógicos:

- ingesta de datos comerciales e inventario;
- motor de cálculo diario;
- gestión de excepciones;
- gestión de rebalanceos;
- consolidación y versionado;
- adaptador de salida a Valkimia;
- adaptador de tracking;
- proyección de stock y pipeline;
- tablero del comprador;
- auditoría y monitoreo.

---

## 7. Estrategia de integración con Valkimia

### 7.1 Fase 1

Se utilizarán capacidades confirmadas de la versión instalada o del mecanismo vigente. La documentación recibida describe servicios REST para:

- alta individual o en lista de documentos de salida;
- consulta de documento e ID;
- consulta de documentos finalizados pendientes;
- consulta de documento en curso;
- marcado como procesado;
- cancelación;
- estados y cantidades confirmadas por línea.

No se considera confirmada una API específica de Stock Neto Disponible. Por lo tanto:

- el cálculo usará las fuentes de stock actualmente disponibles para Connexa;
- Valkimia será la última validación operativa al preparar;
- la ausencia de una API SND no bloqueará la Fase 1;
- el contrato real se probará con payloads, estados, límites e idempotencia en ambiente.

### 7.2 Fase 2 / versión WEB

La evolución buscará:

- APIs documentadas y versionadas;
- autenticación y seguridad modernas;
- idempotencia contractual;
- eventos o polling incremental;
- stock neto y reservas en tiempo cercano a real;
- tracking detallado por línea;
- mejores capacidades de cancelación y ajuste.

### 7.3 Patrón de desacople

Connexa expondrá puertos internos estables:

- `publishDistributionOffer`
- `getDistributionStatus`
- `getPreparedQuantities`
- `getNetAvailableStock` — opcional en Fase 1

Cada versión de Valkimia tendrá su adaptador. Ninguna regla funcional debe depender directamente del formato externo.

---

## 8. Corte Big‑Bang

### 8.1 Preparación

- definir fecha y hora de corte;
- congelar cambios del circuito en SGM;
- inventariar necesidades y documentos abiertos;
- clasificar cada pendiente como migrar, cerrar o continuar solo para seguimiento;
- cargar y validar el inventario inicial en Connexa;
- habilitar usuarios y permisos;
- probar cálculo, carga de excepciones, publicación y tracking;
- preparar contingencia y mesa de ayuda.

### 8.2 Corte

- deshabilitar altas y publicaciones del módulo en SGM;
- ejecutar última conciliación;
- activar Connexa como único origen;
- publicar el primer consolidado controlado;
- verificar conteos y referencias extremo a extremo.

### 8.3 Estabilización

- monitoreo intensivo diario;
- conciliación de cantidades por artículo y sucursal;
- gestión de errores sin reabrir el doble ingreso;
- corrección por reenvío idempotente o intervención controlada;
- revisión diaria de backlog, SLA y documentos no actualizados.

### 8.4 Contingencia

El rollback no consistirá en reactivar libremente SGM. Si Connexa no puede publicar:

- se conserva el registro único en Connexa;
- se habilita una cola de salida o procedimiento manual controlado;
- cada envío de contingencia usa la misma referencia;
- la regularización posterior actualiza Connexa;
- la reactivación de SGM requiere una decisión ejecutiva explícita.

---

## 9. Fases del programa

### Fase 0 — Cierre funcional y preparación del corte

Entregables:

- fórmula de necesidad y horizonte;
- fuentes y calidad de datos;
- catálogo de excepciones;
- mapping Valkimia;
- inventario de pendientes;
- plan de corte y contingencia;
- criterios Go/No-Go.

### Fase 1A — Necesidades y visibilidad

Entregables:

- cálculo diario;
- backlog vigente;
- Venta Especial, Acuerdo Comercial y Acopio;
- panel del comprador;
- alertas de bajo stock y SLA;
- auditoría.

### Fase 1B — Consolidado y ejecución Valkimia

Entregables:

- consolidado CD -> sucursal;
- publicación segura por adaptador actual;
- tracking de estados y cantidades preparadas;
- recálculo diario del remanente;
- monitor técnico.

### Fase 1C — Rebalanceo intersucursal

Entregables:

- solicitud origen/destino;
- aprobación;
- estados para ejecución logística;
- impacto en stock proyectado;
- seguimiento y auditoría.

Las tres subfases forman una única salida Big‑Bang. La separación organiza construcción y pruebas, no autoriza convivencia productiva.

### Fase 2 — Gestión de la Distribución Inteligente

Cuando la organización y Valkimia estén preparadas:

- Connexa asignará stock escaso;
- aplicará prioridades y *fair share*;
- planificará ventanas y capacidad;
- incorporará peso, volumen, pallets y cubicaje;
- optimizará viajes/rutas;
- simulará escenarios;
- se integrará preferentemente con la versión WEB.

---

## 10. Alcance excluido de la Fase 1

- asignación central de SND entre sucursales;
- prorrateo automático de stock escaso;
- optimización de camiones;
- cubicaje;
- ruteo;
- reservas de stock en Valkimia;
- reoptimización intradía avanzada;
- convivencia de SGM y Connexa;
- reconciliación permanente de dos publicadores;
- reemplazo integral de otros módulos de SGM;
- migración obligatoria a Valkimia WEB.

---

## 11. Indicadores de éxito

- 100% de las nuevas necesidades dentro del alcance nacen en Connexa.
- 0 nuevas cargas o publicaciones del módulo desde SGM después del corte.
- 100% de ofertas a Valkimia con referencia única trazable.
- 100% de cantidades no preparadas permanecen visibles o son explicadas por recálculo.
- Reducción del tiempo de carga manual de Compras.
- Porcentaje de compradores activos en el panel.
- Backlog por proveedor, sucursal y artículo con antigüedad y SLA.
- Tasa de actualización de estados Valkimia dentro del intervalo acordado.
- Diferencia entre cantidades ofrecidas, preparadas y recibidas.
- Alertas de quiebre o entrega tardía gestionadas dentro del SLA.

---

## 12. Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| Datos de stock o demanda incompletos | Calidad previa, semáforo de frescura y modo controlado |
| SGM continúa usándose por hábito | Deshabilitar funcionalidad, permisos y procedimiento formal |
| API/servicio actual no es idempotente | Referencia estable, tabla de correspondencia y consulta antes de crear |
| Estados Valkimia ambiguos | Mapping validado con casos reales y estado `UNKNOWN` alertable |
| Cantidad preparada llega tarde | Polling configurable, lista de pendientes y alerta de desactualización |
| Big‑Bang deja pendientes sin migrar | Inventario firmado, conteos de control y conciliación de arranque |
| Excepciones duplican demanda regular | Política explícita adicional/mínimo/reemplazo e ID estable |
| Falta de SND accesible | No bloquear Fase 1; mostrar stock de referencia y aceptar ejecución oportunista |
| Alcance se expande hacia Fase 2 | Criterios de exclusión y backlog evolutivo separado |

---

## 13. Decisiones pendientes para iniciar desarrollo

1. Fórmula exacta, horizonte y frecuencia del cálculo regular.
2. Fuente de stock sucursal, stock CD, tránsito, demanda y maestro.
3. Significado del stock CD disponible usado hoy por Compras.
4. Política de combinación de cada tipo de excepción con la necesidad regular.
5. Datos obligatorios y aprobación de Venta Especial, Acuerdo Comercial y Acopio.
6. Estados y responsables del circuito intersucursal.
7. Contrato real con Valkimia instalado: operación, tipo documental, campos, límites y errores.
8. Estado que representa “preparado” y cantidad confirmada por línea.
9. Mecanismo técnico de idempotencia.
10. Intervalo de sincronización y SLA de frescura.
11. Fecha de corte y universo de pendientes a migrar.
12. Fuente de recepción en sucursal.

Estas decisiones no modifican el rumbo aprobado; completan la especificación operativa.

---

## 14. Resultado esperado

Al finalizar la Fase 1, Compras dejará de mantener manualmente la reposición normal y trabajará por excepción. Connexa ofrecerá una vista compartida y diaria de lo que cada sucursal necesita, lo que Valkimia tomó, lo que preparó y lo que continúa pendiente. El corte único con SGM elimina la duplicación de origen, mientras el diseño por adaptadores permite obtener beneficios inmediatos sin renunciar a la futura migración WEB ni a la evolución hacia Gestión de la Distribución Inteligente.

