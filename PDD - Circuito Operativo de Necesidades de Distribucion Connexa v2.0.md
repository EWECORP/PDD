# Circuito Operativo de Necesidades de Distribución — Connexa

Versión: **2.0**
Fecha: **2026-07-24**
Destino: Compras, Abastecimiento, Logística, Operación CD, IT, Producto y Dirección
Reemplaza: `PDD - Circuito Operativo de Planificacion Connexa v1.0.md`

---

## 1. Objetivo

Describir cómo se operará diariamente la Fase 1:

- Connexa calcula la reposición regular.
- Compras interviene solo por excepción.
- Connexa consolida y comunica las necesidades a Valkimia.
- Valkimia prepara lo que puede con el SND real.
- Connexa registra el avance y recalcula lo pendiente.
- Los rebalanceos entre sucursales siguen un circuito separado.

---

## 2. Regla operativa central

> Desde el corte, toda nueva necesidad de distribución se origina y gobierna en Connexa. SGM deja de ser un canal operativo para este módulo.

No existe período productivo con doble carga. La preparación previa al corte puede incluir pruebas, simulaciones y migración, pero no dos fuentes simultáneas para el mismo universo.

---

## 3. Día operativo

### 3.1 Cierre y captura de datos

Antes de la corrida, Connexa recibe:

- stock disponible por sucursal;
- stock CD de referencia;
- demanda/forecast/venta;
- transferencias e ingresos activos;
- maestro de artículos, proveedores, sucursales y unidades;
- parámetros de cobertura;
- estados recientes de Valkimia;
- transferencias intersucursal aprobadas y activas.

Cada fuente queda identificada por lote y fecha. Si un dato obligatorio está ausente o vencido, el ámbito afectado no se publica sin autorización.

### 3.2 Cálculo automático

Connexa calcula por sucursal-artículo:

1. stock proyectado;
2. stock objetivo del horizonte;
3. necesidad regular bruta;
4. pipeline válido que ya cubrirá la sucursal;
5. necesidad regular abierta;
6. brecha contra stock CD de referencia;
7. alertas.

El resultado del día reemplaza la foto operativa anterior. No se acumula como una nueva solicitud.

### 3.3 Incorporación de excepciones

Connexa agrega las excepciones activas según su política:

- Venta Especial;
- Acuerdo Comercial;
- Acopio.

Cada excepción conserva ID, autor, vigencia, SLA, cantidad, cumplimiento y aprobación.

### 3.4 Consolidación

Connexa genera una posición por:

```text
CD + sucursal + artículo + ventana
```

El consolidado muestra:

- necesidad regular;
- excepciones por tipo;
- total abierto;
- stock CD de referencia;
- ofrecido anteriormente aún activo;
- cantidad nueva a ofrecer;
- SLA más próximo.

### 3.5 Oferta a Valkimia

Connexa crea una oferta con referencia única y la transmite mediante el adaptador vigente.

El envío puede ser:

- automático al finalizar la corrida;
- automático dentro de una ventana;
- liberado por un supervisor durante estabilización.

Compras no crea documentos directamente en Valkimia.

### 3.6 Procesamiento oportunista

Valkimia:

- recibe el documento;
- evalúa la disponibilidad operativa real;
- prepara total o parcialmente;
- mantiene sus estados logísticos;
- informa el documento y cantidades confirmadas.

En la Fase 1, Connexa no reserva ni prorratea el SND. El hecho de ofrecer una cantidad no garantiza su preparación.

### 3.7 Seguimiento

Connexa sincroniza:

- identificador Valkimia;
- estado normalizado;
- cantidad requerida;
- cantidad confirmada/preparada;
- despacho/recepción si la fuente existe;
- fecha de actualización;
- errores o mensajes.

El comprador ve el avance sin consultar varios sistemas.

### 3.8 Cierre del día y nuevo cálculo

Las cantidades preparadas o activas quedan en el pipeline. Al día siguiente:

- se actualizan stock, demanda y movimientos;
- se descuentan ingresos/transferencias todavía válidos;
- se vuelve a calcular la necesidad;
- el saldo anterior no se suma automáticamente;
- las excepciones conservan su remanente hasta cumplir, vencer o cancelarse.

---

## 4. Ejemplo

Situación del día 1:

| Concepto | Cantidad |
| --- | ---: |
| Stock objetivo sucursal | 100 |
| Stock proyectado sucursal | 20 |
| Necesidad regular | 80 |
| Venta Especial adicional | 30 |
| Total consolidado | 110 |
| Stock CD de referencia | 70 |
| Cantidad ofrecida a Valkimia | 110 |
| Cantidad que Valkimia prepara | 60 |

Connexa no elimina las 50 unidades restantes.

En el día 2, el cálculo no hace `110 + nueva necesidad`. Vuelve a medir:

- stock actual;
- 60 unidades preparadas/en tránsito;
- demanda actualizada;
- remanente de la Venta Especial;
- nueva posición del CD.

El nuevo resultado se convierte en la única necesidad regular vigente y la Venta Especial conserva únicamente su saldo no cumplido.

---

## 5. Circuitos de excepción de Compras

### 5.1 Venta Especial

```text
Comprador registra venta y SLA
  -> validación de duplicado
  -> aprobación si supera umbral
  -> estado ACTIVE
  -> entra al consolidado
  -> preparación se imputa a la venta
  -> fulfilled / partial / expired
```

Reglas:

- Debe tener fecha objetivo.
- La modificación posterior a aprobación queda auditada.
- Si el SLA vence con saldo, se genera alerta.
- No se crea una reposición regular manual paralela.

### 5.2 Acuerdo Comercial

```text
Comprador registra proveedor, artículos, destinos y vigencia
  -> validación
  -> aprobación
  -> materialización de líneas
  -> aplicación diaria durante vigencia
  -> seguimiento de cumplimiento
```

Reglas:

- La fecha de fin es obligatoria.
- Debe definirse si es adicional, mínimo garantizado o reemplazo.
- Se debe poder ver cumplimiento acumulado por proveedor y sucursal.

### 5.3 Acopio

```text
Comprador registra cantidad, destino, motivo y fecha
  -> aprobación según umbral
  -> consolidación
  -> cumplimiento parcial/total
  -> cierre
```

Reglas:

- No debe quedar activo sin vigencia.
- El acopio vencido no continúa generando necesidad.
- Cancelar requiere motivo.

---

## 6. Transferencia intersucursal

### 6.1 Propósito

Rebalancear stock sin pasar por el CD.

### 6.2 Flujo

```text
Comprador detecta exceso/quiebre
  -> selecciona sucursal origen
  -> selecciona sucursal destino
  -> artículo, cantidad y SLA
  -> Connexa muestra impacto proyectado
  -> aprobación
  -> pendiente de coordinación logística
  -> preparación en origen
  -> despacho
  -> recepción en destino
  -> cierre
```

### 6.3 Reglas

- Origen y destino deben ser distintos.
- No se publica en el consolidado del CD.
- El origen no debería quedar bajo su stock protegido.
- Una excepción autorizada debe indicar quién aprobó y por qué.
- Al aprobar, la cantidad se incorpora al pipeline proyectado de ambas sucursales.
- Cancelar libera el pipeline.
- Logística es responsable de la ejecución; Compras define la necesidad.

---

## 7. Gestión por el comprador

### 7.1 Inicio de jornada

El comprador abre su panel con filtros persistidos de proveedores/familias.

Revisa:

- alertas críticas;
- sucursales con riesgo de quiebre;
- stock CD insuficiente;
- Ventas Especiales/Acuerdos/Acopios próximos a SLA;
- ofertas sin avance;
- preparación parcial;
- rebalanceos pendientes.

### 7.2 Acciones permitidas

- Analizar detalle y explicación del cálculo.
- Crear o modificar una excepción dentro de sus permisos.
- Solicitar un rebalanceo.
- Agregar comentario o responsable a una alerta.
- Escalar atraso de proveedor/CD/logística.
- Exportar o compartir una vista.

### 7.3 Acciones no permitidas

- Cargar reposiciones regulares.
- Crear otra fuente en SGM.
- Publicar directamente a Valkimia.
- Cambiar un estado logístico sin evidencia.
- Duplicar un documento para “forzar” un reintento.
- Modificar stock de origen.

---

## 8. Estados funcionales

### 8.1 Necesidad regular

La necesidad regular se expresa principalmente por cantidades y alertas, porque se reemplaza cada día.

Estados sugeridos:

- `CALCULATED`
- `OFFER_PENDING`
- `OFFERED`
- `IN_PIPELINE`
- `PARTIALLY_COVERED`
- `COVERED`
- `DATA_BLOCKED`

### 8.2 Excepción

- `DRAFT`
- `PENDING_APPROVAL`
- `ACTIVE`
- `PARTIALLY_FULFILLED`
- `FULFILLED`
- `EXPIRED`
- `CANCELLED`

### 8.3 Oferta/Valkimia

- `OFFER_PENDING`
- `OFFER_SENT`
- `VKM_RECEIVED`
- `VKM_IN_PROCESS`
- `VKM_PREPARED_PARTIAL`
- `VKM_PREPARED`
- `VKM_DISPATCHED`
- `VKM_CANCELLED`
- `TECHNICAL_ERROR`
- `UNKNOWN_EXTERNAL_STATUS`

### 8.4 Intersucursal

- `DRAFT`
- `PENDING_APPROVAL`
- `APPROVED`
- `REJECTED`
- `PENDING_LOGISTICS`
- `IN_PREPARATION`
- `DISPATCHED`
- `RECEIVED`
- `CANCELLED`

---

## 9. Tratamiento de incidentes

### 9.1 Valkimia no responde al publicar

1. La oferta queda `TECHNICAL_ERROR` o `UNKNOWN_RESULT`.
2. Connexa consulta por referencia externa antes de reintentar.
3. Si existe, vincula el documento.
4. Si no existe, reenvía con la misma referencia.
5. Compras ve la alerta, pero no crea otro documento.

### 9.2 Estado externo desconocido

1. Se conserva el valor original.
2. Se mapea temporalmente a `UNKNOWN_EXTERNAL_STATUS`.
3. IT recibe alerta.
4. No se infiere cumplimiento.
5. El administrador actualiza el mapping con auditoría.

### 9.3 Preparación parcial

1. Se registra cantidad confirmada.
2. Se imputa según SLA/prioridad/origen.
3. Se muestra el saldo.
4. El siguiente cálculo considera el pipeline.
5. No se duplica la oferta en forma manual.

### 9.4 Datos diarios incompletos

1. Se identifica el ámbito afectado.
2. Se bloquea su nueva oferta o se usa modo degradado autorizado.
3. Se muestra la fecha del último dato válido.
4. Se registra la decisión.
5. Se recalcula cuando la fuente se restablece.

### 9.5 Error durante el Big‑Bang

1. Se mantiene a Connexa como registro único.
2. Se activa la cola/procedimiento de contingencia.
3. Todo envío conserva la referencia Connexa.
4. Se reconcilia al recuperar la integración.
5. No se reabre SGM salvo decisión ejecutiva formal.

---

## 10. RACI

Referencias: R = ejecuta; A = responsable final; C = consultado; I = informado.

| Actividad | Connexa | Compras | Supervisor | Valkimia | Operación CD | Logística | IT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Capturar datos diarios | R | I | I | C | I | I | A/R |
| Calcular necesidad regular | R/A | C | I | I | I | I | C |
| Revisar alertas de abastecimiento | C | R/A | C | I | I | I | I |
| Crear Venta Especial | R | R/A | C/A según umbral | I | I | I | I |
| Crear Acuerdo Comercial | R | R | A | I | I | I | I |
| Crear Acopio | R | R | A según umbral | I | I | C | I |
| Consolidar necesidad | R/A | I | I | I | I | I | C |
| Publicar oferta | R/A | I | I | C | I | I | C |
| Decidir cantidad procesable | I | I | I | R/A | C | I | I |
| Preparar mercadería | I | I | I | A | R | I | I |
| Informar estado/cantidad | C | I | I | R/A | C | I | C |
| Gestionar atraso comercial | C | R/A | C | C | C | C | I |
| Solicitar intersucursal | R | R/A | C | I | I | C | I |
| Aprobar intersucursal | C | R | A | I | I | C | I |
| Ejecutar intersucursal | I | I | I | I | C | R/A | I |
| Resolver error técnico | C | I | I | C | I | I | R/A |
| Mantener parámetros | R | C | A | C | C | C | C |
| Autorizar Go/No-Go | C | C | A | C | C | C | C |

---

## 11. Controles diarios

### Control automático

- fuentes recibidas y frescas;
- una foto vigente por ámbito;
- cero duplicados de referencia;
- ofertas sin documento externo;
- documentos sin actualización;
- cantidades confirmadas superiores a ofrecidas;
- estados sin mapping;
- excepciones vencidas;
- pipeline duplicado;
- SGM rechazado como origen posterior al corte.

### Control de Compras

- top de quiebres;
- SLA vencidos;
- necesidades con stock CD cero;
- preparaciones parciales;
- acuerdos próximos a vencer;
- rebalanceos pendientes.

### Control IT

- latencia y error por interfaz;
- colas y reintentos;
- diferencias de conteos;
- trabajos diarios fallidos;
- lotes pendientes de procesar.

---

## 12. Indicadores operativos

- necesidad regular total;
- excepciones activas por tipo;
- backlog por proveedor/sucursal/artículo;
- porcentaje preparado sobre ofrecido;
- porcentaje de preparación parcial;
- tiempo oferta -> recepción Valkimia;
- tiempo recepción -> preparado;
- SLA cumplido de excepciones;
- artículos/sucursales con riesgo de quiebre;
- stock CD de referencia insuficiente;
- documentos estancados;
- rebalanceos por estado y SLA;
- incidencias técnicas;
- uso posterior al corte originado en SGM — objetivo cero.

---

## 13. Checklist de corte

### Antes

- [ ] Alcance exacto de artículos, sucursales y CD definido.
- [ ] Fecha/hora aprobadas.
- [ ] Fórmula y fuentes validadas.
- [ ] Usuarios y permisos cargados.
- [ ] Funciones SGM deshabilitables confirmadas.
- [ ] Pendientes inventariados y clasificados.
- [ ] Contrato Valkimia probado.
- [ ] Referencia idempotente probada.
- [ ] Mapping de estados probado.
- [ ] Contingencia ensayada.
- [ ] Mesa de ayuda y responsables comunicados.

### Durante

- [ ] Congelamiento aplicado.
- [ ] Último extracto recibido.
- [ ] Inventario inicial cargado y conciliado.
- [ ] SGM bloqueado para el módulo.
- [ ] Primera corrida finalizada.
- [ ] Primera oferta vinculada en Valkimia.
- [ ] Cantidades y conteos validados.

### Después

- [ ] Monitoreo intensivo activo.
- [ ] Revisión diaria de excepciones.
- [ ] Cero nuevas altas desde SGM.
- [ ] Documentos sin estado investigados.
- [ ] Backlog explicado.
- [ ] Revisión de estabilización y decisión de salida de hiper‑cuidado.

---

## 14. Resultado operativo

El proceso diario deja de depender de que el comprador cargue reposiciones y compare manualmente sistemas. Connexa calcula y muestra la posición; Compras actúa donde existe una excepción o desvío; Valkimia prepara lo que realmente puede; y el siguiente cálculo mantiene actualizada la necesidad sin duplicarla. El circuito intersucursal permite rebalancear stock sin mezclarlo con la operación del CD.

