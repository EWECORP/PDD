A continuación se entrega (1) **pseudocódigo implementable** del planificador (backlog + replanificación) y (2) una **propuesta inicial de pesos** para `priority_score`, diferenciando familias (Perecederos / Secos / Non-Food). Se agrega además (3) un esquema mínimo de **monitoreo y alertas** para operación.

---

# 1) Pseudocódigo implementable — Planificador de Transferencias

## 1.1 Supuestos operativos (explícitos)

- La unidad de planificación es **línea SKU–Sucursal–CD**.
    
- El backlog está representado por `TransferNeed` con `qty_need`, `qty_fulfilled`, y derivados.
    
- Valkimia provee `stock_net_available` por `CD–SKU` (snapshot).
    
- Se evita duplicación verificando ejecuciones activas.
    
- La ejecución se crea solo para líneas planificadas con qty > 0.
    
- La replanificación respeta `next_replan_at` (cooldown + backoff).
    

---

## 1.2 Funciones auxiliares

### Backoff exponencial (cooldown)

function compute_next_replan_at(now, attempts, base_minutes, max_minutes):  
    wait = base_minutes * 2^(attempts-1)  
    wait = min(wait, max_minutes)  
    return now + wait minutes

### Priority Score (conceptual)

function compute_priority_score(need, context):  
    score =  
        w_manual_priority * need.manual_priority  
      + w_sla_urgency     * sla_urgency(need.sla_due_at, now)  
      + w_break_risk      * break_risk(context.stock_store, context.min_stock_store)  
      + w_sales           * normalize(context.sales_rate)  
      + w_promo           * promo_boost(context.promo_active)  
      + w_age             * normalize(need.backlog_age_hours)  
      - w_retry_penalty   * need.replan_attempts  
    return score

> Nota: “context” proviene de datos de tienda (stock tienda, mínimos, ventas, promo). Si aún no están disponibles, el score puede operar “degradado” (FIFO + prioridad manual).

---

## 1.3 Proceso principal — Generar Plan (por CD)

### Entrada

- `cd_id`
    
- `now`
    
- parámetros (frecuencia, backoff, estrategia, pesos)
    

### Salida

- `TransferPlan` + `TransferPlanLine[]`
    

---

### Pseudocódigo

procedure run_planning(cd_id, now):  
  
  # 0) Crear corrida de planificación (Plan)  
  plan_id = create_plan(cd_id, now, status="OPEN")  
  
  # 1) Seleccionar Needs elegibles (backlog real)  
  needs = query TransferNeed  
          where cd_id = cd_id  
            and (qty_need - qty_fulfilled) > 0  
            and hold_reason is null  
            and (next_replan_at is null or next_replan_at <= now)  
            and need_status not in (NEED_CANCELLED, NEED_EXPIRED)  
  
  if needs is empty:  
      close_plan(plan_id, status="NO_WORK")  
      return  
  
  # 2) Armar conjunto de SKUs involucrados  
  skus = distinct needs.sku_id  
  
  # 3) Consultar Stock Neto Valkimia (snapshot)  
  stock_map = valkimia.get_stock_net_available(cd_id, skus)  
  # stock_map[sku] = {stock_net_available, snapshot_ts, version}  
  
  # 4) Cargar contexto para scoring (si existe)  
  # (ventas, stock tienda, mínimos, promo, etc.)  
  ctx_map = load_context_for_needs(needs)  # opcional, degradable  
  
  # 5) Calcular backlog_qty y priority_score por Need  
  for need in needs:  
      need.backlog_qty = need.qty_need - need.qty_fulfilled  
      need.backlog_age_hours = hours_between(need.created_at, now)  
      need.priority_score = compute_priority_score(need, ctx_map[need.id])  
  
  # 6) Agrupar por SKU para asignación por disponibilidad  
  grouped = group needs by sku_id  
  
  planned_lines = []  
  
  for each sku_id in grouped.keys:  
      snd = stock_map[sku_id].stock_net_available  
      snapshot_ts = stock_map[sku_id].snapshot_ts  
      stock_version = stock_map[sku_id].version  
  
      sku_needs = grouped[sku_id]  
  
      # 6.1) Orden de asignación (strategy)  
      if allocation_strategy == "PRIORITY":  
          sort sku_needs by (priority_score desc, created_at asc)  
      else if allocation_strategy == "FIFO":  
          sort sku_needs by (created_at asc)  
      else if allocation_strategy == "FAIR_SHARE":  
          # 1ra vuelta: asignar mínimo a todos (si hay)  
          # 2da vuelta: completar por prioridad  
          sku_needs = fair_share_order(sku_needs)  
      else:  
          sort sku_needs by (priority_score desc, created_at asc)  
  
      # 6.2) Asignación  
      for need in sku_needs:  
          if snd <= 0:  
              mark_need_waiting_stock(need, now)  
              continue  
  
          # 6.3) Anti-duplicación durante transición:  
          if exists_active_execution_in_valkimia(cd_id, need.sucursal_id, sku_id):  
              mark_need_blocked_by_external_execution(need, now)  
              continue  
  
          qty_to_plan = min(need.backlog_qty, snd)  
  
          if qty_to_plan <= 0:  
              mark_need_waiting_stock(need, now)  
              continue  
  
          # 6.4) Crear PlanLine  
          plan_line = create_plan_line(  
              plan_id=plan_id,  
              need_id=need.need_id,  
              cd_id=cd_id,  
              sucursal_id=need.sucursal_id,  
              sku_id=sku_id,  
              qty_planned=qty_to_plan,  
              stock_snapshot=snd,  
              stock_snapshot_ts=snapshot_ts,  
              stock_net_version=stock_version,  
              status="PLAN_PLANNED"  
          )  
          planned_lines.append(plan_line)  
  
          # 6.5) Actualizar Need (acumuladores y tiempos)  
          need.qty_planned += qty_to_plan  
          need.last_planned_at = now  
  
          # 6.6) Reducir snd  
          snd -= qty_to_plan  
  
          # 6.7) Si queda backlog remanente, programar replanificación  
          if (need.backlog_qty - qty_to_plan) > 0:  
              need.replan_attempts += 1  
              need.next_replan_at = compute_next_replan_at(  
                    now, need.replan_attempts,  
                    base_minutes=BACKOFF_BASE,  
                    max_minutes=BACKOFF_MAX  
              )  
              need.need_status = NEED_PARTIALLY_PLANNED  
          else:  
              need.need_status = NEED_FULLY_PLANNED  
  
          persist_need(need)  
  
  # 7) Si no se planificó nada, cerrar plan  
  if planned_lines is empty:  
      close_plan(plan_id, status="NO_STOCK_OR_BLOCKED")  
      return  
  
  # 8) Publicación (fase siguiente): publicar plan_lines planificadas  
  publish_results = publish_plan_lines_to_valkimia(plan_id, planned_lines)  
  
  # 9) Actualizar Execution/Need según respuestas  
  handle_publish_results(publish_results, now)  
  
  close_plan(plan_id, status="SENT")

---

## 1.4 Publicación idempotente y manejo de respuestas

procedure publish_plan_lines_to_valkimia(plan_id, planned_lines):  
    # agrupar por sucursal (cabecera ejecución)  
    groups = group planned_lines by sucursal_id  
  
    results = []  
    for sucursal_id in groups:  
        execution_id = uuid()  
        payload = build_payload(execution_id, plan_id, cd_id, sucursal_id, groups[sucursal_id])  
  
        resp = valkimia.publish_transfer(payload)  # idempotente por execution_id  
  
        results.append({execution_id, sucursal_id, resp})  
    return results

### Manejo de respuesta

procedure handle_publish_results(results, now):  
  
  for r in results:  
      if r.resp.accepted:  
         create_or_update_execution(r.execution_id, r.resp.valkimia_transfer_id, status="EXEC_ACCEPTED")  
         for each line in r.resp.lines:  
             update_execution_line_status(line.connexa_line_id, map_status(line.status))  
             # actualizar need.qty_published += qty_requested (si accepted)  
             update_need_published(line.connexa_line_id)  
      else:  
         # REJECTED_STOCK u otro  
         create_or_update_execution(r.execution_id, r.resp.valkimia_transfer_id, status="EXEC_REJECTED_STOCK")  
         for each line in r.resp.lines:  
             # devolver al backlog: qty_published no incrementa o se revierte  
             revert_need_on_reject(line.connexa_line_id, now)

---

## 1.5 Replanificación automática por rechazo

procedure revert_need_on_reject(plan_line_id, now):  
    need = get_need_by_plan_line(plan_line_id)  
    need.replan_attempts += 1  
    need.next_replan_at = compute_next_replan_at(now, need.replan_attempts, BACKOFF_BASE, BACKOFF_MAX)  
    need.last_execution_status = "REJECTED_STOCK"  
    need.need_status = NEED_PARTIALLY_PLANNED  # o NEED_CONSOLIDATED si se quiere “volver atrás”  
    persist_need(need)

---

# 2) Pesos iniciales para `priority_score`

Se propone un set de pesos por “familia logística” (ajustable por parámetros). La idea es:

- **Perecederos:** priorizar urgencia y riesgo de quiebre, con replan más frecuente.
    
- **Secos:** balancear ventas y antigüedad.
    
- **Non-Food:** dar más peso a promociones/eventos y menos a urgencia.
    

> Escala sugerida: 0 a 10 (por componente), score total típicamente 0–100.

## 2.1 Componentes

- `manual_priority` (0–100)
    
- `sla_urgency` (0–1)
    
- `break_risk` (0–1)
    
- `sales_rate` normalizado (0–1)
    
- `promo_active` (0 o 1)
    
- `backlog_age` normalizado (0–1)
    
- `replan_attempts` (0..n)
    

---

## 2.2 Pesos recomendados

### A) Perecederos

- `w_manual_priority = 0.25`
    
- `w_sla_urgency = 0.20`
    
- `w_break_risk = 0.25`
    
- `w_sales = 0.15`
    
- `w_promo = 0.10`
    
- `w_age = 0.10`
    
- `w_retry_penalty = 0.05`
    

**Interpretación:** si hay riesgo de quiebre y ventana corta, se prioriza fuerte.

---

### B) Secos

- `w_manual_priority = 0.25`
    
- `w_sla_urgency = 0.10`
    
- `w_break_risk = 0.20`
    
- `w_sales = 0.20`
    
- `w_promo = 0.10`
    
- `w_age = 0.15`
    
- `w_retry_penalty = 0.05`
    

**Interpretación:** se prioriza ventas + equidad por antigüedad.

---

### C) Non-Food

- `w_manual_priority = 0.25`
    
- `w_sla_urgency = 0.05`
    
- `w_break_risk = 0.10`
    
- `w_sales = 0.20`
    
- `w_promo = 0.20`
    
- `w_age = 0.20`
    
- `w_retry_penalty = 0.05`
    

**Interpretación:** promociones/campañas y backlog aging pesan más; menos urgencia por perecibilidad.

---

## 2.3 Parámetros de replanificación sugeridos por familia

### Perecederos

- `replan_frequency_minutes = 30`
    
- `backoff_base = 15`
    
- `backoff_max = 240` (4h)
    

### Secos

- `replan_frequency_minutes = 90`
    
- `backoff_base = 30`
    
- `backoff_max = 720` (12h)
    

### Non-Food

- `replan_frequency_minutes = 180`
    
- `backoff_base = 60`
    
- `backoff_max = 1440` (24h)
    

---

# 3) Monitoreo y Alertas — mínimo indispensable

## 3.1 KPIs operativos

1. **Backlog_total_qty** por CD y familia
    
2. **Backlog_aging_p95** (horas)
    
3. **Reject_rate_stock** (rechazos/total publicados)
    
4. **Publish_success_rate**
    
5. **Time_to_ship_p50/p90** (publicado → despachado)
    
6. **Fill_rate_transfer** (recibido / solicitado)
    

## 3.2 Alertas (reglas prácticas)

- **ALERTA A — Backlog aging crítico**
    
    - si `aging_p95 > umbral` (ej: perecederos > 6h, secos > 48h)
        
- **ALERTA B — Rechazos por stock anómalos**
    
    - si `reject_rate_stock > 20%` en 2h
        
- **ALERTA C — Stock neto inconsistente**
    
    - si `stock_net_available < 0` o fluctúa violentamente (versión)
        
- **ALERTA D — Ejecuciones “colgadas”**
    
    - si `EXEC_ACCEPTED` sin avanzar a `PICKING` en X horas
        
- **ALERTA E — Duplicación detectada**
    
    - si aparecen 2 ejecuciones activas mismo SKU–Sucursal
        

---

# 4) Lo que conviene definir ya (para que desarrollo no “interprete”)

Para evitar discusiones en implementación, conviene cerrar:

1. **Qué es “bucket”** (diario vs intradía)
    
2. **Cómo se normaliza sales_rate** (por ejemplo z-score o min-max por familia)
    
3. **Qué es break_risk** (ej: `stock_tienda <= stock_minimo`)
    
4. **Cuándo se considera “ejecución activa”** (qué estados de Valkimia)
    
5. **Qué pasa si Valkimia acepta cabecera pero rechaza líneas** (parcialidad)
    

---

## Siguiente paso recomendado

Para convertir esto en artefacto implementable sin ambigüedad, el próximo entregable es un **catálogo de reglas** (tabla) con:

- Definición exacta de `break_risk`, `sla_urgency`, normalizaciones,
    
- Umbrales por familia,
    
- Estados de Valkimia mapeados a estados internos,
    
- Conjunto de estados considerados “activos” para anti-duplicación.
    

Si avanzan, lo entrego en formato de **matriz de reglas** (lista estructurada) lista para pegar en un documento de arquitectura o Confluence.

---
### PEGAR EN CONFLUENCE
---
