# Contexto
## Situación actual del proceso de transferencias

El esquema vigente de transferencias presenta múltiples orígenes y una falta de sincronización entre sistemas:

- **Connexa genera necesidades de transferencia**, las envía a la DMZ y luego a SGM, desde donde finalmente se derivan a **Valkimia** para su ejecución logística.
- **SGM también puede generar transferencias directamente**, lo que provoca que una misma sucursal pueda recibir **más de una solicitud para el mismo SKU**, sin consolidación automática. Esto obliga a actualizar, sumar cantidades o definir un mecanismo alternativo para evitar duplicidades.
- **Valkimia registra todas las solicitudes**, pero si al preparar un pedido no dispone de stock suficiente, **elimina la solicitud en lugar de reservarla o mantenerla pendiente**, generando pérdida de información y falta de trazabilidad.
- Debido a estas inconsistencias, **no existe garantía de que una transferencia esté correctamente registrada, planificada o ejecutada**, lo que afecta la confiabilidad del proceso y la visibilidad desde Connexa.


## Problemas principales identificados

- **Múltiples fuentes de generación de transferencias** → riesgo de duplicados y falta de consolidación.
- **Ausencia de un stock disponible confiable** → Valkimia no descuenta correctamente las solicitudes pendientes.
- **Pérdida de solicitudes por falta de stock** → se eliminan en lugar de mantenerse en backlog.
- **Falta de trazabilidad unificada** → Connexa no puede ver el estado real de cada línea de planificación.
- **Imposibilidad de planificar envíos optimizados** → no se puede cubicar ni consolidar viajes de manera eficiente
---

# Propuesta conceptual para un nuevo enfoque
De hecho, el problema que existe no es técnico sino **arquitectónico**: hoy no existe una única ***“fuente de verdad”*** para las transferencias, y además el sistema logístico (Valkimia) no se comporta como un reservorio sino como un ==ejecutor oportunista==.

Vamos a estructurar la respuesta en cuatro partes:

1. Diagnóstico del modelo actual
    
2. Análisis crítico de la propuesta
    
3. Arquitectura objetivo recomendada
    
4. Evolución futura (cubicaje y optimización logística)
    

---

# 1️⃣ Diagnóstico del esquema actual

### Flujo vigente

CONNEXA → DMZ → SGM → VALKIMIA → Ejecución CD

Pero además:

SGM → VALKIMIA (transferencias directas)

### Problemas estructurales detectados

### 🔴 1. Multiplicidad de orígenes

- Connexa genera necesidades.
    
- SGM también genera transferencias directas.
    
- No existe mecanismo nativo de consolidación por SKU + sucursal.
    

**Resultado**:  
Pueden coexistir múltiples transferencias para el mismo SKU y destino.

---

### 🔴 2. Valkimia no reserva stock

Si no puede preparar:

- elimina la solicitud
    
- no queda backlog
    
- no hay estado “pendiente por falta de stock”
    

Esto rompe cualquier trazabilidad.

---

### 🔴 3. Falta de visibilidad real

Connexa:

- No sabe si la transferencia fue realmente planificada.
    
- No sabe si fue eliminada.
    
- No tiene certeza de reserva.
    

En términos de control de gestión, esto es crítico.

---

# 2️⃣ Análisis de su propuesta

Su planteo es conceptualmente correcto y va en la dirección adecuada:

### ✔ Punto 1 — Calcular stock disponible real en Valkimia

Proponen:

**Stock Disponible** = Stock Físico CD – Transferencias en estado ACO (acopio)

Esto es correcto, pero hay que refinarlo:

El stock realmente utilizable debería ser:

	Stock Utilizable =  
	Stock Físico CD  
		– ACO  
		– Pedidos de cliente pendientes  
		– Transferencias en preparación  
		– Bloqueos / reservas técnicas

Es decir, Valkimia debe convertirse en **proveedor de stock neto utilizable**, no stock bruto.

---

### ✔ Punto 2 — Enviar solo lo que puede planificarse

Esto es clave.

Hoy el flujo es:

> “Necesidad primero, factibilidad después”.

Proponemos cambiar:

> “Factibilidad primero, planificación después”.

Eso reduce:

- falsas expectativas
    
- inconsistencias
    
- eliminaciones silenciosas
    

Es correcto.

---

### ✔ Punto 3 — Estado real por línea

Aquí está el verdadero salto cualitativo.

Connexa debería pasar de:

> “Generador de solicitudes”

a:

> “Orquestador del ciclo de vida de la transferencia”.

---

### ✔ Punto 4 — Mantener ID Valkimia

Fundamental.

Hoy probablemente el ID Valkimia es un dato accesorio.

Debe transformarse en:

Clave técnica obligatoria para tracking

---

### ✔ Punto 5 — Cubicaje futuro

Esto ya es un nivel 2 de madurez logística.

Significa que Connexa dejaría de ser solo motor de necesidad,  
para convertirse en:

> Motor de consolidación logística por viaje.

***Esto es la clave del cambio y es muy potente.***

---

# 3️⃣ Arquitectura recomendada (Modelo Objetivo)

Yo propondría una modificación más profunda:

---

# 🔷 Nuevo Principio Rector

> CONNEXA debe ser la única fuente de planificación de transferencias.

- SGM no debería generar transferencias directas.

- Si por razones políticas o técnicas no se puede eliminar eso, 
- entonces:

- SGM debe generar necesidades,  
- pero la planificación debe centralizarse en Connexa.

---

# 🔷 Modelo propuesto en 3 capas

---

## 🧠 Capa 1 — Necesidad Consolidada (Connexa)

Tabla central:

	'transfer_need

Clave única:

SKU + Sucursal + Fecha

Si llegan dos necesidades:

- se suman
    
- no se duplican
    

Aquí se elimina el problema estructural de multiplicidad.

---

## 📦 Capa 2 — Factibilidad (Stock CD)

Proceso diario:

1. Connexa consulta stock neto Valkimia.
    
2. Calcula asignación posible.
    
3. Marca cada línea:
    

Estado Planificación:  
- PLANIFICABLE  
- PARCIAL  
- NO PLANIFICABLE (sin stock)

Solo las planificables se envían.

Las no planificables quedan en backlog.

Esto reemplaza la eliminación silenciosa actual.

---

## 🚛 Capa 3 — Ejecución (Valkimia)

Al enviar:

Connexa genera:

	'transfer_plan_id

Y recibe:

	'valkimia_transfer_id

Se guarda relación 1:1.

Estados posibles:

- SOLICITADA  
- RESERVADA (ACO)  
- EN PREPARACION  
- DESPACHADA  
- RECIBIDA  
- CANCELADA

Nunca se elimina físicamente.

---

# 🔷 Cambio clave: Valkimia no puede eliminar

Si Valkimia no tiene stock:

Debe responder:

- RECHAZADA_POR_STOCK

Pero la transferencia debe quedar viva en Connexa.

---

# 4️⃣ Cómo resolver el problema de duplicación actual

VAMOS A TRATAR POR TODOS LO MEDIOS ELIMINAR SGM,
Pero si no pueden eliminar el origen SGM:

Se puede aplicar este algoritmo:

### Consolidación por ventana temporal

Regla:

	'Si existe transferencia pendiente  
	para SKU + Sucursal  
	en estado NO DESPACHADA  
	
		→ SUMAR CANTIDAD

Pero esto solo funciona  
==si Connexa es el dueño de la planificación.==

---

# 5️⃣ Qué deberíamos hacer (Opinión Técnica)

Desde una mirada neutral:

Esta propuesta es correcta, pero aún conservadora.

Desde mi opinión técnica:

Yo iría más allá.

Convertiría a Connexa en:

> **OMS interno de transferencias**

SGM dejaría de generar transferencias directas.  
Solo consumiría estado.

> Valkimia dejaría de decidir si planifica.  
Solo ejecutaría lo que Connexa asigna.

Eso les da:

- trazabilidad completa
    
- control financiero del stock
    
- eliminación de inconsistencias
    
- base para optimización logística futura
    

---

# 6️⃣ Evolución futura: Cubicaje inteligente

Una vez que tengan:

- Necesidades consolidadas
    
- Stock neto
    
- Backlog ordenado
    

Podríamos hacer:

	* Agrupar por sucursal  
	* Calcular volumen total  
	* Optimizar camión  
	* Completar hasta capacidad

Eso transforma el sistema en:

> Motor de optimización logística.

Impacto directo en:

- costo por viaje
    
- ocupación de camiones
    
- frecuencia óptima
    

---

# 7️⃣ Riesgos si no se cambia

Si continúan con el modelo actual:

- Seguirán existiendo duplicaciones.
    
- Habrá transferencias invisibles.
    
- Valkimia seguirá eliminando.
    
- No podrán hacer optimización logística real.
    

---

# 8️⃣ Conclusión

### Versión Neutral

Su propuesta es técnicamente correcta y mejora significativamente el control y la trazabilidad.

### Mi Opinión

>Es momento de centralizar completamente la planificación en Connexa y convertirlo en el orquestador único del ciclo de vida de transferencias.

>No solo resolvería el problema actual.  
Sentaría la base para una arquitectura de supply planning mucho más madura.

---

