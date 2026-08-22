# PDD - Solicitud de ampliación de `pdd_item_logistics_snapshot`

Versión: 1.0  
Fecha: 2026-08-21  
Responsable funcional: PDD / Planificación de Distribución  
Componente responsable del DDL: BACK Stock Management / Flyway

## 1. Objetivo

Ampliar `stock_management.pdd_item_logistics_snapshot` para conservar, en cada corrida PDD, la configuración logística inmutable utilizada para:

- convertir unidades de demanda en bultos y pallets;
- calcular peso y volumen de las líneas;
- cubicar viajes;
- validar capacidad de vehículos;
- explicar la calidad y procedencia de cada cálculo;
- reproducir posteriormente una planificación histórica.

La tabla continúa siendo un **snapshot por corrida**. No debe transformarse en un maestro editable. El maestro canónico será `diarco_data.src.base_articulos_logistica`; el proceso Python publicará una copia congelada de sus atributos en esta entidad operacional.

## 2. Compatibilidad requerida

No eliminar ni renombrar los campos actuales:

- `item_logistics_snapshot_id`;
- `calculation_run_id`;
- `origin_cd`;
- `codigo_articulo`;
- `product_id`;
- `origin_site_id`;
- `base_unit`;
- `units_per_package`;
- `packages_per_pallet`;
- `unit_weight_kg`;
- `unit_volume_m3`;
- `source_snapshot_id`;
- `quality_status`;
- `source_as_of_ts`;
- `input_checksum`;
- `created_at`.

La clave lógica debe continuar siendo:

```text
(calculation_run_id, origin_cd, codigo_articulo)
```

No se debe crear una FK física hacia `diarco_data`, porque la fuente y el destino se encuentran en bases diferentes.

## 3. Campos nuevos requeridos

### 3.1 Identidad y procedencia de la configuración

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `source_logistics_id` | `bigint` | Sí | Identificador lógico `articulo_logistica_id` de la fila canónica de `diarco_data.src.base_articulos_logistica`. Sin FK entre bases. |
| `supplier_code` | `integer` | Sí | Proveedor al que corresponde la configuración logística. Nulo cuando la configuración es general para el artículo. |
| `logistics_configuration_code` | `varchar(60)` | Sí | Código funcional de configuración, por ejemplo `DEFAULT`, `SUPPLIER_1234` o una presentación logística particular. |
| `source_valid_from` | `timestamptz` | Sí | Inicio de vigencia de la versión canónica copiada al snapshot. |
| `sells_by_weight` | `boolean` | Sí | Indica si el artículo se administra o vende por peso. |
| `package_uom` | `varchar(30)` | Sí | Unidad logística del bulto: `BOX`, `PACK`, `BAG`, `DISPLAY`, etc. |
| `unit_gtin` | `varchar(14)` | Sí | GTIN/EAN de la unidad base, si está disponible. |
| `package_gtin` | `varchar(14)` | Sí | GTIN/DUN del bulto, si está disponible. |
| `source_reference` | `varchar(200)` | Sí | Referencia al registro, archivo, medición o sistema que originó el dato. |

### 3.2 Peso

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `unit_net_weight_kg` | `numeric(18,6)` | Sí | Peso neto de una unidad base. |
| `unit_gross_weight_kg` | `numeric(18,6)` | Sí | Peso bruto de una unidad base, incluyendo su envase primario. |
| `package_gross_weight_kg` | `numeric(18,6)` | Sí | Peso bruto del bulto completo. |
| `weight_basis` | `varchar(30)` | Sí | Regla utilizada para obtener el peso efectivo: `GROSS_UNIT`, `GROSS_PACKAGE_DERIVED`, `NET_UNIT_FALLBACK` o `ESTIMATED`. |

El campo actual `unit_weight_kg` se conserva como **peso efectivo por unidad utilizado por los cálculos**. Su selección debe seguir esta prioridad:

1. `unit_gross_weight_kg`;
2. `package_gross_weight_kg / units_per_package`;
3. `unit_net_weight_kg`, solamente como fallback identificado;
4. una estimación explícitamente identificada.

No se debe grabar cero para representar un peso desconocido: corresponde `NULL`.

### 3.3 Dimensiones y volumen

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `package_length_cm` | `numeric(12,3)` | Sí | Largo exterior del bulto en centímetros. |
| `package_width_cm` | `numeric(12,3)` | Sí | Ancho exterior del bulto en centímetros. |
| `package_height_cm` | `numeric(12,3)` | Sí | Alto exterior del bulto en centímetros. |
| `package_volume_m3` | `numeric(18,9)` | Sí | Volumen del bulto en metros cúbicos. Puede venir informado o ser derivado de sus dimensiones. |
| `volume_method` | `varchar(30)` | Sí | Procedencia del volumen: `MEASURED_DIMENSIONS`, `SOURCE_DIMENSIONS`, `SOURCE_REPORTED`, `SUPPLIER_REPORTED` o `ESTIMATED`. |

El campo actual `unit_volume_m3` se conserva como **volumen efectivo por unidad utilizado por los cálculos**:

```text
package_volume_m3 =
    package_length_cm * package_width_cm * package_height_cm / 1.000.000

unit_volume_m3 = package_volume_m3 / units_per_package
```

Cuando el volumen venga informado directamente, debe conservarse `volume_method` para distinguirlo de una medición o una estimación. No se debe grabar cero para representar volumen desconocido.

### 3.4 Palletización

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `packages_per_layer` | `integer` | Sí | Bultos por camada o piso del pallet. |
| `layers_per_pallet` | `integer` | Sí | Cantidad de camadas del pallet completo. |
| `units_per_pallet` | `numeric(18,6)` | Sí | Unidades base por pallet completo. |
| `pallet_type` | `varchar(30)` | Sí | Tipo de pallet: `ARLOG`, `EUR`, `CUSTOM`, etc. |
| `pallet_length_cm` | `numeric(12,3)` | Sí | Largo del pallet empleado. |
| `pallet_width_cm` | `numeric(12,3)` | Sí | Ancho del pallet empleado. |
| `loaded_pallet_height_cm` | `numeric(12,3)` | Sí | Altura total del pallet cargado. |
| `pallet_gross_weight_kg` | `numeric(18,6)` | Sí | Peso bruto del pallet completo. |

Reglas derivadas:

```text
packages_per_pallet = packages_per_layer * layers_per_pallet
units_per_pallet    = units_per_package * packages_per_pallet
```

Si existe una cantidad informada directamente y también los componentes, deben coincidir. Una diferencia debe marcar la fila como inválida o generar una incidencia de calidad; no debe corregirse silenciosamente.

### 3.5 Restricciones de manipulación

Estos atributos pueden permanecer nulos hasta que DIARCO disponga de la información, pero conviene incorporarlos al contrato ahora para no requerir otra ampliación durante el desarrollo de cubicación.

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `stackable` | `boolean` | Sí | Indica si el bulto admite apilamiento. |
| `max_stack_levels` | `smallint` | Sí | Máximo de niveles de apilamiento permitidos. |
| `fragile` | `boolean` | Sí | Requiere manipulación como mercadería frágil. |
| `hazardous` | `boolean` | Sí | Identifica mercadería peligrosa o regulada. |
| `temperature_zone` | `varchar(20)` | Sí | Zona térmica: `AMBIENT`, `CHILLED`, `FROZEN` u otra controlada. |
| `temperature_min_c` | `numeric(6,2)` | Sí | Temperatura mínima permitida en °C. |
| `temperature_max_c` | `numeric(6,2)` | Sí | Temperatura máxima permitida en °C. |
| `orientation_code` | `varchar(20)` | Sí | Restricción de orientación: `ANY`, `UPRIGHT`, `DO_NOT_TILT`, etc. |

### 3.6 Calidad y trazabilidad

| Campo | Tipo PostgreSQL | Nulabilidad | Descripción |
|---|---|---:|---|
| `packaging_quality_status` | `varchar(20)` | No | Calidad del factor de compra/presentación. |
| `weight_quality_status` | `varchar(20)` | No | Calidad de los pesos. |
| `volume_quality_status` | `varchar(20)` | No | Calidad de dimensiones y volumen. |
| `pallet_quality_status` | `varchar(20)` | No | Calidad de la palletización. |
| `quality_issue_codes` | `text[]` | No | Códigos de problemas detectados; el publicador V2 debe enviar `'{}'` cuando no existan incidencias. |
| `verified_at` | `timestamptz` | Sí | Fecha de la última verificación humana o certificada. |
| `verified_by` | `varchar(120)` | Sí | Usuario, proveedor o proceso que verificó el dato. |
| `attributes` | `jsonb` | No | Extensión controlada para atributos logísticos no incorporados aún al contrato; default `'{}'::jsonb`. No sustituye campos estructurados. |

Valores permitidos para los cuatro estados por eje:

- `VERIFIED`: verificado por una fuente aprobada o una medición controlada;
- `SOURCE`: recibido de una fuente autorizada, todavía no verificado;
- `ESTIMATED`: calculado o imputado;
- `MISSING`: no disponible;
- `INVALID`: disponible pero no supera las reglas de validación.

El campo actual `quality_status` continúa como resumen general y debe admitir:

- `COMPLETE`;
- `PARTIAL`;
- `ESTIMATED`;
- `MISSING`;
- `INVALID`.

Regla recomendada para `quality_status`:

- `INVALID`: algún eje necesario es inválido;
- `MISSING`: no existe una configuración logística utilizable;
- `ESTIMATED`: el cálculo operativo puede realizarse, pero utiliza al menos un dato estimado;
- `PARTIAL`: existe configuración, pero falta al menos uno de peso, volumen o palletización;
- `COMPLETE`: presentación, peso, volumen y palletización están completos y ninguno es estimado.

## 4. Restricciones requeridas

1. Todos los pesos, dimensiones y volúmenes informados deben ser mayores que cero.
2. `unit_gross_weight_kg >= unit_net_weight_kg` cuando ambos estén informados.
3. Las tres dimensiones del bulto deben estar todas informadas o todas nulas.
4. `packages_per_layer`, `layers_per_pallet` y `max_stack_levels` deben ser enteros mayores que cero cuando estén informados.
5. Si `stackable = false`, `max_stack_levels` debe ser nulo o igual a 1.
6. `temperature_min_c <= temperature_max_c` cuando ambas estén informadas.
7. Los GTIN deben contener solamente dígitos y tener una longitud válida: 8, 12, 13 o 14 caracteres.
8. Los estados y métodos deben estar limitados por `CHECK` o por catálogos estables acordados con BACK.
9. `input_checksum` debe incluir todos los campos anteriores, para que un cambio logístico produzca una huella distinta.

## 5. Carga inicial y compatibilidad histórica

La migración debe agregar los campos sin borrar snapshots existentes.

Para no interrumpir al publicador V1 durante el despliegue coordinado, los cuatro estados por eje tendrán temporalmente el default conservador `MISSING`, y `quality_issue_codes` tendrá el default `LOGISTICS_CONTRACT_V2_NOT_POPULATED`. El publicador V2 deberá enviar todos esos campos explícitamente; el default no representa una clasificación definitiva.

Para los registros históricos se deben completar objetivamente los estados por eje:

- `packaging_quality_status = 'SOURCE'` si existen `base_unit` y `units_per_package`; de lo contrario `MISSING`;
- `weight_quality_status = 'SOURCE'` si existe `unit_weight_kg`; de lo contrario `MISSING`;
- `volume_quality_status = 'SOURCE'` si existe `unit_volume_m3`; de lo contrario `MISSING`;
- `pallet_quality_status = 'SOURCE'` si existe `packages_per_pallet`; de lo contrario `MISSING`.

No se deben inventar dimensiones, volumen ni palletización para completar el histórico. Tampoco se debe reinterpretar retroactivamente `quality_status`; la fórmula utilizada en cada corrida ya queda identificada por `pdd_calculation_run.formula_version`.

## 6. Cambios requeridos fuera del DDL

### BACK Java

- Incorporar los campos en el modelo de persistencia de Stock Management.
- Exponerlos como solo lectura en los DTO de consulta logística y planificación.
- Permitir al frontend identificar si peso, volumen o palletización son completos, estimados o faltantes.
- No habilitar edición directa sobre el snapshot.

### Publicador Python PDD

- Leer la versión vigente de `diarco_data.src.v_base_articulos_logistica_actual`.
- Copiar los atributos al snapshot correspondiente a la corrida.
- Calcular los valores efectivos y los cuatro estados de calidad.
- Registrar incidencias con códigos estables en `quality_issue_codes`.
- Recalcular `input_checksum` con el contrato ampliado.

### Frontend

- Mostrar peso y volumen total de la línea y del viaje.
- Mostrar bultos y pallets estimados.
- Advertir cuando se cubique con datos `ESTIMATED`, `PARTIAL`, `MISSING` o `INVALID`.
- Impedir la confirmación del viaje cuando falten atributos definidos como obligatorios por la configuración operativa.

## 7. Criterios de aceptación

1. La migración Flyway se ejecuta con `ON_ERROR_STOP` y no elimina datos existentes.
2. Los campos actuales continúan disponibles con el mismo nombre y semántica compatible.
3. Un snapshot nuevo conserva la identidad lógica de la versión canónica utilizada.
4. Para un artículo completo se pueden reproducir unidades por bulto, bultos por pallet, peso y volumen.
5. Los faltantes permanecen como `NULL`, nunca como cero.
6. Cada eje de calidad puede consultarse de forma independiente.
7. No existen dependencias físicas entre bases de datos.
8. El BACK puede devolver estos atributos al frontend sin consultar directamente `diarco_data`.
9. Una modificación logística en origen cambia `input_checksum` y genera un snapshot auditable en una nueva corrida.

## 8. Prioridad de implementación

Para liberar cubicación, el mínimo obligatorio es:

1. identidad y procedencia;
2. peso neto/bruto y `weight_basis`;
3. dimensiones y volumen del bulto;
4. estructura de pallet;
5. calidad por eje y códigos de incidencia.

Los atributos de manipulación pueden comenzar nulos, pero deben estar presentes en el contrato para su incorporación progresiva.
