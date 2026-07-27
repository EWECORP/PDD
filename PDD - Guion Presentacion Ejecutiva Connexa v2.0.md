# Guion para presentación ejecutiva — Necesidades de Distribución Connexa

Versión: **2.0**
Fecha: **2026-07-24**
Documento fuente: `PDD - Vision Requerimiento y Plan Connexa v2.0.md`
Duración objetivo: **20–25 minutos + preguntas**
Audiencia: **Dirección, Compras, Abastecimiento, Logística, IT y referentes de Valkimia**

---

## 1. Instrucción maestra para el agente de presentaciones

Copiar desde aquí junto con el guion de diapositivas:

> Crear una presentación ejecutiva en español, formato PowerPoint 16:9, basada exclusivamente en este guion y en el documento “PDD - Vision Requerimiento y Plan Connexa v2.0”. La presentación debe explicar una decisión de negocio y un camino de implementación; no debe parecer una especificación técnica.
>
> El mensaje central es: “DIARCO puede resolver ahora la duplicación y la falta de visibilidad implementando en Connexa una única fuente de necesidades de distribución, sin esperar la migración WEB de Valkimia”.
>
> Generar 14 diapositivas principales y 4 de anexo. Usar gráficos editables, diagramas simples, tablas breves e íconos lineales. Evitar fotografías decorativas, bloques extensos de texto, mockups ilegibles y métricas inventadas. Incluir las notas del orador indicadas en el campo de notas de cada diapositiva.
>
> No introducir convivencia productiva entre SGM y Connexa. No presentar a Connexa como asignador o prorrateador de Stock Neto Disponible en la Fase 1. No incluir cubicaje, rutas, optimización de camiones ni planificación inteligente dentro del MVP. Esas capacidades pertenecen a la Fase 2.
>
> Mantener siempre esta separación:
>
> - Connexa identifica, consolida, registra y da visibilidad a la necesidad.
> - Compras trabaja por excepción.
> - Valkimia decide oportunísticamente cuánto puede preparar con su SND real.
> - SGM queda fuera del circuito desde el corte Big‑Bang.
>
> Cuando falte un valor numérico, usar “por definir” o un marcador `[VALIDAR]`. No inventar fechas, ahorros, volúmenes, porcentajes de mejora ni capacidades de Valkimia no confirmadas.

---

## 2. Lineamientos visuales

### Estilo

- Ejecutivo, sobrio, moderno y de alta legibilidad.
- Sensación de “torre de control de abastecimiento”, no de sistema transaccional.
- Mucho espacio en blanco.
- Una idea principal por diapositiva.
- Formas y gráficos completamente editables en PowerPoint.

### Paleta sugerida

| Uso | Color |
| --- | --- |
| Azul institucional / títulos | `#17324D` |
| Verde petróleo / Connexa | `#067A78` |
| Verde claro / resultado positivo | `#BFE3D6` |
| Ámbar / atención y transición | `#F2B45F` |
| Coral / problema o riesgo | `#DB674E` |
| Fondo cálido | `#F4F1E9` |
| Texto | `#172033` |

### Tipografía

- Títulos: Aptos Display, Segoe UI o equivalente.
- Cuerpo: Aptos, Segoe UI o equivalente.
- Título: 28–34 pt.
- Mensaje principal: 22–28 pt.
- Texto auxiliar: 16–20 pt.
- No utilizar texto menor de 14 pt.

### Reglas de composición

- Máximo aproximado de 35 palabras visibles por diapositiva, salvo tablas.
- Resaltar cifras o decisiones, no párrafos.
- Usar etiquetas consistentes:
  - Connexa: verde petróleo.
  - Valkimia: azul.
  - Compras: ámbar.
  - SGM / problema actual: coral o gris.
- Pie discreto: `Proyecto Connexa · Necesidades de Distribución · v2.0`.
- Reservar un espacio para logos DIARCO/Connexa si fueran provistos.

---

# Presentación principal

## Diapositiva 1 — Portada

### Objetivo

Presentar el tema como una decisión ejecutiva de simplificación y visibilidad.

### Título en pantalla

**Necesidades de Distribución**

### Subtítulo

**Connexa como fuente única para mejorar ahora la operación de Compras**

### Pie

`Propuesta ejecutiva · Fase 1 · Julio 2026`

### Visual sugerido

Fondo limpio con una línea de flujo:

```text
Necesidad -> Connexa -> Valkimia -> Locales
```

Connexa debe ocupar visualmente el centro.

### Notas del orador

> El objetivo de esta presentación es proponer una primera etapa concreta para mejorar rápidamente la operación de Compras y la visibilidad de la distribución. La propuesta no depende de completar primero la migración WEB de Valkimia. Se concentra en resolver el problema que más impacto genera hoy: tener dos fuentes de ingreso, poca trazabilidad y demasiado trabajo manual. La decisión es que Connexa se convierta en la única fuente de necesidades de distribución y que Valkimia continúe ejecutando lo que puede procesar.

### Transición

> Para entender la propuesta, primero debemos separar el problema operativo de la evolución tecnológica.

---

## Diapositiva 2 — La situación que debemos resolver

### Objetivo

Mostrar por qué el modelo actual no es sostenible.

### Título en pantalla

**El problema no es solo la integración**

### Mensaje central

**Dos fuentes generan dos versiones de la realidad.**

### Contenido visible

Cuatro bloques:

1. **Doble ingreso**
   Duplicación y desincronización.
2. **Trabajo manual**
   Compras repite tareas de reposición.
3. **Visibilidad fragmentada**
   Stock, necesidad y ejecución están separados.
4. **Backlog poco claro**
   No siempre se sabe qué quedó pendiente y por qué.

### Visual sugerido

Diagrama “antes”:

```text
SGM --------\
             > necesidades / transferencias -> Valkimia
Connexa ----/
```

Agregar símbolos de duplicación y pérdida de trazabilidad.

### Notas del orador

> Hoy el comprador debe convivir con información que nace o se modifica en más de un lugar. Eso genera duplicados, diferencias de estado y la necesidad de reconstruir manualmente qué ocurrió. Además, Compras termina dedicando esfuerzo a mantener reposiciones normales, cuando debería concentrarse en excepciones comerciales, faltantes y compromisos críticos. Si mantuviéramos la convivencia entre SGM y Connexa, incluso como transición, conservaríamos la causa estructural del problema.

### Transición

> Al mismo tiempo, existe una oportunidad tecnológica, pero no podemos condicionar toda la mejora a sus tiempos.

---

## Diapositiva 3 — La restricción y la oportunidad

### Objetivo

Explicar por qué se desacopla la mejora funcional de la migración WEB.

### Título en pantalla

**La versión WEB es el destino, no la condición de inicio**

### Diseño

Dos columnas:

#### Ahora

- Presupuesto y calendario restringidos.
- Necesidad de mejorar rápidamente.
- Integración vigente disponible.

#### Evolución

- Valkimia WEB.
- APIs y webservices.
- Mayor agilidad y riqueza de integración.

### Frase inferior

**El proceso funcional debe permanecer estable aunque cambie el mecanismo de integración.**

### Visual sugerido

Un núcleo “Connexa” conectado a dos adaptadores:

```text
Connexa -> Adaptador actual -> Valkimia instalada
        -> Adaptador WEB    -> Valkimia futura
```

### Notas del orador

> La nueva versión WEB de Valkimia es el camino tecnológico recomendado porque facilita la integración mediante APIs y webservices. Sin embargo, esa migración puede demorarse. La propuesta evita que el beneficio operativo quede bloqueado: diseñamos Connexa con un dominio estable y adaptadores intercambiables. En la Fase 1 utilizamos las capacidades confirmadas del entorno actual. Cuando llegue la versión WEB, cambia el adaptador, no el proceso de negocio ni la fuente de verdad.

### Transición

> Con esa separación, podemos tomar una decisión simple y fuerte sobre el modelo operativo.

---

## Diapositiva 4 — La decisión ejecutiva

### Objetivo

Instalar la decisión principal sin ambigüedad.

### Título en pantalla

**Una fuente. Un corte. Una visión.**

### Mensaje destacado

> **Connexa será la única fuente de necesidades de distribución.**

### Tres momentos

| Antes del corte | Desde el corte | Después del corte |
| --- | --- | --- |
| Limpiar, inventariar y migrar | Activar Connexa | SGM queda fuera del circuito |

### Sello visual

**Implementación Big‑Bang del módulo**

### Visual sugerido

Una línea temporal con un punto de corte vertical. Antes aparecen SGM y Connexa; después solo Connexa como origen.

### Notas del orador

> La recomendación es un Big‑Bang limitado al módulo de Necesidades de Distribución. No significa reemplazar todos los procesos de SGM. Significa que, desde una fecha de corte, ninguna nueva necesidad alcanzada por este módulo se crea, modifica o publica desde SGM. Antes del corte se prepara y concilia el inventario de pendientes. Después del corte, Connexa es el único registro funcional. Esta decisión elimina de raíz la duplicación y evita construir una reconciliación permanente entre dos publicadores.

### Transición

> Tener una única fuente permite redefinir también el trabajo del comprador.

---

## Diapositiva 5 — Nuevo rol de Compras

### Objetivo

Mostrar el beneficio operativo más visible para el usuario.

### Título en pantalla

**De cargar reposiciones a gestionar excepciones**

### Diseño

Comparación antes/después:

| Hoy | Fase 1 |
| --- | --- |
| Cargar necesidades regulares | Connexa las calcula diariamente |
| Comparar sistemas | Consultar una posición única |
| Perseguir estados | Gestionar alertas y SLA |
| Resolver manualmente cada faltante | Intervenir solo por excepción |

### Excepciones visibles

- **Venta Especial**
- **Acuerdo Comercial**
- **Acopio**
- **Rebalanceo intersucursal**

### Notas del orador

> En el nuevo modelo, la reposición normal deja de depender de una carga manual. Connexa calcula diariamente la necesidad regular de cada sucursal y artículo. El comprador aporta valor donde realmente hace falta: registra una Venta Especial con su SLA, un Acuerdo Comercial con vigencia, un Acopio o una necesidad de rebalanceo entre sucursales. También actúa frente a alertas de bajo stock, entregas atrasadas o preparaciones parciales. El objetivo es reducir trabajo repetitivo y mejorar la calidad de la decisión comercial.

### Transición

> Veamos cómo funciona ese circuito cada día.

---

## Diapositiva 6 — Circuito diario de la Fase 1

### Objetivo

Explicar el flujo de punta a punta en una sola imagen.

### Título en pantalla

**Un ciclo diario, visible y trazable**

### Flujo visual

```text
1. Datos diarios
   ↓
2. Cálculo de necesidades Connexa
   ↓
3. Excepciones de Compras
   ↓
4. Consolidado CD -> sucursal
   ↓
5. Valkimia prepara lo procesable
   ↓
6. Estados y cantidades preparadas
   ↓
7. Visión actualizada + recálculo
```

### Etiquetas breves

- Datos: demanda, stock sucursal, stock CD y tránsito.
- Resultado: necesidad, pipeline, preparado y backlog.

### Notas del orador

> Cada día Connexa recibe la posición de demanda, stock de sucursales, stock de referencia del CD, mercadería en tránsito y datos maestros. Con esa información calcula la necesidad regular. Luego incorpora las excepciones comerciales vigentes y genera un consolidado para Valkimia. Valkimia toma lo que puede procesar con su Stock Neto Disponible real e informa estados y cantidades preparadas. Connexa actualiza la visión y, al día siguiente, vuelve a calcular con la nueva foto. De esa forma, el saldo no desaparece y tampoco se acumula ciegamente.

### Transición

> La distinción más importante del modelo es separar necesidad de ejecución.

---

## Diapositiva 7 — Necesidad y ejecución no son lo mismo

### Objetivo

Evitar que la audiencia interprete que Connexa asigna o garantiza stock.

### Título en pantalla

**Connexa expresa la necesidad; Valkimia confirma la ejecución**

### Diseño

Dos bloques conectados:

#### Connexa

- Calcula la necesidad.
- Conserva el backlog.
- Muestra stock CD de referencia.
- No reserva ni prorratea SND en Fase 1.

#### Valkimia

- Usa el SND operativo real.
- Decide cuánto puede procesar.
- Prepara total o parcialmente.
- Informa estado y cantidad.

### Frase destacada

**La falta de stock no elimina la necesidad.**

### Notas del orador

> Esta separación protege la trazabilidad. Connexa puede conocer un stock de referencia del CD y utilizarlo para mostrar factibilidad y alertas, pero no debe confundirlo con una reserva operativa. Valkimia tiene la foto real del depósito al momento de preparar y toma únicamente lo que puede procesar. Si prepara menos de lo ofrecido, Connexa registra la cantidad confirmada y mantiene visible el saldo. La asignación inteligente del stock escaso entre sucursales no pertenece a esta primera etapa.

### Transición

> Para evitar duplicaciones, el backlog regular se recalcula con una nueva foto en lugar de acumular solicitudes.

---

## Diapositiva 8 — Cómo se evita duplicar el backlog

### Objetivo

Explicar el recálculo con un ejemplo simple.

### Título en pantalla

**Recalcular, no acumular**

### Contenido visible

Ejemplo gráfico:

```text
Día 1
Necesidad consolidada: 110
Preparado por Valkimia: 60
Saldo visible: 50

Día 2
Nueva foto de stock + demanda + pipeline
→ nueva necesidad vigente
```

### Regla inferior

**La foto del día reemplaza la necesidad regular anterior; las excepciones conservan su identidad y vigencia.**

### Visual sugerido

Dos calendarios “Día 1” y “Día 2”, unidos por una flecha. Mostrar las 60 unidades preparadas dentro del pipeline del día 2.

### Notas del orador

> La necesidad regular no se suma todos los días. Cada corrida crea una nueva versión a partir del stock, la demanda y el pipeline vigente. Si Valkimia ya preparó o tiene en proceso una cantidad, esa cantidad se considera para no volver a pedirla. Las excepciones funcionan distinto: una Venta Especial o un Acuerdo Comercial conserva su ID, su SLA y su saldo hasta cumplirse, vencer o cancelarse. Esta combinación permite tener backlog sin duplicación.

### Transición

> Toda esa información se concentra en la herramienta principal del comprador.

---

## Diapositiva 9 — Panel del comprador

### Objetivo

Materializar el beneficio de visibilidad.

### Título en pantalla

**Una única posición para decidir**

### Jerarquía visual

```text
Proveedor -> Sucursal -> Artículo
```

### Pipeline visible

```text
Stock sucursal
-> Necesidad regular
-> Excepciones
-> Ofrecido
-> En proceso
-> Preparado / tránsito
-> Recibido
-> Backlog + SLA
```

### Alertas destacadas

- Riesgo de quiebre.
- Stock CD insuficiente.
- SLA vencido.
- Preparación parcial.
- Documento sin avance.
- Datos desactualizados.

### Visual sugerido

Mockup ejecutivo de una tabla con tres filas y semáforos. No incluir más de ocho columnas legibles. Agregar un panel lateral de alertas.

### Notas del orador

> El panel debe permitir que el comprador parta de su proveedor, sucursal o artículo y vea toda la posición en una misma línea. No se trata solo de mostrar stock: también debe mostrar qué se calculó, qué excepción existe, cuánto se ofreció, qué tomó Valkimia, qué está en tránsito y qué continúa pendiente. El usuario trabaja por excepción, con alertas y una próxima acción clara. El dato debe incluir siempre su fecha de actualización para que una foto vieja no parezca vigente.

### Transición

> Además del flujo desde el CD, hay una necesidad operativa distinta: rebalancear stock entre sucursales.

---

## Diapositiva 10 — Rebalanceo intersucursal

### Objetivo

Explicar el segundo circuito de Fase 1 sin mezclarlo con Valkimia/CD.

### Título en pantalla

**Rebalancear stock sin pasar por el CD**

### Flujo

```text
Sucursal origen
-> solicitud y validación
-> aprobación
-> coordinación logística
-> despacho
-> sucursal destino
```

### Reglas visibles

- Circuito separado del consolidado CD.
- Impacto visible en stock proyectado de origen y destino.
- Aprobación y trazabilidad propias.
- Ejecución logística posterior.

### Notas del orador

> Connexa también permitirá registrar necesidades de transferencia entre sucursales para rebalancear stock. Este flujo no pasa por el CD y no se mezcla con el consolidado enviado a Valkimia. El comprador propone origen, destino, artículo, cantidad y fecha requerida. Antes de aprobar, el sistema muestra el impacto proyectado sobre ambas sucursales. Luego Logística coordina la ejecución y se registran despacho y recepción. Así obtenemos visibilidad de otro componente del pipeline sin forzarlo dentro de un circuito que no le corresponde.

### Transición

> Para poner este modelo en marcha debemos realizar un corte controlado, no una convivencia indefinida.

---

## Diapositiva 11 — Implementación Big‑Bang

### Objetivo

Presentar el Big‑Bang como una secuencia gobernada y no como un salto sin control.

### Título en pantalla

**Un corte único, preparado en tres momentos**

### Diseño

Tres columnas:

#### 1. Preparar

- Fecha y alcance.
- Inventario de pendientes.
- Datos, usuarios y pruebas.
- Contingencia y Go/No-Go.

#### 2. Cortar

- Bloquear altas/publicaciones en SGM.
- Cargar inventario inicial.
- Activar Connexa.
- Verificar primer consolidado.

#### 3. Estabilizar

- Monitoreo diario.
- Conciliación de cantidades.
- Gestión de errores idempotente.
- Revisión de backlog y SLA.

### Nota visual

Mostrar una barrera clara: **“No reabrir doble ingreso como contingencia”**.

### Notas del orador

> Big‑Bang no significa improvisación. Antes del corte se define el universo, se limpia la información, se inventarían los documentos abiertos, se prueban cálculo, publicación y tracking, y se ensaya la contingencia. En el corte se deshabilita el módulo en SGM, se carga el inventario inicial y se activa Connexa. Después se trabaja con monitoreo intensivo y conciliación. Si falla una interfaz, la contingencia mantiene a Connexa como registro único y utiliza una cola o un envío controlado con la misma referencia; no se reactiva libremente el doble ingreso.

### Transición

> La construcción puede organizarse por capacidades, aunque la salida productiva sea única.

---

## Diapositiva 12 — Hoja de ruta

### Objetivo

Separar claramente preparación, Fase 1 y evolución futura.

### Título en pantalla

**Valor inmediato sin perder la evolución**

### Roadmap visual

```text
Fase 0
Cierre funcional y preparación
    |
Fase 1A
Necesidades + panel
    |
Fase 1B
Consolidado + tracking Valkimia
    |
Fase 1C
Rebalanceo intersucursal
    |
SALIDA BIG-BANG
    |
Fase 2
Gestión de la Distribución Inteligente
```

### Fase 2, en una franja separada

- Asignación y *fair share*.
- Reservas.
- Capacidad y ventanas.
- Peso, volumen y cubicaje.
- Viajes, rutas y optimización.
- Integración WEB enriquecida.

### Advertencia

**1A, 1B y 1C organizan la construcción; no habilitan convivencia productiva.**

### Notas del orador

> Proponemos preparar primero las reglas, datos, mappings, inventario y plan de corte. La construcción de Fase 1 se divide en necesidades y visibilidad, integración con Valkimia y rebalanceo intersucursal. Esa división facilita el trabajo y las pruebas, pero las capacidades salen juntas bajo el modelo de fuente única. La Fase 2 queda protegida como evolución: cuando la organización y la versión WEB estén preparadas, Connexa podrá asumir asignación, prorrateo, capacidad, viajes y optimización.

### Transición

> El éxito de la primera etapa debe medirse por control, adopción y trazabilidad.

---

## Diapositiva 13 — Resultados y métricas de éxito

### Objetivo

Mostrar resultados esperados sin inventar beneficios económicos.

### Título en pantalla

**Cómo sabremos que la Fase 1 funciona**

### Indicadores principales

Mostrar cuatro tarjetas grandes:

1. **100%**
   de nuevas necesidades del alcance nacen en Connexa.
2. **0**
   nuevas cargas o publicaciones desde SGM.
3. **100%**
   de ofertas con referencia única trazable.
4. **100%**
   de saldos no preparados visibles o explicados.

### Indicadores operativos debajo

- Tiempo manual de Compras.
- Adopción del panel.
- Backlog y aging.
- SLA de excepciones.
- Frescura de estados Valkimia.
- Diferencia ofrecido/preparado/recibido.

### Nota para el agente

No convertir los cuatro indicadores de control en promesas de mejora económica. Presentarlos como criterios de aceptación del modelo.

### Notas del orador

> Las primeras métricas no deben ser estimaciones de ahorro sin evidencia. Deben demostrar que el nuevo modelo está gobernado. Toda necesidad nueva debe nacer en Connexa, no debe haber nuevas publicaciones desde SGM, cada oferta debe tener una referencia trazable y todo saldo no preparado debe permanecer visible o ser explicado por el recálculo. Luego mediremos reducción del trabajo manual, adopción, aging, cumplimiento de SLA y diferencias entre lo ofrecido, preparado y recibido.

### Transición

> Para alcanzar estos resultados debemos cerrar un conjunto acotado de decisiones antes de desarrollar.

---

## Diapositiva 14 — Decisiones solicitadas y próximo paso

### Objetivo

Cerrar la presentación con una solicitud concreta a Dirección y áreas.

### Título en pantalla

**Aprobar el rumbo y cerrar las definiciones de arranque**

### Bloque 1 — Aprobación ejecutiva solicitada

- Connexa como fuente única.
- Corte Big‑Bang del módulo.
- Fase 1 acotada a necesidades y visibilidad.
- Fase 2 separada.
- Migración WEB no bloqueante.

### Bloque 2 — Talleres de definición

Agrupar las decisiones pendientes:

1. **Cálculo y datos**
   Fórmula, horizonte, fuentes y stock CD.
2. **Excepciones y operación**
   Políticas, aprobaciones e intersucursales.
3. **Valkimia**
   Contrato, estados, preparado e idempotencia.
4. **Corte**
   Fecha, universo, pendientes y contingencia.

### Cierre en pantalla

> **Resolver ahora la fuente única; evolucionar después la inteligencia logística.**

### Notas del orador

> La decisión que necesitamos no es aprobar todavía cada detalle técnico. Es validar el rumbo: Connexa como única fuente, corte Big‑Bang del módulo, Fase 1 concentrada en necesidades y visibilidad, y Fase 2 separada para la inteligencia logística. Con ese mandato podemos cerrar en talleres breves la fórmula, las fuentes, las reglas de excepción, el contrato real con Valkimia y el plan de corte. La propuesta permite obtener valor operativo ahora sin renunciar a la migración WEB ni a una distribución más inteligente en el futuro.

### Cierre oral sugerido

> La pregunta ejecutiva es simple: ¿acordamos eliminar la doble fuente y concentrar desde el corte todas las necesidades de distribución en Connexa?

---

# Diapositivas de anexo

## Anexo A — Fórmula funcional preliminar

### Título

**Cómo se calcula la necesidad regular**

### Contenido

```text
stock_proyectado_sucursal =
  stock_disponible_sucursal
  + ingresos_confirmados_no_recibidos
  - compromisos_confirmados

necesidad_regular_bruta =
  max(stock_objetivo_horizonte - stock_proyectado_sucursal, 0)
```

Variables a validar:

- horizonte;
- stock objetivo/cobertura;
- demanda o forecast;
- pipeline incluido;
- múltiplos logísticos;
- uso del stock CD de referencia.

### Nota

Indicar claramente “Fórmula base sujeta a validación con Abastecimiento”.

---

## Anexo B — Alcance Fase 1 vs. Fase 2

### Tabla

| Fase 1 — Necesidades | Fase 2 — Distribución Inteligente |
| --- | --- |
| Cálculo diario | Asignación de SND |
| Excepciones de Compras | Prorrateo y *fair share* |
| Consolidado a Valkimia | Reservas |
| Tracking de preparado | Capacidad y ventanas |
| Panel y alertas | Cubicaje |
| Rebalanceo intersucursal | Viajes, rutas y optimización |
| Adaptador actual/WEB | Integración WEB enriquecida |

### Nota

No mostrar la Fase 2 como compromiso de fecha o alcance aprobado.

---

## Anexo C — Riesgos y mitigaciones

### Tabla resumida

| Riesgo | Mitigación |
| --- | --- |
| Datos incompletos | Calidad, frescura y bloqueo controlado |
| Uso residual de SGM | Deshabilitar función y permisos |
| Duplicación por reintentos | Referencia estable y consulta previa |
| Estados Valkimia ambiguos | Mapping validado y alerta `UNKNOWN` |
| Cantidades tardías | Polling y alertas de desactualización |
| Pendientes no migrados | Inventario firmado y conciliación |
| Excepción duplica necesidad | Política adicional/mínimo/reemplazo |
| Sin API de SND | No bloquear; usar referencia y validación Valkimia |
| Expansión de alcance | Separación contractual Fase 1/Fase 2 |

---

## Anexo D — Decisiones pendientes

### Agrupación para workshop

#### Cálculo y datos

- Fórmula, horizonte y frecuencia.
- Fuentes de stock, tránsito, demanda y maestros.
- Significado del stock CD disponible.

#### Excepciones

- Política adicional/mínimo/reemplazo.
- Campos y aprobaciones.
- Estados intersucursal.

#### Valkimia

- Operación, tipo documental y campos.
- Estado/cantidad que significa “preparado”.
- Referencia e idempotencia.
- Frecuencia de sincronización.

#### Corte

- Fecha.
- Universo de pendientes.
- Fuente de recepción.
- Contingencia.

---

## 3. Controles de calidad antes de entregar el PowerPoint

El agente generador debe verificar:

- [ ] La presentación contiene 14 diapositivas principales y 4 anexos.
- [ ] La decisión de fuente única aparece antes de la diapositiva 5.
- [ ] SGM está explícitamente fuera del circuito posterior al corte.
- [ ] No se propone *shadow mode* ni convivencia productiva.
- [ ] Valkimia aparece como ejecutor oportunista en Fase 1.
- [ ] Connexa no aparece reservando o prorrateando SND.
- [ ] El recálculo diario se explica como reemplazo, no acumulación.
- [ ] Venta Especial, Acuerdo Comercial, Acopio e intersucursal están visibles.
- [ ] La versión WEB se presenta como evolución no bloqueante.
- [ ] Fase 1 y Fase 2 se distinguen visualmente.
- [ ] No hay métricas, ahorros ni fechas inventadas.
- [ ] Las notas del orador están incluidas.
- [ ] Todos los diagramas son editables.
- [ ] Los textos son legibles en una sala.
- [ ] La última diapositiva contiene una decisión solicitada.

---

## 4. Versión abreviada del mensaje ejecutivo

Si el agente necesita una síntesis para la descripción del archivo:

> DIARCO implementará en Connexa una única fuente de necesidades de distribución mediante un corte Big‑Bang del módulo. Connexa calculará diariamente la reposición regular y Compras actuará por excepción. Valkimia continuará preparando oportunísticamente según su Stock Neto Disponible, mientras Connexa registrará lo preparado, mantendrá visible el backlog y recalculará la necesidad. La integración funcionará con el mecanismo vigente y evolucionará a APIs WEB sin rediseñar el proceso. La asignación inteligente, el prorrateo y la optimización logística quedarán para una Fase 2 independiente.

