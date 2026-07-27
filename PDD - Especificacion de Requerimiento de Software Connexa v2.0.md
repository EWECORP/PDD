# Especificación de Requerimiento de Software

Sistema: **Módulo de Necesidades de Distribución — Connexa**
Versión: **2.0**
Fecha: **2026-07-24**
Estado: **Base para refinamiento técnico, historias y estimación**
Reemplaza: `PDD - Especificacion de Requerimiento de Software Connexa v1.0.md`

---

## 1. Propósito

Definir los requerimientos para que Connexa:

- calcule diariamente necesidades regulares de distribución;
- permita registrar excepciones de Compras;
- consolide necesidades CD -> sucursal;
- las comunique a Valkimia mediante el mecanismo disponible;
- reciba estados y cantidades preparadas;
- mantenga un backlog recalculado y trazable;
- ofrezca una visión de stock y pipeline por proveedor, sucursal y artículo;
- registre solicitudes intersucursal fuera del CD.

La solución entrará en producción con un corte Big‑Bang: SGM no será origen, editor ni publicador dentro del alcance.

---

## 2. Alcance

### 2.1 Incluido

- Integración de fuentes de demanda, inventario, tránsito y maestros.
- Cálculo batch diario de necesidad regular.
- Versionado de cada foto de cálculo.
- Venta Especial con fecha objetivo y SLA.
- Acuerdo Comercial con período de vigencia.
- Acopio con fecha requerida y vigencia.
- Consolidación sin duplicar demanda regular y excepcional.
- Oferta de necesidades a Valkimia.
- Tracking de documento y cantidades confirmadas/preparadas.
- Recálculo del remanente.
- Panel de Compras y alertas.
- Requerimientos de transferencia intersucursal.
- Auditoría funcional y monitoreo técnico.
- Carga inicial de pendientes al corte.
- Adaptadores intercambiables para Valkimia actual y WEB.

### 2.2 Excluido

- Ingreso de necesidades desde SGM después del corte.
- Doble publicación o reconciliación continua de dos orígenes.
- Asignación/prorrateo central de SND.
- Optimización de cargas, camiones, rutas o cubicaje.
- Reserva de stock en Valkimia.
- Migración obligatoria a la versión WEB.
- Sustitución integral de SGM.
- Gestión contable o fiscal de transferencias.

---

## 3. Glosario

| Término | Definición |
| --- | --- |
| Need regular | Resultado vigente del cálculo diario para una sucursal-artículo |
| Exception need | Necesidad persistente cargada por Venta Especial, Acuerdo Comercial o Acopio |
| Calculation run | Corrida diaria identificada, fechada y auditada |
| Snapshot | Foto de datos y resultados de una corrida |
| Distribution offer | Consolidado CD -> sucursal enviado o puesto a disposición de Valkimia |
| Offer line | Línea por sucursal-artículo dentro de una oferta |
| Prepared quantity | Cantidad confirmada por Valkimia como preparada |
| Pipeline | Cantidades ofrecidas, en proceso, preparadas, despachadas, en tránsito o recibidas |
| Backlog | Cantidad vigente aún requerida y no cubierta por el pipeline válido |
| SND | Stock Neto Disponible que Valkimia usa al decidir qué puede preparar |
| CD reference stock | Stock conocido por Connexa; no necesariamente equivale al SND |
| Branch transfer request | Solicitud de transferencia entre sucursales, sin paso por CD |
| SLA | Fecha/hora comprometida o límite esperado |
| Big‑Bang | Corte único desde el cual el módulo opera solamente en Connexa |

---

## 4. Actores y responsabilidades

| Actor/Sistema | Responsabilidad |
| --- | --- |
| Comprador | Opera por excepción, analiza stock/pipeline y gestiona alertas |
| Supervisor de Compras | Aprueba excepciones definidas, cambios sensibles y rebalanceos |
| Connexa | Fuente única de necesidades, backlog, oferta, estado funcional y auditoría |
| Valkimia | Toma lo procesable, prepara y devuelve estados/cantidades |
| Operación CD | Ejecuta preparación, incidencias y despacho en Valkimia |
| Logística | Ejecuta/coordina transferencias intersucursal y transporte |
| Sucursal | Destino de mercadería y eventual fuente de recepción |
| IT Integraciones | Opera adaptadores, sincronización, reintentos y monitoreo |
| Administrador | Mantiene parámetros, mappings, permisos y calendarios |
| SGM | Sin responsabilidad operativa en el nuevo módulo después del corte |

---

## 5. Vista general

```text
Datos diarios
  -> CalculationRun
  -> RegularNeedSnapshot
  -> Need vigente
           + ExceptionNeed
  -> DistributionOffer
  -> Adaptador Valkimia
  -> OfferExecutionStatus / PreparedQuantity
  -> Pipeline y panel
  -> nuevo cálculo diario

BranchTransferRequest
  -> aprobación
  -> ejecución logística
  -> despacho/recepción
  -> pipeline origen y destino
```

La unidad principal de trazabilidad es:

```text
sucursal + artículo + necesidad/origen + cantidad + fecha
```

---

## 6. Requerimientos funcionales

### 6.1 Datos y cálculo diario

#### RF-001. Ejecutar corrida diaria

El sistema debe ejecutar una corrida automática diaria y permitir relanzarla de forma controlada.

Criterios:

- Cada corrida tendrá `calculation_run_id`, fecha operativa, inicio, fin, estado y versión de fórmula.
- Solo una versión podrá quedar vigente para una fecha y ámbito.
- Un relanzamiento no sumará cantidades al resultado anterior.
- Los resultados anteriores quedarán disponibles para auditoría.

#### RF-002. Validar frescura de fuentes

Antes de calcular, Connexa debe validar la disponibilidad y frescura de:

- stock sucursal;
- stock CD de referencia;
- demanda/forecast o consumo;
- transferencias/ingresos activos;
- maestro artículo-sucursal-proveedor;
- parámetros de cobertura.

Criterios:

- Cada fuente tendrá timestamp, lote y estado.
- Una fuente obligatoria ausente detendrá el ámbito afectado.
- Una fuente opcional ausente activará modo degradado y alerta.
- El resultado indicará qué fuentes se utilizaron.

#### RF-003. Calcular stock proyectado de sucursal

El sistema debe calcular:

```text
stock_proyectado =
  stock_disponible
  + inbound_pipeline_valido
  - compromisos_confirmados
```

Los componentes y la política de inclusión deben ser configurables.

#### RF-004. Calcular necesidad regular

El sistema debe calcular una necesidad regular por sucursal-artículo según fórmula versionada.

Criterios:

- La necesidad nunca será negativa.
- Debe conservar demanda, stock, cobertura, tránsito y parámetros usados.
- Debe distinguir necesidad bruta, pipeline descontado y necesidad abierta.
- Debe aplicar múltiplos/unidades logísticas según configuración.
- El stock CD de referencia debe quedar visible aunque sea cero o esté desactualizado.

#### RF-005. No ocultar demanda por falta de stock CD

El sistema no debe eliminar la necesidad bruta cuando el stock CD sea insuficiente.

Debe exponer:

- necesidad vigente;
- stock CD de referencia;
- brecha contra stock CD;
- indicador `CD_STOCK_LOW`, `CD_STOCK_ZERO`, `CD_STOCK_STALE` o equivalente.

#### RF-006. Reemplazar la foto regular

El resultado vigente del cálculo regular debe reemplazar el resultado operativo anterior del mismo ámbito.

Criterios:

- El historial será inmutable.
- El panel utilizará solo la versión vigente.
- Las ofertas y ejecuciones históricas conservarán su vínculo con la versión que las originó.
- No se duplicará la necesidad por relanzar una corrida.

#### RF-007. Explicabilidad

Para cada necesidad regular, el sistema debe mostrar:

- fórmula aplicada;
- valores de entrada;
- parámetros;
- pipeline descontado;
- redondeos;
- alertas de calidad;
- resultado.

### 6.2 Necesidades excepcionales

#### RF-010. Registrar Venta Especial

El comprador debe poder crear una Venta Especial.

Campos mínimos:

- `special_sale_id`;
- sucursal;
- artículo;
- cantidad;
- fecha/hora objetivo;
- SLA;
- referencia comercial;
- prioridad;
- observación;
- creador y timestamps.

#### RF-011. Registrar Acuerdo Comercial

El comprador debe poder crear un acuerdo con:

- proveedor;
- artículo(s);
- sucursal(es) o agrupador;
- cantidad o regla;
- inicio y fin de vigencia;
- fecha/SLA de llegada;
- referencia;
- prioridad.

El sistema deberá materializar líneas trazables por sucursal-artículo antes de consolidar.

#### RF-012. Registrar Acopio

El comprador debe poder registrar:

- destino;
- artículo;
- cantidad;
- motivo;
- fecha requerida;
- vigencia;
- prioridad.

#### RF-013. Administrar ciclo de excepción

Estados mínimos:

- `DRAFT`
- `PENDING_APPROVAL`
- `ACTIVE`
- `PARTIALLY_FULFILLED`
- `FULFILLED`
- `EXPIRED`
- `CANCELLED`

Toda modificación de cantidad, destino, fecha o vigencia debe auditarse.

#### RF-014. Evitar duplicados de excepción

El sistema debe advertir coincidencias por tipo, referencia, sucursal, artículo y período.

La advertencia no reemplaza la identidad única. Solo un usuario autorizado podrá confirmar un posible duplicado con justificación.

#### RF-015. Combinar excepción y cálculo regular

La política será configurable por tipo:

- `ADDITIVE`: se agrega a la necesidad regular.
- `MINIMUM_GUARANTEE`: eleva el total hasta un mínimo.
- `REPLACE`: reemplaza la necesidad regular para el período indicado.

La política aplicada debe quedar visible y versionada.

### 6.3 Consolidación y oferta a Valkimia

#### RF-020. Construir necesidad consolidada

Connexa debe consolidar por CD, sucursal, artículo y ventana, sin perder el detalle de origen.

Criterios:

- Cada cantidad consolidada debe poder distribuirse hacia sus fuentes.
- Debe respetar vigencias y SLA.
- Debe excluir canceladas, vencidas y ya cubiertas.
- Debe evitar sumar el mismo pipeline más de una vez.

#### RF-021. Crear oferta

El sistema debe crear una `distribution_offer` por lote y `distribution_offer_line` por sucursal-artículo.

Campos mínimos:

- ID interno y referencia externa estable;
- CD y sucursal;
- fecha operativa;
- fecha objetivo;
- cantidad ofrecida;
- estado;
- vínculo a fuentes;
- versión del cálculo;
- adaptador de destino.

#### RF-022. Publicar por adaptador

El sistema debe publicar mediante una interfaz interna independiente de Valkimia.

Criterios:

- El adaptador actual podrá mapear a alta individual o masiva de documento de salida.
- El adaptador WEB podrá incorporarse sin modificar las reglas de negocio.
- Request y response se almacenarán con datos sensibles protegidos.
- Los errores técnicos quedarán reintentables.

#### RF-023. Garantizar identidad e idempotencia

Reenviar la misma oferta no debe crear un segundo documento funcional.

La solución debe utilizar, en este orden:

1. idempotencia nativa si el contrato la ofrece;
2. referencia externa única consultable;
3. tabla de correspondencia y consulta previa;
4. bloqueo transaccional local.

#### RF-024. No asignar stock en Connexa

En la Fase 1, Connexa no decidirá el prorrateo de SND entre sucursales.

El sistema podrá:

- ordenar líneas por SLA/prioridad para su presentación;
- mostrar factibilidad estimada;
- ofrecer el consolidado.

No deberá:

- reservar SND;
- garantizar que lo ofrecido será preparado;
- redistribuir automáticamente stock escaso.

#### RF-025. Manejar publicación parcial técnica

Si un lote contiene líneas aceptadas y fallidas:

- cada línea conservará estado independiente;
- solo se reintentará la parte no confirmada;
- se mantendrá la misma referencia funcional;
- no se recrearán líneas ya recibidas por Valkimia.

### 6.4 Tracking y backlog

#### RF-030. Consultar estado Valkimia

Connexa debe obtener el estado de cada documento publicado usando el mecanismo disponible.

Criterios:

- Polling configurable en Fase 1.
- Consulta puntual bajo permiso.
- Procesamiento incremental de documentos finalizados si está disponible.
- Mapeo externo/interno parametrizable.

#### RF-031. Registrar cantidades por línea

El sistema debe registrar, cuando estén disponibles:

- requerida;
- confirmada/preparada;
- despachada;
- recibida;
- cancelada/rechazada.

Debe conservar el valor recibido, unidad, timestamp y fuente.

#### RF-032. Interpretar preparación parcial

Cuando `qty_prepared < qty_offered`, el saldo seguirá visible como pendiente hasta el próximo recálculo o cierre.

No se debe crear automáticamente una segunda oferta dentro de la misma ventana salvo regla explícita y control idempotente.

#### RF-033. Recalcular backlog regular

El nuevo cálculo diario debe incluir el pipeline válido para evitar volver a pedir cantidades ya comprometidas.

El remanente del documento anterior se usará como evidencia, no como suma automática, salvo que la fórmula de negocio lo defina expresamente.

#### RF-034. Calcular backlog de excepción

Para una excepción:

```text
exception_backlog =
  qty_exception
  - qty_fulfilled_allocated
  - qty_cancelled
```

La asignación de una cantidad preparada a sus fuentes seguirá una regla determinística y auditable, por defecto:

1. excepción con SLA vencido o más próximo;
2. excepción con mayor prioridad;
3. excepción más antigua;
4. necesidad regular.

Esta regla de imputación no constituye prorrateo logístico entre sucursales.

#### RF-035. Detectar estados estancados

El sistema debe alertar documentos o líneas sin actualización por encima del umbral configurado según estado.

#### RF-036. Procesar cancelaciones

Una cancelación en Valkimia:

- no borrará la necesidad;
- liberará la cantidad del pipeline;
- dejará motivo y evento;
- permitirá que el próximo cálculo la reevalúe.

### 6.5 Panel de Compras

#### RF-040. Proveer vista multidimensional

El panel debe permitir agrupar y filtrar por:

- proveedor;
- sucursal;
- artículo;
- familia/categoría;
- comprador;
- CD;
- estado de pipeline;
- tipo de necesidad;
- SLA;
- nivel de cobertura;
- severidad de alerta.

#### RF-041. Mostrar posición integral

Cada fila debe mostrar:

- stock sucursal y fecha;
- cobertura/días de stock;
- stock CD de referencia y fecha;
- demanda/horizonte;
- necesidad regular;
- excepciones;
- ofrecido;
- en proceso;
- preparado;
- despachado/en tránsito;
- recibido, si existe;
- backlog;
- SLA más exigente;
- última actualización;
- alerta y próxima acción.

#### RF-042. Gestionar por excepción

Desde el panel, el comprador podrá:

- abrir detalle;
- registrar Venta Especial, Acuerdo Comercial o Acopio;
- solicitar transferencia intersucursal;
- reconocer/asignar una alerta;
- agregar comentario;
- exportar información autorizada.

No podrá crear reposición regular manual ni publicar directamente a Valkimia.

#### RF-043. Alertar bajo stock y atraso

Alertas mínimas:

- sucursal bajo mínimo o con riesgo de quiebre;
- stock CD insuficiente para la necesidad visible;
- SLA próximo o vencido;
- oferta no recibida por Valkimia;
- documento sin avance;
- preparación parcial;
- fuente de datos desactualizada;
- transferencia intersucursal atrasada.

### 6.6 Transferencias intersucursal

#### RF-050. Crear solicitud intersucursal

Campos mínimos:

- origen y destino;
- artículo;
- cantidad;
- fecha requerida/SLA;
- motivo;
- prioridad;
- solicitante;
- evidencia/comentario.

Debe validarse que origen y destino sean distintos.

#### RF-051. Evaluar stock del origen

El sistema debe mostrar stock disponible y proyectado de la sucursal origen. La aprobación no debe permitir una cantidad superior al máximo definido por política sin autorización especial.

#### RF-052. Administrar estados

Estados mínimos:

- `DRAFT`
- `PENDING_APPROVAL`
- `APPROVED`
- `REJECTED`
- `PENDING_LOGISTICS`
- `IN_PREPARATION`
- `DISPATCHED`
- `RECEIVED`
- `CANCELLED`

#### RF-053. Mantener circuito separado

La solicitud intersucursal:

- no generará oferta CD -> sucursal;
- no será publicada a Valkimia CD salvo integración futura específica;
- sí integrará la visión de pipeline y stock proyectado;
- tendrá auditoría y responsables propios.

### 6.7 Corte, auditoría y administración

#### RF-060. Cargar inventario inicial

El sistema debe permitir una carga única y controlada de pendientes del corte.

Criterios:

- lote identificado;
- conteos de origen y destino;
- clasificación por estado;
- rechazo de duplicados;
- reporte de conciliación;
- aprobación de negocio.

#### RF-061. Bloquear origen SGM

Las interfaces del módulo no deben aceptar nuevas necesidades con `source_system=SGM` después del timestamp de corte.

Los registros históricos conservarán su origen para consulta.

#### RF-062. Auditar eventos

Toda alta, cálculo, modificación, aprobación, publicación, respuesta, estado, comentario y cancelación debe generar un evento append-only.

#### RF-063. Parametrizar

Parámetros mínimos:

- frecuencia y calendario;
- fórmula/horizonte;
- cobertura/stock objetivo;
- múltiplos;
- políticas de excepción;
- mapping de estados;
- intervalos de polling;
- umbrales de alertas;
- regla de imputación;
- permisos;
- fecha de corte.

#### RF-064. Operar contingencia

El sistema debe soportar cola de salida y envío manual controlado sin crear una segunda fuente de necesidad.

Toda contingencia debe reutilizar la referencia de Connexa y reconciliarse después.

---

## 7. Modelo de datos lógico

Entidades mínimas:

| Entidad | Propósito |
| --- | --- |
| `calculation_run` | Cabecera de corrida y estado |
| `calculation_source_snapshot` | Lotes/frescura de entradas |
| `regular_need_snapshot` | Resultado histórico por corrida |
| `current_distribution_need` | Vista/materialización vigente |
| `exception_need` | Cabecera de excepción |
| `exception_need_line` | Artículo-sucursal-vigencia |
| `need_source_allocation` | Descomposición del consolidado |
| `distribution_offer` | Lote/cabecera publicado |
| `distribution_offer_line` | Línea sucursal-artículo |
| `offer_external_reference` | Correspondencia Connexa-Valkimia |
| `offer_status_event` | Estados y cantidades externas |
| `branch_transfer_request` | Cabecera intersucursal |
| `branch_transfer_line` | Líneas de rebalanceo |
| `business_event_log` | Auditoría funcional |
| `integration_message` | Request/response/reintento técnico |
| `configuration_version` | Parámetros versionados |

Restricciones:

- UUID interno para entidades.
- Referencia externa única por oferta.
- `numeric(18,4)` para cantidades.
- cantidades no negativas;
- vigencia `from <= to`;
- origen y destino intersucursal diferentes;
- una sola foto vigente por ámbito;
- eventos append-only;
- timestamps en UTC y presentación en zona local.

No se requiere `external_execution` para convivencia con SGM. Los documentos migrados al corte se identifican mediante `migration_batch_id`.

---

## 8. Interfaces

### IF-01. Entradas de datos diarios

Contrato lógico:

```text
source
batch_id
as_of_ts
cd_id
branch_id
item_id
stock_qty / demand_qty / inbound_qty / parameter values
```

Se definirá si cada fuente se integra por base, archivo, servicio o API.

### IF-02. Publicación a Valkimia

Contrato interno:

```text
publishDistributionOffer(offer)
  -> external_document_id
  -> accepted/status
  -> line_results
  -> messages
```

El adaptador actual deberá mapear los campos reales, incluyendo tipo de documento, operación, depósito, destino, artículo, cantidad, fecha y referencia externa.

### IF-03. Tracking Valkimia

Contrato interno:

```text
getDistributionStatus(external_document_id)
  -> normalized_status
  -> lines[item, requested_qty, confirmed_qty]
  -> last_update_ts
  -> messages
```

### IF-04. Documentos finalizados

Cuando exista, Connexa podrá consultar documentos finalizados no procesados, registrarlos y confirmar su procesamiento solo después de persistirlos correctamente.

### IF-05. Stock Neto Disponible opcional

La Fase 1 no depende de esta interfaz. Si se habilita:

```text
getNetAvailableStock(cd_id, item_ids)
```

se usará para mejorar visibilidad y factibilidad, sin convertir a Connexa en asignador logístico.

### IF-06. Versión WEB futura

Deberá implementar los mismos contratos internos con un adaptador nuevo. El cambio de adaptador requerirá pruebas de contrato y no migración del dominio.

---

## 9. Requerimientos no funcionales

### RNF-01. Idempotencia

Corridas, publicaciones, tracking y carga inicial deben poder reejecutarse sin duplicar efectos.

### RNF-02. Trazabilidad

Debe reconstruirse el camino:

```text
dato fuente -> cálculo -> necesidad -> oferta -> documento Valkimia
-> cantidad preparada -> backlog/pipeline
```

### RNF-03. Rendimiento

Objetivos iniciales a validar con volumen:

- cálculo diario completo dentro de la ventana acordada;
- panel inicial en menos de 5 segundos para filtros habituales;
- detalle en menos de 3 segundos;
- publicación por lotes compatibles con límites Valkimia;
- exportaciones grandes mediante proceso asíncrono.

### RNF-04. Disponibilidad y recuperación

- Fallas de Valkimia no perderán necesidades.
- Los mensajes permanecerán en cola reintentable.
- Reiniciar un worker no duplicará documentos.
- Debe existir recuperación desde último estado persistido.

### RNF-05. Seguridad

Control por roles, mínimo privilegio, auditoría de cambios, protección de payloads y separación de permisos de crear/aprobar/publicar.

### RNF-06. Observabilidad

Métricas mínimas:

- frescura de fuentes;
- duración y resultado de corridas;
- necesidades y ofertas por estado;
- latencia/error del adaptador;
- reintentos;
- documentos sin actualización;
- diferencias de cantidades;
- backlog y SLA.

### RNF-07. Usabilidad

La interfaz debe operar por excepción, conservar filtros, permitir navegación al detalle y explicar cantidades/estados sin requerir consulta técnica.

### RNF-08. Configurabilidad

Reglas funcionales modificables por configuración versionada, con vigencia y aprobación.

### RNF-09. Calidad de datos

Los datos inválidos se aislarán por línea. El sistema no publicará artículos, sucursales o unidades sin correspondencia válida.

### RNF-10. Desacople

No se admitirán reglas de negocio dentro del adaptador Valkimia ni referencias a estructuras externas dentro del dominio.

---

## 10. Reglas de negocio críticas

| ID | Regla |
| --- | --- |
| RN-01 | Connexa es el único origen después del corte |
| RN-02 | SGM no tiene convivencia operativa |
| RN-03 | La foto regular vigente se reemplaza, no se acumula |
| RN-04 | Una excepción tiene identidad y vigencia propias |
| RN-05 | Falta de stock CD no borra la necesidad |
| RN-06 | Valkimia decide cuánto puede preparar en Fase 1 |
| RN-07 | Cantidades activas del pipeline no vuelven a pedirse |
| RN-08 | Cancelaciones liberan pipeline, no eliminan necesidad |
| RN-09 | Toda oferta tiene referencia estable |
| RN-10 | Transferencias intersucursal no pasan por el CD |
| RN-11 | Compras no publica directamente a Valkimia |
| RN-12 | Fase 2 no forma parte de la aceptación de Fase 1 |

---

## 11. Casos de uso principales

### CU-01. Calcular necesidades diarias

1. Validar fuentes.
2. Crear corrida.
3. Calcular stock proyectado y necesidad.
4. Descontar pipeline válido.
5. Publicar nueva foto vigente.
6. Generar alertas.

### CU-02. Registrar Venta Especial

1. Comprador ingresa datos y SLA.
2. Sistema valida duplicados y política.
3. Se solicita aprobación si corresponde.
4. La excepción activa entra al consolidado.

### CU-03. Enviar consolidado a Valkimia

1. Connexa crea oferta con referencia.
2. Adaptador valida mappings.
3. Publica o encola.
4. Persiste referencia/respuesta.
5. Actualiza panel.

### CU-04. Valkimia prepara parcialmente

1. Tracking informa cantidad confirmada menor.
2. Connexa registra evento por línea.
3. Imputa cantidad a fuentes.
4. Mantiene saldo visible.
5. El cálculo siguiente evita duplicar pipeline y reevalúa el remanente.

### CU-05. Solicitar rebalanceo

1. Comprador selecciona origen, destino y artículo.
2. Sistema muestra impacto en ambos stocks.
3. Supervisor aprueba/rechaza.
4. Logística ejecuta.
5. Despacho y recepción actualizan pipeline.

### CU-06. Gestionar atraso

1. Panel genera alerta.
2. Comprador abre detalle y timeline.
3. Asigna/escala la acción.
4. Sistema conserva responsable, comentario y resolución.

---

## 12. Criterios de aceptación del MVP

El MVP se acepta cuando:

1. Una corrida diaria completa produce una sola foto vigente y es reejecutable.
2. La necesidad puede explicarse con sus datos y fórmula.
3. Un comprador registra los tres tipos de excepción.
4. Las excepciones no duplican silenciosamente la necesidad regular.
5. Connexa publica una oferta con referencia única y un reintento no duplica.
6. Se visualizan estado y cantidad confirmada/preparada por línea.
7. Una preparación parcial deja saldo visible.
8. El cálculo del día siguiente no vuelve a pedir pipeline activo.
9. El panel filtra por proveedor, sucursal y artículo.
10. Las alertas de SLA, bajo stock y estancamiento son accionables.
11. Se registra y sigue una transferencia intersucursal separada del CD.
12. SGM no puede ingresar nuevas necesidades después del corte.
13. Toda entidad tiene timeline de auditoría.
14. La caída del adaptador no pierde ni duplica ofertas.
15. Los conteos del inventario inicial concilian con el acta de corte.

---

## 13. Pruebas mínimas

### Datos

- fuente ausente/desactualizada;
- artículo sin mapping;
- stock negativo;
- múltiplos y redondeos;
- pipeline duplicado;
- relanzamiento de corrida.

### Negocio

- necesidad regular con/sin stock CD;
- cada política de excepción;
- excepción vencida/cancelada;
- consolidación de varias fuentes;
- preparación total, parcial y nula;
- cancelación Valkimia;
- intersucursal aprobada/rechazada.

### Integración

- alta individual y lista;
- timeout antes/después de respuesta;
- respuesta ambigua;
- reintento idempotente;
- consulta por ID/referencia;
- mapping de cada estado real;
- cantidades confirmadas;
- marcado de finalizado procesado.

### Corte

- carga inicial repetida;
- pendientes duplicados;
- bloqueo de SGM;
- contingencia de publicación;
- conciliación posterior.

### Seguridad y UX

- permisos por rol;
- aprobación segregada;
- exportación;
- filtros y tiempos;
- auditoría de cambios.

---

## 14. Dependencias y decisiones abiertas

| Tema | Responsable sugerido | Bloquea |
| --- | --- | --- |
| Fórmula/horizonte regular | Compras + Datos | Construcción del cálculo |
| Fuentes y SLA de datos | Datos + IT | Integración |
| Política por excepción | Compras | Consolidación |
| Aprobaciones | Negocio | Workflow |
| Contrato Valkimia real | Valkimia + IT | Adaptador |
| Mapping de estados | Operación CD + Valkimia | Tracking |
| Idempotencia viable | Arquitectura + Valkimia | Productivo |
| Fuente de recepción | Logística + IT | Pipeline completo |
| Fecha/universo del corte | Sponsor + Operación | Go-live |
| Estados intersucursal | Compras + Logística | Circuito |

---

## 15. Evolución a Fase 2

La arquitectura deberá permitir incorporar, sin redefinir Need/Offer/Event:

- SND en tiempo cercano a real;
- asignación de stock;
- score y *fair share*;
- reservas;
- simulación;
- capacidad, peso, volumen y pallets;
- consolidación por viaje;
- ruteo y optimización;
- eventos WEB.

Estas capacidades se mantendrán como épicas separadas y no condicionarán el cierre del MVP.

