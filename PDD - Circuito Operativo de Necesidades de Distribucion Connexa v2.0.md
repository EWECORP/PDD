# Circuito Operativo de Necesidades de Distribución — Fase 1

Versión: **2.1**
Fecha: **2026-07-28**
Estado: **Procedimiento operativo objetivo**

---

## 1. Regla central

Connexa mantiene la deuda de abastecimiento. Valkimia decide qué puede ejecutar. Ninguna selección elimina una necesidad hasta recibir evidencia efectiva.

## 2. Secuencia diaria

### 2.1 Cierre anterior y captura

Datos:

- stock físico por sucursal–artículo;
- ingresos directos de OC y tránsito desde Base 2;
- compromisos por ventas especiales y transferencias confirmadas;
- PDVB y parámetros;
- stock e ingresos de Base 2;
- maestros y unidades logísticas;
- eventos Valkimia pendientes.

Controles:

- fecha/hora y lote;
- cobertura de universo;
- duplicados;
- valores inválidos;
- factores logísticos faltantes;
- conciliación de eventos.

### 2.2 Cálculo

Para cada línea:

1. calcular Stock Neto Sucursal;
2. calcular crítico, mínimo, máximo y sobre-stock;
3. generar D y S;
4. calcular IRQ;
5. recuperar E/C/A vigentes;
6. descontar pipeline y cumplimiento una sola vez;
7. consolidar DECAS;
8. ordenar por compromiso, IRQ, antigüedad y fecha.

Una corrida fallida no desplaza la última foto válida.

### 2.3 Revisión de Compras

Compras:

- revisa quiebres, compromisos y datos faltantes;
- investiga el detalle del cálculo;
- crea o actualiza E/C/A;
- gestiona alertas;
- no carga reposición regular;
- no asigna stock ni arma viajes.

Si una excepción cambia después de publicada la foto, el backlog se actualiza con versión y auditoría; no se modifica la corrida histórica.

### 2.4 Disponibilización

Connexa expone el backlog abierto con:

- ID y versión;
- D/E/C/A/S;
- obligatorio/opcional;
- prioridad e IRQ;
- saldo;
- fechas y SLA;
- proveedor, sucursal y artículo;
- unidades, bultos, pallets, kg y volumen si existen;
- timestamp y frescura.

### 2.5 Selección Valkimia

El operador:

1. consulta la foto vigente;
2. filtra y ordena;
3. revisa totales estimados;
4. selecciona según stock y capacidad;
5. confirma importación con ID/versiones Connexa;
6. ejecuta en Valkimia.

Connexa no sugiere cómo completar un camión y no convierte el conjunto seleccionado en un viaje.

### 2.6 Resultado Valkimia

Valkimia informa por línea:

- referencia externa;
- cantidad importada;
- cantidad preparada;
- estado;
- timestamp;
- remito, despacho o ETA, si existen.

Connexa:

- deduplica el evento;
- valida que las cantidades sean coherentes;
- imputa lo preparado a sus fuentes;
- conserva el remanente;
- actualiza tránsito cuando hay evidencia;
- alerta estado desconocido o falta de avance.

### 2.7 Cierre

Al final del ciclo:

- conciliar importaciones y eventos;
- registrar incidencias;
- actualizar pipeline;
- publicar indicadores de control;
- tomar la siguiente foto;
- recalcular y reemplazar D/S vigentes;
- mantener E/C/A abiertas.

## 3. Tratamiento DECAS

| Tipo | Origen | Clase | Persistencia |
| --- | --- | --- | --- |
| D | cálculo PDVB/cobertura | Obligatoria | se reemplaza con nueva foto |
| E | venta/negocio especial | Obligatoria | hasta cumplimiento/cierre |
| C | campaña | Obligatoria | durante vigencia y hasta cierre |
| A | acopio | Opcional | hasta cumplimiento/vencimiento/cierre |
| S | pulmón de sobre-stock | Opcional | se reemplaza con nueva foto |

La ausencia de stock no cierra ningún tipo.

## 4. Imputación inicial

Cuando una línea consolidada contiene varios orígenes, lo preparado se imputa:

1. E vencida;
2. E vigente;
3. C;
4. D;
5. A;
6. S.

Dentro del mismo tipo: fecha objetivo, antigüedad e ID. La regla se versiona.

## 5. Casos operativos

### Preparación parcial

Backlog 100, Valkimia importa 80 y prepara 50:

- importado: 80;
- preparado: 50;
- saldo de necesidad: 50;
- diferencia importado/no preparado: 30, visible;
- siguiente corrida: descuenta solo pipeline válido, sin duplicar.

### Importación sin preparación

La línea permanece abierta. Si supera el umbral de inactividad, se genera alerta.

### Datos diarios incompletos

Se bloquea el ámbito afectado y se conserva la última foto válida claramente fechada. No se calcula con cero implícito.

### Estado externo desconocido

Se conserva el código, se normaliza como `UNKNOWN_EXTERNAL_STATUS`, se alerta y no se cierra saldo.

### Resultado ambiguo

Antes de reintentar se busca la referencia Connexa. Solo se reenvía si se confirma ausencia.

## 6. Responsabilidades

| Actividad | Compras | Supervisor | Valkimia | IT/Datos |
| --- | --- | --- | --- | --- |
| Revisar prioridades | R | A | I | I |
| Mantener E/C/A | R | A según umbral | I | I |
| Calcular D/S e IRQ | I | A funcional | I | R técnico |
| Seleccionar/importar | I | I | R/A | C |
| Preparar/despachar | I | I | R/A | I |
| Reconciliar interfaces | I | I | C | R/A |
| Gestionar calidad | C | A | I | R |
| Cambiar parámetros | C | A | I | R |

No existe rol de planificador de transporte en Connexa Fase 1.

## 7. Controles diarios

- fuentes recibidas y frescas;
- corrida completa por ámbito;
- líneas rechazadas;
- totales D/E/C/A/S;
- backlog obligatorio/opcional;
- IRQ críticos;
- importaciones y duplicados;
- preparado parcial;
- importaciones sin avance;
- estados desconocidos;
- diferencias de cantidades;
- eventos pendientes;
- antigüedad y SLA.

## 8. Checklist de salida

Antes del Go-Live:

- fórmulas y redondeos ratificados;
- parámetros cargados;
- universo y volúmenes probados;
- IDs e idempotencia certificados;
- mapping Valkimia validado;
- tres días simulados sin duplicación;
- UAT D/E/C/A/S aprobada;
- permisos, alertas y monitor activos;
- contingencia ensayada;
- exclusiones verificadas.

## 9. Resultado operativo

Cada mañana existe una única foto explicable del backlog. Compras gestiona excepciones comerciales; Valkimia elige qué ejecutar; Connexa conserva la deuda y su trazabilidad. Ninguna función de gestión u optimización logística se introduce en este circuito.

