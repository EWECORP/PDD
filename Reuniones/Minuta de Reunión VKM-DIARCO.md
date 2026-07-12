# MINUTA DE REUNIÓN

## Proyecto

**Diseño del Módulo de Planificación de la Distribución**
**Fecha:** 02 de Julio de 2026
**Duración:** 62 minutos

## Participantes

**DIARCO**
- Guillermo Añaños
- Eduardo Ettlin
- Diego Ferrara
- Hernán López
- Cristhian David Rojas Adorno

**Valkimia**
- Gustavo Palacios
- Ariel Turrisi
- Alejandro Bozzolo
- Fernando De Pedro

---

# Objetivo de la reunión

Analizar el circuito actual de distribución entre SGM, Connexa y VKM para definir una arquitectura futura que permita reemplazar el proceso manual de planificación logística por un proceso inteligente centralizado dentro de Connexa.

El objetivo principal consiste en establecer una estrategia tecnológica que permita:

- separar la planificación comercial de la operación logística;
- automatizar la asignación de mercadería disponible;
- eliminar procesos manuales;
- mejorar la utilización del stock;
- preparar la futura desaparición de SGM.

---

# Contexto actual

Actualmente intervienen cuatro sistemas principales.

- SGM
- Connexa
- VKM (WMS)
- SAP (en algunos procesos administrativos)

Connexa ya genera las Órdenes de Compra utilizando algoritmos de demanda, stock disponible, pendientes y reglas comerciales.

Sin embargo, la generación automática de las Órdenes de Distribución fue detenida debido a diversos problemas operativos detectados durante las pruebas.

*Actualmente*:
- las compras son generadas por SGM ;
- las distribuciones continúan siendo planificadas manualmente desde SGM;
- VKM recibe únicamente órdenes preparadas manualmente.

---

# Situación detectada

Durante la reunión se identificó que el principal inconveniente no es tecnológico sino conceptual.

El comprador actualmente realiza simultáneamente dos funciones:

- decisiones comerciales;
- decisiones logísticas.

Esto provoca que el comprador deba decidir:

- cuánto comprar;
- cuándo distribuir;
- qué sucursal priorizar;
- cómo repartir el stock escaso;
- cómo completar camiones.

Estas tareas pertenecen conceptualmente al proceso logístico y no al proceso comercial.

---

# Diagnóstico consensuado

Se concluyó que hoy existe una mezcla de responsabilidades.

El comprador termina actuando como:

- planificador logístico;
- asignador de stock;
- administrador de transporte;
- optimizador de carga.

La reunión concluye que estas funciones deberían migrarse hacia un módulo especializado.

---

# Problemas observados

Se identificaron los siguientes problemas.

## 1. Falta de planificación integral

- Hoy la distribución se genera manualmente.
- No existe un planificador central.

---

## 2. Ausencia de un backlog único

- Cada sucursal solicita necesidades.
- Luego estas necesidades se procesan manualmente.
- No existe un repositorio único donde permanezcan pendientes hasta ser satisfechas.
---

## 3. Stock disponible insuficiente

Cuando el stock no alcanza:

- no existe un algoritmo formal;
- la decisión queda en manos del operador.

---

## 4. Prorrateo manual

- La distribución de mercadería escasa se realiza manualmente.
- No existen reglas configurables.

---

## 5. Falta de visibilidad

No existe un único tablero donde puedan visualizarse simultáneamente:

- necesidades
- stock disponible
- pedidos pendientes
- capacidad logística
- oportunidades de transporte

---

# Concepto estratégico aprobado

Se acordó avanzar hacia un nuevo concepto.

## Connexa será el Planificador Integral de Distribución.

Mientras que VKM continuará siendo el ejecutor operativo del depósito.

Es decir:

>Connexa decide
 >     ↓
>VKM ejecuta

---

# Nueva responsabilidad de Connexa

El nuevo módulo deberá administrar:

- necesidades de todas las sucursales
- stock disponible
- stock comprometido
- stock neto disponible
- pendientes
- órdenes abiertas
- demanda futura
- campañas comerciales
- prioridades
- reglas de asignación
- reglas de prorrateo

---

# Rol futuro de VKM

VKM dejaría de participar en las decisiones comerciales.

Su función sería:

- recibir órdenes preparadas;
- generar picking;
- administrar pallets;
- administrar preparación;
- administrar despacho.

En otras palabras:

**VKM será un WMS puro.**

---

# Conceptos funcionales propuestos

## Backlog de Necesidades

Se propone crear una entidad donde permanezcan todas las necesidades pendientes.

Cada necesidad deberá conservar información como:

- sucursal
- artículo
- prioridad
- fecha
- origen
- tipo de necesidad
- promoción
- cobertura
- criticidad

---

## Stock Neto Disponible

Se considera imprescindible incorporar el concepto de:

**Stock Neto Disponible**

No deberá utilizarse simplemente el stock físico.

Sino:

**Stock físico**
− reservado
− comprometido
− ya planificado  =
**Stock Neto Disponible**

***Será el verdadero insumo para distribuir.***

---

## Motor de Asignación

Se propone construir un motor que determine automáticamente:

>qué mercadería puede distribuirse
>y   a quién.

---

## Motor de Prorrateo

Cuando la mercadería resulte insuficiente, Connexa deberá aplicar reglas automáticas.

Ejemplos:
- prioridad comercial
- cobertura de stock
- campañas
- criticidad
- ABC
- rotación
- margen
- artículos sensibles
- riesgo de quiebre

Estas reglas deberán parametrizarse.

---

## Optimización de carga

También se discutió incorporar algoritmos capaces de:

- completar camiones
- aprovechar espacio
- agregar productos sugeridos
- maximizar utilización del transporte

Siempre respetando prioridades comerciales.

---

# Información necesaria

Se identificó que el módulo requerirá integrar información proveniente de:

## Comercial

- demanda
- forecast
- promociones
- campañas
- compras

## Inventario

- stock
- stock comprometido
- pendientes

## Logística

- pallets
- peso
- volumen
- capacidad
- ventanas
- camiones
- disponibilidad

## Maestro de artículos

Especialmente:

- dimensiones
- peso
- cajas por pallet
- altura
- datos logísticos

---

# Calidad de datos

Se destacó la importancia de mantener correctamente los datos logísticos.

Se propuso que:

el alta de un artículo no pueda quedar aprobada hasta validar sus datos logísticos.

---
# Arquitectura propuesta

```
Forecast
↓
Necesidades de Sucursales
↓
Backlog de Distribución
↓
Motor de Priorización
↓
Stock Neto Disponible
↓
Motor de Prorrateo
↓
Planificador de Distribución
↓
Órdenes de Distribución
↓
VKM
↓
Picking
↓
Despacho
↓
Recepción
```

---

# Integración tecnológica

Se conversó sobre avanzar hacia la nueva versión de VKM.

Se analizaron dos escenarios.

## Escenario 1

Continuar utilizando la versión actual.

Integración mediante Base de Datos.

---

## Escenario 2

Migrar a la nueva versión.

Integración mediante APIs.

**Se considera el camino recomendado**.

---

# Decisiones tomadas

Se acordó:

- detener definitivamente la lógica anterior de generación automática de órdenes de distribución;
- rediseñar completamente el proceso;
- concentrar la inteligencia en Connexa;
- convertir VKM en un ejecutor operativo;
- comenzar el diseño del nuevo módulo de planificación;
- elaborar un documento funcional detallado;
- realizar nuevas reuniones técnicas para profundizar el diseño.

---

# Próximos pasos

## DIARCO

- Elaborar documento funcional.
- Modelar el nuevo proceso.
- Definir reglas de asignación.
- Definir reglas de prorrateo.
- Diseñar entidades del modelo de datos.
- Construir prototipo funcional.

---

## Valkimia

- Analizar integración con la nueva versión.
- Evaluar APIs disponibles.
- Revisar impacto de la migración.
- Definir mecanismo de intercambio con Connexa.

---

# Conclusión

La reunión permitió alinear la visión de ambas organizaciones respecto del futuro proceso de distribución.

El consenso alcanzado establece que **Connexa debe evolucionar desde un sistema de planificación comercial hacia una plataforma integral de planificación del abastecimiento y distribución**, concentrando toda la inteligencia de negocio, mientras que **VKM debe especializarse en la ejecución operativa del centro de distribución**. Esta separación de responsabilidades permitirá reducir procesos manuales, mejorar la utilización del stock, automatizar las decisiones de asignación y prorrateo, incrementar la eficiencia logística y preparar la transición definitiva para reemplazar a SGM. La presente minuta constituye la base funcional para iniciar el diseño del nuevo **Módulo de Planificación de la Distribución**.