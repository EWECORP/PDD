# Diseño de Pantallas Operativas — Necesidades de Distribución

Versión: **2.0**
Fecha: **2026-07-24**
Destino: Producto, UX/UI, Desarrollo, QA, Compras, Logística e IT
Reemplaza: `PDD - Diseno de Pantallas Operativas Connexa v1.0.md`

---

## 1. Objetivo

Diseñar una experiencia centrada en el comprador:

- ver stock y pipeline por proveedor, sucursal y artículo;
- detectar bajo stock, atrasos y preparación parcial;
- comprender cómo se calculó una necesidad;
- registrar únicamente Ventas Especiales, Acuerdos Comerciales y Acopios;
- solicitar rebalanceos intersucursal;
- seguir la respuesta de Valkimia;
- operar por excepción, no línea por línea.

La interfaz no incluye en Fase 1 un simulador de asignación, *fair share*, cubicaje o planificación de camiones.

---

## 2. Principios UX

### P1. Posición integral

Una fila debe reunir:

```text
stock sucursal + necesidad + stock CD + pipeline + backlog + SLA
```

### P2. Excepción antes que volumen

El inicio debe priorizar las líneas que requieren una acción, no la totalidad del catálogo.

### P3. Cantidades explicables

Cada cantidad permite ver origen, fecha, fórmula, movimientos incluidos y vínculo con Valkimia.

### P4. Frescura visible

Todo stock, demanda o estado externo muestra fecha/hora. Un dato vencido nunca parece actual.

### P5. Un solo canal

No se ofrece ninguna acción que derive la carga hacia SGM o una publicación directa a Valkimia.

### P6. Fase 1 y Fase 2 separadas

La UI no prometerá asignación inteligente de stock. “Stock CD” es referencia; “Preparado” es confirmación de Valkimia.

---

## 3. Roles

| Rol | Capacidades |
| --- | --- |
| Comprador | Consulta, crea excepciones, solicita rebalanceos, gestiona alertas |
| Supervisor de Compras | Aprueba, cancela, modifica umbrales autorizados, ve KPIs |
| Logística | Gestiona ejecución intersucursal y consulta pipeline |
| Operación CD | Consulta ofertas/estados e incidencias |
| IT Integraciones | Monitor, errores, payloads, reintentos controlados |
| Auditor | Solo lectura y exportación |
| Administrador | Parámetros, mappings, fuentes, permisos y calendarios |

Segregación recomendada:

- quien crea una excepción de alto impacto no la aprueba;
- Compras no reintenta técnicamente;
- IT no modifica cantidades de negocio;
- un cambio de cantidad aprobado vuelve a aprobación si supera tolerancia.

---

## 4. Navegación

```text
Inicio — Mi Panel
  |
  +-- Stock y Necesidades
  |     +-- Detalle Sucursal–Artículo
  |
  +-- Excepciones
  |     +-- Ventas Especiales
  |     +-- Acuerdos Comerciales
  |     +-- Acopios
  |
  +-- Ofertas y Ejecución
  |     +-- Consolidado enviado
  |     +-- Documento Valkimia
  |
  +-- Transferencias Intersucursal
  |     +-- Nueva solicitud
  |     +-- Seguimiento logístico
  |
  +-- Alertas
  |
  +-- Administración
        +-- Corridas y fuentes
        +-- Integraciones
        +-- Mappings y parámetros
        +-- Auditoría
```

---

## 5. Pantalla 1 — Mi Panel de Compras

### Pregunta que responde

> ¿Dónde tengo riesgo de stock, un compromiso próximo o una entrega atrasada?

### Wireframe

```text
+----------------------------------------------------------------------------------+
| Necesidades de Distribución                      Datos al 24/07 06:10  [Actualizar]|
+----------------------------------------------------------------------------------+
| Riesgo quiebre | SLA vencidos | Prep. parcial | Sin avance | Datos vencidos      |
|      128       |      19      |       34      |     11     |       7              |
+----------------------------------------------------------------------------------+
| Mis filtros: Comprador [EE] Proveedor [Todos] Familia [Todos] Sucursal [Todas]   |
+----------------------------------------------------------------------------------+
| Prioridad | Proveedor | Sucursal | Artículo | Cobertura | Backlog | Estado | SLA  |
| CRÍTICA   | Prov. A   | 041      | 1234     | 0,8 días  | 60      | PARCIAL| -4h  |
| ALTA      | Prov. B   | 052      | 9876     | 1,2 días  | 20      | SIN CD | 12h  |
+----------------------------------------------------------------------------------+
| [Ver posición completa] [Nueva excepción] [Solicitar rebalanceo]                 |
+----------------------------------------------------------------------------------+
```

### Componentes

- KPIs accionables.
- Lista priorizada de alertas.
- Filtros persistentes del comprador.
- Semáforo de frescura.
- Accesos rápidos.
- Evolución de backlog y cobertura.

### Acciones

- Abrir posición filtrada.
- Crear excepción.
- Solicitar transferencia intersucursal.
- Asignar/reconocer alerta.
- Guardar vista.

---

## 6. Pantalla 2 — Stock y Necesidades

### Pregunta que responde

> ¿Cuál es la posición completa por proveedor, sucursal y artículo?

### Wireframe

```text
+--------------------------------------------------------------------------------------------------+
| Stock y Necesidades                                                                               |
+--------------------------------------------------------------------------------------------------+
| Agrupar por [Proveedor > Sucursal > Artículo]  Buscar [...]  Datos [Actuales ▾]                   |
| Filtros: Comprador | CD | Proveedor | Familia | Sucursal | Artículo | Estado | SLA | Alerta       |
+--------------------------------------------------------------------------------------------------+
| Prov | Suc | Artículo | Stock Suc | Cob. | Stock CD* | Regular | Excep. | Ofrec. | Prep. | Backlog|
| A    | 041 | 1234     | 20 06:00  | 0,8  | 70 05:55  | 80      | 30     | 110    | 60    | 50     |
+--------------------------------------------------------------------------------------------------+
| * Stock CD de referencia; Valkimia confirma disponibilidad real al preparar.                      |
+--------------------------------------------------------------------------------------------------+
```

### Filtros

- comprador;
- proveedor;
- familia/categoría;
- CD;
- sucursal;
- artículo;
- tipo de necesidad;
- cobertura;
- estado pipeline;
- SLA;
- severidad;
- frescura.

### Columnas

- proveedor;
- sucursal;
- artículo y descripción;
- stock sucursal + timestamp;
- cobertura;
- stock CD de referencia + timestamp;
- necesidad regular;
- Venta Especial;
- Acuerdo;
- Acopio;
- ofrecido;
- en proceso;
- preparado;
- despachado/en tránsito;
- recibido;
- backlog;
- SLA;
- última actividad;
- alerta;
- próxima acción.

### Vistas

- compacta;
- posición completa;
- solo excepciones;
- solo riesgo de quiebre;
- solo atraso;
- por proveedor;
- por sucursal.

### Reglas visuales

- Rojo: quiebre o SLA vencido.
- Ámbar: cobertura baja, parcial o SLA próximo.
- Azul: en proceso.
- Verde: cubierto/recibido.
- Gris rayado: dato desactualizado.
- Ícono de advertencia: stock CD es referencia, no reserva.

---

## 7. Pantalla 3 — Detalle Sucursal–Artículo

### Pregunta que responde

> ¿Por qué Connexa dice que se necesitan estas unidades y qué pasó con ellas?

### Wireframe

```text
+----------------------------------------------------------------------------------+
| Sucursal 041 — Artículo 1234                               Riesgo: CRÍTICO         |
+----------------------------------------------------------------------------------+
| Stock sucursal 20 | Objetivo 100 | Pipeline 60 | Regular abierta 20 | Excep. 30  |
| Stock CD ref. 70 (05:55) | Cobertura 0,8 días | Próximo SLA 24/07 14:00          |
+----------------------------------------------------------------------------------+
| Cómo se calculó                                                                  |
| Objetivo 100 - Stock 20 - Pipeline 60 = Regular 20                              |
+----------------------------------------------------------------------------------+
| Excepciones: VE-120 30 u, SLA 14:00, parcial 10/30                              |
+----------------------------------------------------------------------------------+
| Pipeline                                                                          |
| Oferta CNX-... 110 -> VKM 55431 -> En curso -> Preparado 60 -> Últ. 10:32       |
+----------------------------------------------------------------------------------+
| Timeline | Comentarios | Calidad de datos                                        |
+----------------------------------------------------------------------------------+
```

### Secciones

- posición actual;
- explicación de fórmula;
- datos fuente y frescura;
- excepciones;
- ofertas y documentos Valkimia;
- cantidades por etapa;
- transferencias intersucursal relacionadas;
- timeline;
- alertas y responsable.

### Acciones

- crear excepción;
- solicitar rebalanceo;
- ver documento Valkimia;
- comentar;
- reconocer/escalar alerta;
- exportar timeline.

---

## 8. Pantalla 4 — Nueva Venta Especial

### Formulario

```text
Sucursal* | Artículo* | Cantidad*
Fecha/hora objetivo* | SLA*
Cliente/campaña/referencia*
Prioridad | Política [Adicional / Mínimo / Reemplazo]
Observaciones | Evidencia
```

### Panel lateral

Mientras se completa, mostrar:

- stock sucursal;
- cobertura;
- stock CD de referencia;
- necesidad regular;
- otras excepciones coincidentes;
- pipeline;
- impacto total;
- advertencia de posible duplicado.

### Acciones

- guardar borrador;
- enviar a aprobación;
- activar si el permiso/umbral lo permite;
- cancelar.

---

## 9. Pantalla 5 — Acuerdos Comerciales

### Listado

Columnas:

- acuerdo;
- proveedor;
- vigencia;
- artículos;
- sucursales;
- regla/cantidad;
- política;
- cumplimiento;
- próximo SLA;
- estado.

### Alta/edición

```text
Proveedor* | Referencia*
Inicio* | Fin*
Política* | Prioridad | SLA
Artículos [selector/importación]
Sucursales [selector/grupo/importación]
Cantidad fija / mínimo / regla
```

### Validaciones

- período válido;
- artículos vinculados al proveedor;
- líneas duplicadas;
- superposición con otro acuerdo;
- impacto estimado;
- aprobación por umbral.

### Detalle

Mostrar cumplimiento por artículo y sucursal, cantidades ofrecidas/preparadas, pendientes, SLA y versiones.

---

## 10. Pantalla 6 — Acopios

### Listado

- ID;
- destino;
- artículo;
- cantidad;
- motivo;
- requerida;
- vigencia;
- cumplida;
- backlog;
- estado.

### Alta

Debe mostrar la posición actual y requerir:

- motivo;
- fecha requerida;
- fin de vigencia;
- política de combinación;
- prioridad.

No se permitirá un acopio indefinido.

---

## 11. Pantalla 7 — Excepciones

### Pregunta que responde

> ¿Qué excepciones están activas, pendientes o vencidas?

### Wireframe

```text
+----------------------------------------------------------------------------------+
| Excepciones                         [Nueva Venta] [Nuevo Acuerdo] [Nuevo Acopio]  |
+----------------------------------------------------------------------------------+
| Tipo | Ref | Proveedor | Suc | Art | Cant. | Cumplida | Saldo | SLA | Estado    |
+----------------------------------------------------------------------------------+
| Filtros: Tipo | Creador | Aprobador | Vigencia | SLA | Estado | Posible duplicado|
+----------------------------------------------------------------------------------+
```

Acciones masivas limitadas a exportar/asignar; no se habilitará cancelación masiva sin flujo específico.

---

## 12. Pantalla 8 — Ofertas a Valkimia

### Pregunta que responde

> ¿Qué consolidado se envió y cuánto tomó Valkimia?

### Wireframe

```text
+----------------------------------------------------------------------------------+
| Ofertas a Valkimia                                                               |
+----------------------------------------------------------------------------------+
| Oferta | Fecha | CD | Destinos | Líneas | Ofrecido | Preparado | Estado | Alerta |
| CNX-01 | 24/07 | 01 | 84       | 3.210  | 125.000  | 88.500    | PARCIAL| 34 SLA |
+----------------------------------------------------------------------------------+
```

### Detalle

- referencia Connexa;
- documento(s) Valkimia;
- adaptador usado;
- timestamps;
- líneas;
- origen regular/excepcional;
- ofrecido/confirmado;
- estados;
- errores;
- timeline técnico resumido.

### Acciones por rol

Compras:

- ver y filtrar;
- abrir posición;
- gestionar alerta.

IT:

- consultar estado;
- reintentar solo error técnico;
- ver payload;
- vincular respuesta ambigua con controles.

---

## 13. Pantalla 9 — Documento Valkimia

### Contenido

- ID y estado externo original;
- estado normalizado;
- tipo/operación/depósito/destino;
- fecha de generación;
- líneas con cantidad requerida y confirmada;
- última consulta;
- mensajes;
- oferta Connexa asociada;
- timeline.

Debe distinguir claramente:

- `Ofrecido por Connexa`.
- `Confirmado/preparado por Valkimia`.
- `Despachado/recibido`, solo si existe evidencia.

No etiquetar `TER` automáticamente como “recibido” sin validación del mapping.

---

## 14. Pantalla 10 — Transferencias Intersucursal

### Listado

```text
ID | Origen | Destino | Artículo | Cantidad | SLA | Estado | Responsable | Alerta
```

### Nueva solicitud

```text
Sucursal origen* | Sucursal destino*
Artículo* | Cantidad* | Fecha requerida*
Motivo* | Prioridad | Observación
```

Panel de impacto:

```text
Origen: stock 100 -> proyectado 60 -> cobertura 4,2 días
Destino: stock 5 -> proyectado 45 -> cobertura 3,1 días
```

### Flujo de estado

Barra visual:

```text
Solicitud -> Aprobación -> Logística -> Preparación -> Despacho -> Recepción
```

### Acciones

- aprobar/rechazar;
- asignar responsable logístico;
- registrar preparación;
- registrar despacho;
- confirmar recepción;
- cancelar con motivo.

---

## 15. Pantalla 11 — Centro de Alertas

### Tipos

| Grupo | Ejemplos |
| --- | --- |
| Abastecimiento | Quiebre, cobertura baja, stock CD insuficiente |
| Comercial | Venta/Acuerdo/Acopio próximo o vencido |
| Ejecución | Sin recepción, preparación parcial, documento estancado |
| Datos | Stock/demanda/maestro desactualizado |
| Integración | Error, timeout, respuesta ambigua, estado desconocido |
| Intersucursal | Aprobación o entrega vencida |
| Gobierno | Intento de origen SGM posterior al corte |

### Gestión

Cada alerta tendrá:

- severidad;
- entidad;
- responsable;
- creación;
- SLA de atención;
- estado;
- comentario;
- acción recomendada;
- resolución.

---

## 16. Pantalla 12 — Corridas Diarias

### Usuarios

Supervisor, Datos, IT y auditor.

### Contenido

- fecha operativa;
- versión de fórmula;
- ámbitos;
- fuentes/lotes/frescura;
- inicio/fin;
- registros procesados;
- rechazados;
- necesidades resultantes;
- alertas;
- versión vigente;
- usuario/proceso.

### Acciones

- ver diferencias contra corrida anterior;
- ver errores por línea;
- relanzar ámbito autorizado;
- promover una versión como vigente;
- exportar control.

Un relanzamiento debe advertir que reemplazará la foto vigente; nunca “agregar” resultados.

---

## 17. Pantalla 13 — Monitor Técnico

### Tarjetas

- fuentes de datos;
- publicador Valkimia;
- tracking Valkimia;
- cola de salida;
- documentos finalizados;
- recálculo;
- notificaciones.

### Métricas

- última ejecución exitosa;
- latencia p50/p95;
- tasa de error;
- cola/reintentos;
- respuestas ambiguas;
- estados desconocidos;
- referencias sin vínculo;
- documentos sin actualización;
- diferencia ofrecido/confirmado.

### Reintentos

La UI debe mostrar primero:

1. si existe documento externo;
2. referencia utilizada;
3. último request/response;
4. riesgo de duplicación.

Solo entonces un usuario autorizado podrá reintentar.

---

## 18. Pantalla 14 — Parámetros y Mappings

### Secciones

- calendario/frecuencia;
- fórmula e horizonte;
- cobertura/stock objetivo;
- múltiplos;
- política por excepción;
- aprobación por umbral;
- mapping de estados Valkimia;
- intervalos de polling;
- umbrales de alerta;
- imputación de preparados;
- stock protegido intersucursal;
- fecha de corte y fuentes permitidas.

### Reglas

- versionado con vigencia;
- comparación antes/después;
- motivo obligatorio;
- aprobación;
- aplicación a nuevas corridas;
- no alterar historia.

---

## 19. Pantalla 15 — Auditoría

Búsqueda por:

- sucursal;
- artículo;
- proveedor;
- necesidad;
- excepción;
- oferta;
- ID Valkimia;
- transferencia intersucursal;
- usuario;
- evento;
- fecha.

Cada evento muestra:

- valor anterior/nuevo;
- actor/sistema;
- timestamp;
- correlación;
- payload protegido;
- comentario.

---

## 20. Flujos principales

### Flujo A — Revisión diaria

```text
Mi Panel
  -> alerta de quiebre
  -> Stock y Necesidades
  -> Detalle Sucursal–Artículo
  -> revisar pipeline
  -> crear excepción o escalar atraso
```

### Flujo B — Venta Especial

```text
Nueva Venta Especial
  -> validar impacto/duplicados
  -> aprobación
  -> Excepciones activas
  -> Oferta Valkimia
  -> preparación
  -> cumplimiento/SLA
```

### Flujo C — Preparación parcial

```text
Alerta
  -> Oferta
  -> Documento Valkimia
  -> línea parcial
  -> posición sucursal–artículo
  -> saldo y próxima acción
```

### Flujo D — Rebalanceo

```text
Stock y Necesidades
  -> solicitar intersucursal
  -> impacto origen/destino
  -> aprobación
  -> Logística
  -> despacho
  -> recepción
```

### Flujo E — Error técnico

```text
Monitor
  -> resultado ambiguo
  -> consulta por referencia
  -> vincular o reintentar con misma referencia
  -> reconciliación
```

---

## 21. MVP de pantallas

### Imprescindibles para Big‑Bang

1. Mi Panel de Compras.
2. Stock y Necesidades.
3. Detalle Sucursal–Artículo.
4. Venta Especial.
5. Acuerdos Comerciales.
6. Acopios.
7. Excepciones.
8. Ofertas a Valkimia.
9. Documento Valkimia.
10. Transferencias Intersucursal.
11. Centro de Alertas.
12. Corridas Diarias.
13. Monitor Técnico.
14. Parámetros/mappings básicos.
15. Auditoría.

### Posteriores dentro de Fase 1

- vistas comparativas históricas avanzadas;
- personalización amplia del dashboard;
- importadores masivos con plantillas;
- analítica de cumplimiento por proveedor;
- notificaciones multicanal.

### Reservadas para Fase 2

- simulador de asignación;
- *fair share*;
- tablero de capacidad;
- cubicaje;
- viajes y rutas;
- optimización.

---

## 22. Criterios de aceptación UX

- Un comprador identifica sus cinco excepciones más críticas en menos de 2 minutos.
- Puede pasar de una alerta a su cálculo, oferta y documento Valkimia sin buscar IDs manualmente.
- La fecha de cada stock y estado externo es visible.
- “Stock CD de referencia” no se confunde con SND reservado.
- Una preparación parcial muestra cantidad y saldo.
- El usuario puede distinguir regular, Venta Especial, Acuerdo y Acopio.
- No existe acción de carga regular manual.
- No existe acción de envío por SGM.
- Un rebalanceo muestra impacto en origen y destino antes de aprobar.
- Un error técnico presenta una acción segura y riesgo de duplicación.
- Cambios sensibles solicitan confirmación y motivo.
- La interfaz es utilizable con teclado y cumple contraste/accesibilidad definidos por el estándar corporativo.

---

## 23. Resultado

La interfaz convierte a Connexa en la torre de control funcional de la Fase 1. El comprador ve la posición completa y actúa únicamente cuando existe una excepción, un riesgo o un atraso. Valkimia conserva la ejecución oportunista y sus cantidades quedan reflejadas en el mismo pipeline. El diseño evita anticipar funciones de planificación inteligente que pertenecen a la Fase 2.

