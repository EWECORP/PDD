"""Early, read-only Inventory coverage audit for the active PDD scope."""

from __future__ import annotations

import json
from uuid import UUID

from prefect import flow, get_run_logger
from prefect.artifacts import create_markdown_artifact
from prefect.events import emit_event

from pdd_backend.clock import business_today
from pdd_backend.config import OperationalSettings, Settings
from pdd_backend.db import build_engine, build_operational_engine
from pdd_backend.jobs.inventory_coverage import (
    InventoryGapPolicy,
    inspect_candidate_inventory_coverage,
    inspect_inventory_coverage,
)
from pdd_backend.runtime_registry import read_active_runtime_binding


def _markdown(result: dict, environment: str) -> str:
    lines = [
        f"# Cobertura Inventory PDD · {environment}",
        "",
        f"Scope: `{result['scope_version_uuid']}`",
        f"Universo verificado: {result['scope_evaluated']} · "
        f"altas previstas: {result['added_pairs']} · "
        f"bajas previstas: {result['removed_pairs']}",
        f"Estado: **{result['status']}** · pares: {result['scope_pairs']} · "
        f"faltantes: {result['gap_count']} · límite: {result['allowed_gap_count']} "
        f"· con necesidad dirigida activa: {len(result['active_directed_pairs'])}",
        "",
        "| Motivo | Pares |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {reason} | {count} |"
        for reason, count in result["reason_counts"].items()
    )
    lines.extend(["", "| Artículo | Sucursal | Motivo |", "|---:|---:|---|"])
    lines.extend(
        f"| {row['codigo_articulo']} | {row['sucursal']} | {row['reason']} |"
        for row in result["gaps"][:100]
    )
    if len(result["gaps"]) > 100:
        lines.append(
            f"\nSe muestran 100 de {len(result['gaps'])} pares; "
            "la lista completa figura en los logs de esta corrida."
        )
    lines.extend([
        "",
        "Acción: verificar altas y estados en Inventory; revisar la política "
        "antes de reactivarla. Si el estado es BLOCKED, resolver los faltantes "
        "o ajustar el scope autorizado antes de la corrida diaria.",
    ])
    return "\n".join(lines)


def _publish_diagnostics(result: dict, environment: str, logger) -> None:
    gaps = result["gaps"]
    for offset in range(0, len(gaps), 50):
        chunk = gaps[offset:offset + 50]
        logger.warning(
            "Pares Inventory incompletos %s-%s/%s: %s",
            offset + 1, offset + len(chunk), len(gaps),
            json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
        )
    resource = {"prefect.resource.id": f"pdd.inventory.{environment.lower()}"}
    events = []
    if result["added_pairs"] or result["removed_pairs"]:
        events.append((
            "pdd.inventory.coverage.scope_changed",
            {
                "environment": environment,
                "active_scope_version_uuid": result["scope_version_uuid"],
                "added_pairs": result["added_pairs"],
                "removed_pairs": result["removed_pairs"],
            },
        ))
    if gaps:
        events.append((
            f"pdd.inventory.coverage.{result['status'].lower()}",
            {
                "environment": environment,
                "scope_version_uuid": result["scope_version_uuid"],
                "gap_count": result["gap_count"],
                "allowed_gap_count": result["allowed_gap_count"],
                "reason_counts": result["reason_counts"],
                "active_directed_pairs": len(result["active_directed_pairs"]),
                "scope_evaluated": result["scope_evaluated"],
                "added_pairs": result["added_pairs"],
                "removed_pairs": result["removed_pairs"],
            },
        ))
    for event_name, payload in events:
        try:
            emit_event(event=event_name, resource=resource, payload=payload)
        except Exception as exc:
            logger.warning("No se pudo emitir evento %s: %s", event_name, exc)
    try:
        create_markdown_artifact(
            key=f"pdd-inventory-coverage-{environment.lower()}",
            markdown=_markdown(result, environment),
            description="Pares del scope sin politica Inventory utilizable",
        )
    except Exception as exc:
        logger.warning(
            "No se pudo crear el artefacto Prefect; la lista completa "
            "permanece en los logs: %s", exc,
        )


@flow(name="PDD - Verificar cobertura Inventory", log_prints=True)
def pdd_inventory_coverage_flow(scope_version_uuid: str | None = None) -> dict:
    logger = get_run_logger()
    source_settings = Settings.from_env()
    target_settings = OperationalSettings.from_env()
    environment = target_settings.target_environment
    if source_settings.runtime_environment != environment:
        raise RuntimeError("Ambiente runtime y destino operativo inconsistentes")
    source_engine = build_engine(source_settings)
    target_engine = build_operational_engine(target_settings)
    try:
        with source_engine.connect() as source:
            binding = read_active_runtime_binding(
                source,
                environment,
                source_settings.runtime_process_code,
            )
            scope_uuid = (
                UUID(scope_version_uuid) if scope_version_uuid else
                binding.scope_version_uuid if binding else
                source_settings.require_scope_uuid()
            )
        policy = InventoryGapPolicy.from_env()
        active = inspect_inventory_coverage(
            source_engine, target_engine, scope_uuid,
            policy, business_today(),
        )
        candidate = inspect_candidate_inventory_coverage(
            source_engine, target_engine, source_settings, scope_uuid,
            policy, business_today(),
        )
        membership_changed = bool(
            candidate["added_pairs"] or candidate["removed_pairs"]
        )
        result = {
            **(candidate if membership_changed else active),
            "scope_version_uuid": str(scope_uuid),
            "scope_evaluated": "LIVE_CANDIDATE" if membership_changed else "ACTIVE",
            "added_pairs": candidate["added_pairs"],
            "removed_pairs": candidate["removed_pairs"],
            "active_scope_status": active["status"],
            "active_scope_gap_count": active["gap_count"],
        }
        logger.info(
            "Cobertura Inventory %s: scope=%s, universo=%s, "
            "altas=%s, bajas=%s, cubiertos=%s/%s, "
            "faltantes=%s, limite=%s, dirigidos=%s, motivos=%s",
            result["status"], scope_uuid, result["scope_evaluated"],
            result["added_pairs"], result["removed_pairs"],
            result["covered_pairs"],
            result["scope_pairs"], result["gap_count"],
            result["allowed_gap_count"], len(result["active_directed_pairs"]),
            result["reason_counts"],
        )
        _publish_diagnostics(result, environment, logger)
        if result["status"] == "BLOCKED":
            raise RuntimeError(
                "Cobertura Inventory bloqueada: "
                f"faltantes={result['gap_count']}, "
                f"limite={result['allowed_gap_count']}, "
                f"dirigidos={len(result['active_directed_pairs'])}; "
                f"motivos={result['reason_counts']}"
            )
        if result["gap_count"]:
            logger.warning(
                "El calculo diario podria omitir %s pares sin parametro Inventory; "
                "ver logs y resolver antes de las 21:15/21:45 ART",
                result["gap_count"],
            )
        return result
    finally:
        target_engine.dispose()
        source_engine.dispose()
