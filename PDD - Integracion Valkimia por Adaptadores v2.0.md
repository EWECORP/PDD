# Integración Valkimia por Adaptadores

Versión: **2.0**
Fecha: **2026-07-24**
Estado: **Diseño lógico; contrato técnico sujeto a validación con Valkimia**

---

## 1. Objetivo

Permitir que la Fase 1 opere con la integración disponible y que la futura migración WEB cambie la tecnología sin cambiar el dominio de Connexa.

---

## 2. Principio

```text
Dominio Connexa
  -> Puerto estable
  -> Adaptador Valkimia instalado

Dominio Connexa
  -> mismo puerto estable
  -> Adaptador Valkimia WEB futuro
```

Las reglas de necesidades, excepciones, backlog e intersucursales no deben conocer endpoints ni tablas externas.

---

## 3. Capacidades requeridas

| Capacidad | Obligatoria Fase 1 | WEB futura |
| --- | --- | --- |
| Publicar documento de salida | Sí | Sí |
| Obtener ID/referencia | Sí | Sí |
| Consultar documento/estado | Sí | Sí |
| Obtener cantidad confirmada por línea | Sí | Sí |
| Detectar documentos finalizados | Deseable | Sí/eventos |
| Marcar información procesada | Si el contrato lo requiere | Según contrato |
| Cancelar | Solo si está validado | Deseable |
| Idempotencia nativa | Deseable; compensar si no existe | Obligatoria |
| Stock Neto Disponible | No bloquea | Deseable/objetivo |
| Eventos incrementales | No bloquea | Deseable |
| Tracking despacho/recepción | Según disponibilidad | Objetivo |

---

## 4. Puertos internos

### 4.1 Publicación

```text
publishDistributionOffer(request)
```

Request lógico:

```json
{
  "offerId": "uuid",
  "externalReference": "CNX-...",
  "sourceCd": "CD01",
  "destinationBranch": "041",
  "businessDate": "2026-07-24",
  "targetDate": "2026-07-25",
  "lines": [
    {
      "offerLineId": "uuid",
      "itemId": "1234",
      "uom": "UN",
      "quantity": 10
    }
  ]
}
```

Response lógico:

```json
{
  "result": "ACCEPTED|PARTIAL|REJECTED|UNKNOWN",
  "externalDocumentId": "string",
  "externalStatus": "string",
  "lineResults": [],
  "messages": []
}
```

### 4.2 Tracking

```text
getDistributionStatus(externalDocumentId)
```

Response lógico:

```json
{
  "externalDocumentId": "string",
  "externalStatus": "string",
  "normalizedStatus": "VKM_IN_PROCESS",
  "lastUpdateAt": "timestamp",
  "lines": [
    {
      "itemId": "1234",
      "requestedQuantity": 10,
      "confirmedQuantity": 6
    }
  ]
}
```

### 4.3 Finalizados incrementales

```text
listFinishedDistributions(cursor/filter)
acknowledgeDistributionProcessed(externalDocumentId)
```

Connexa solo confirmará procesamiento después de persistir eventos e imputar cantidades en una transacción segura.

### 4.4 SND opcional

```text
getNetAvailableStock(cdId, itemIds)
```

Su ausencia no bloquea la Fase 1. Su presencia mejora la visibilidad, pero no activa prorrateo automático.

---

## 5. Capacidades observadas en la documentación recibida

El PDF `Reuniones/Documentacion servicios WMS-VKM_v2.pdf` describe para “Salidas” rutas lógicas de la familia:

```text
.../OP/Remote/v9/Document/getById
.../OP/Remote/v9/Document/getId
.../OP/Remote/v9/Document/listNewDeliveryFinished
.../OP/Remote/v9/Document/inUse
.../OP/Remote/v9/Document/add
.../OP/Remote/v9/Document/addList
.../OP/Remote/v9/Document/setProcessed
.../OP/Remote/v9/Document/cancel
```

También documenta:

- cabecera de documento;
- destino/entidad;
- depósito, operación y tipo;
- detalle por artículo;
- cantidades requeridas y confirmadas;
- estados `GEN`, `ACO`, `CUR`, `TER`, `REV`, `PRG`, `EXP`, `CAR`, `ANU`, `AGR`;
- mensajes e indicador `isOk`.

Esto demuestra capacidades candidatas, no confirma:

- disponibilidad en el ambiente DIARCO;
- método HTTP definitivo — la propia documentación presenta diferencias en algunos apartados;
- autenticación;
- semántica DIARCO de operación/tipo;
- idempotencia;
- límites;
- SND;
- que “cantidad confirmada” equivalga exactamente a “preparada”;
- que un estado final equivalga a entrega en sucursal.

---

## 6. Mapping preliminar a validar

| Estado externo | Interpretación candidata | Estado normalizado |
| --- | --- | --- |
| `GEN` | Generado | `VKM_RECEIVED` |
| `ACO` | A controlar | `VKM_IN_PROCESS` |
| `CUR` | En curso | `VKM_IN_PROCESS` |
| `PRG` | Programado | `VKM_IN_PROCESS` |
| `REV` | En revisión | `VKM_IN_PROCESS` o incidencia |
| `TER` | Terminado | `VKM_PREPARED` — validar |
| `EXP` | Expedido | `VKM_DISPATCHED` — validar |
| `CAR` | En carga | `VKM_IN_PROCESS` o despacho — validar |
| `ANU` | Anulado | `VKM_CANCELLED` |
| `AGR` | Agrupado | Depende del documento resultante |

Reglas:

- el valor original siempre se conserva;
- un estado sin mapping se normaliza como `UNKNOWN_EXTERNAL_STATUS`;
- no se infiere recepción en sucursal desde un estado WMS;
- cambios de mapping son versionados y auditados.

---

## 7. Idempotencia

### 7.1 Riesgos

Un timeout puede ocurrir:

- antes de que Valkimia reciba;
- después de crear el documento pero antes de responder;
- después de responder mientras Connexa no persiste.

Reenviar sin consulta podría duplicar.

### 7.2 Estrategia

1. Crear `offerId` y `externalReference` antes de llamar.
2. Persistir mensaje `PENDING`.
3. Enviar la referencia en el campo externo validado.
4. Persistir respuesta y documento en una transacción.
5. Ante resultado ambiguo, consultar por referencia/clave.
6. Vincular si existe.
7. Reenviar con la misma referencia solo si se confirma ausencia.
8. Aplicar lock por referencia.

Si Valkimia no permite consultar una referencia estable, el riesgo debe considerarse bloqueante de Go-Live o mitigarse mediante una interfaz acordada.

---

## 8. Publicación por lotes

El adaptador podrá agrupar según límites confirmados:

- por CD;
- por sucursal;
- por tipo de operación;
- por máximo de líneas/payload.

Reglas:

- el lote técnico no cambia la identidad funcional;
- una falla parcial conserva resultado por documento/línea;
- no se reenvían documentos confirmados;
- el orden no implica reserva de stock;
- toda división mantiene correlación con la oferta.

---

## 9. Polling y cantidades

### Frecuencia

Parametrizable por estado:

- recién publicado: más frecuente;
- en curso: frecuencia operativa;
- final: no consultar salvo reconciliación;
- error/desconocido: circuito especial.

### Monotonicidad

Si una cantidad confirmada disminuye:

- no sobrescribir silenciosamente;
- registrar evento de corrección;
- alertar si el contrato no prevé la disminución;
- recalcular imputaciones de forma controlada.

### Finalizados

El proceso recomendado:

1. listar pendientes;
2. persistir documento y líneas;
3. deduplicar evento;
4. actualizar proyección;
5. confirmar procesado;
6. registrar auditoría.

---

## 10. Errores y reintentos

| Tipo | Ejemplo | Tratamiento |
| --- | --- | --- |
| Validación | artículo/destino inválido | No reintentar; corregir mapping |
| Negocio | documento rechazado | Registrar y devolver saldo al ciclo |
| Técnico transitorio | timeout/5xx | Consulta previa + backoff |
| Autenticación | credencial vencida | Alerta crítica; no reintento masivo |
| Resultado ambiguo | conexión cortada | Buscar referencia antes de reenviar |
| Estado desconocido | nuevo código | Conservar, alertar y mapear |
| Datos inconsistentes | confirmada > requerida | Aislar, alertar y no cerrar |

No se usará el endpoint de cancelación física como mecanismo habitual de corrección. Su semántica y trazabilidad deben validarse antes de habilitarlo.

---

## 11. Seguridad

Por confirmar con Valkimia:

- protocolo TLS;
- autenticación;
- rotación de credenciales;
- allowlist/red;
- cifrado;
- límites y protección contra abuso;
- datos sensibles.

Connexa:

- no expondrá credenciales en logs;
- enmascarará payloads;
- separará permisos de consulta/reintento;
- auditará acciones manuales;
- almacenará secretos en el mecanismo corporativo.

---

## 12. Pruebas de contrato obligatorias

1. Alta individual exitosa.
2. Alta masiva parcial.
3. Consulta por ID.
4. Resolución por referencia externa.
5. Cada estado real.
6. Cantidad requerida/confirmada por línea.
7. Documento con artículos repetidos.
8. Timeout antes y después de creación.
9. Reenvío con misma referencia.
10. Documento anulado.
11. Documento agrupado.
12. Listado de finalizados y confirmación.
13. Límites de líneas/tamaño.
14. Caracteres, decimales, fechas y unidades.
15. Autenticación y expiración.
16. Rendimiento/ventana.

La evidencia de estas pruebas formará el contrato técnico definitivo.

---

## 13. Migración al adaptador WEB

Pasos:

1. Implementar el mismo puerto interno.
2. Ejecutar pruebas de contrato.
3. Comparar respuestas contra el adaptador vigente fuera del flujo productivo.
4. Migrar referencias abiertas o permitir que cada documento continúe con su adaptador original.
5. Cambiar el adaptador para nuevas ofertas en una fecha controlada.
6. Mantener rollback técnico sin reactivar SGM.

La transición entre adaptadores puede ser gradual por documento porque no crea dos fuentes de necesidad: Connexa sigue siendo el único origen.

---

## 14. Decisiones por confirmar con Valkimia

- versión y despliegue real;
- endpoints/métodos;
- autenticación;
- operación y tipo documental;
- campo de referencia Connexa;
- unicidad/idempotencia;
- semántica de destino y depósitos;
- unidades/decimales;
- estados;
- cantidad confirmada;
- finalización/despacho;
- cancelación;
- límites;
- polling/rate limit;
- SND y componentes;
- eventos disponibles;
- ambiente de prueba y datos de certificación.

