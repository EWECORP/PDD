from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from ..config import Settings
from ..db import build_engine, transactional_connection
from ..runtime_registry import activate_runtime_binding, read_active_runtime_binding
from .common import require_frozen_scope
from .operational_inputs import inspect_stock_readiness
from .scope_snapshot import capture_scope_snapshot


AUTO_ACTOR = "pdd.scope.auto"
SCOPE_BLOCKER = "SCOPE_CONTAINS_EXCLUDED_BRANCHES"


def _source_contract(connection) -> dict:
    row = connection.execute(
        text(
            """
            SELECT source_sync_run_uuid, business_date, status, finished_at
            FROM audit.pdd_source_sync_run
            WHERE refresh_mode = 'FULL'
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
    ).mappings().one_or_none()
    if row is None or row["status"] != "READY" or row["finished_at"] is None:
        raise RuntimeError("La ultima sincronizacion completa de fuentes PDD no esta READY")
    return dict(row)


def _candidate(connection, old_scope_uuid: UUID) -> dict | None:
    row = connection.execute(
        text(
            """
            SELECT v.scope_version_uuid, v.version_no, v.status,
                   v.article_count, v.pair_count, v.article_checksum,
                   v.pair_checksum, v.scope_checksum, v.captured_at
            FROM datamart.dm_pdd_scope_version AS v
            WHERE v.supersedes_scope_version_uuid = :old_scope_uuid
              AND v.status IN ('DRAFT', 'APPROVED')
              AND NOT EXISTS (
                  SELECT 1
                  FROM datamart.dm_pdd_scope_pair AS p
                  JOIN src.sucursales_excluidas AS e
                    ON e.c_sucu_empr::integer = p.destination_branch
                  WHERE p.scope_version_uuid = v.scope_version_uuid
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements_text(
                      coalesce(
                          v.pair_filter #> '{operational_branch_exclusion_policy,excluded_branches}',
                          '[]'::jsonb
                      )
                  ) AS old_exclusion(branch)
                  WHERE NOT EXISTS (
                      SELECT 1 FROM src.sucursales_excluidas AS live
                      WHERE live.c_sucu_empr::integer = old_exclusion.branch::integer
                  )
              )
            ORDER BY v.captured_at DESC
            LIMIT 1
            """
        ),
        {"old_scope_uuid": old_scope_uuid},
    ).mappings().one_or_none()
    return dict(row) if row else None


def _reopened_branches(connection, scope_uuid: UUID) -> tuple[int, ...]:
    rows = connection.execute(
        text(
            """
            SELECT old_exclusion.branch::integer AS branch
            FROM datamart.dm_pdd_scope_version AS v
            CROSS JOIN LATERAL jsonb_array_elements_text(
                coalesce(
                    v.pair_filter #> '{operational_branch_exclusion_policy,excluded_branches}',
                    '[]'::jsonb
                )
            ) AS old_exclusion(branch)
            WHERE v.scope_version_uuid = :scope_uuid
              AND NOT EXISTS (
                  SELECT 1 FROM src.sucursales_excluidas AS live
                  WHERE live.c_sucu_empr::integer = old_exclusion.branch::integer
              )
            ORDER BY branch
            """
        ),
        {"scope_uuid": scope_uuid},
    ).scalars().all()
    return tuple(rows)


def _guard_change(old_scope: dict, candidate: dict, excluded_branches: int) -> None:
    max_branches = int(os.getenv("PDD_AUTO_SCOPE_MAX_AFFECTED_BRANCHES", "5"))
    max_delta_percent = float(os.getenv("PDD_AUTO_SCOPE_MAX_DELTA_PERCENT", "10"))
    if max_branches < 1 or not 0 < max_delta_percent <= 100:
        raise ValueError("Limites de renovacion automatica de scope invalidos")
    if excluded_branches > max_branches:
        raise RuntimeError(
            f"Renovacion de scope requiere revision: {excluded_branches} sucursales "
            f"afectadas exceden el limite {max_branches}"
        )
    for field in ("article_count", "pair_count"):
        before = int(old_scope[field])
        after = int(candidate[field])
        if before <= 0 or after <= 0:
            raise RuntimeError(f"Renovacion de scope con {field} vacio")
        delta = abs(after - before) * 100 / before
        if delta > max_delta_percent:
            raise RuntimeError(
                f"Renovacion de scope requiere revision: {field} varia "
                f"{delta:.2f}% (limite {max_delta_percent:.2f}%)"
            )


def _guard_pair_membership(
    connection, old_scope_uuid: UUID, candidate_uuid: UUID, old_pair_count: int
) -> dict:
    change = dict(
        connection.execute(
            text(
                """
                WITH old_pairs AS (
                    SELECT codigo_articulo, destination_branch
                    FROM datamart.dm_pdd_scope_pair
                    WHERE scope_version_uuid = :old_scope_uuid
                ), new_pairs AS (
                    SELECT codigo_articulo, destination_branch
                    FROM datamart.dm_pdd_scope_pair
                    WHERE scope_version_uuid = :candidate_uuid
                )
                SELECT count(*) FILTER (
                           WHERE old_pairs.codigo_articulo IS NULL
                       ) AS added_pairs,
                       count(*) FILTER (
                           WHERE new_pairs.codigo_articulo IS NULL
                       ) AS removed_pairs
                FROM old_pairs FULL JOIN new_pairs
                    USING (codigo_articulo, destination_branch)
                WHERE old_pairs.codigo_articulo IS NULL
                   OR new_pairs.codigo_articulo IS NULL
                """
            ),
            {"old_scope_uuid": old_scope_uuid, "candidate_uuid": candidate_uuid},
        ).mappings().one()
    )
    churn_percent = _pair_churn_percent(
        change["added_pairs"], change["removed_pairs"], old_pair_count
    )
    max_percent = float(os.getenv("PDD_AUTO_SCOPE_MAX_DELTA_PERCENT", "10"))
    if churn_percent > max_percent:
        raise RuntimeError(
            "Renovacion de scope requiere revision: membresia de pares varia "
            f"{churn_percent:.2f}% (limite {max_percent:.2f}%)"
        )
    return {**change, "churn_percent": round(churn_percent, 3)}


def _pair_churn_percent(added_pairs: int, removed_pairs: int, old_pair_count: int) -> float:
    if old_pair_count <= 0 or min(added_pairs, removed_pairs) < 0:
        raise ValueError("Conteos de membresia de pares invalidos")
    return (added_pairs + removed_pairs) * 100 / old_pair_count


def _approve_candidate(
    engine: Engine,
    settings: Settings,
    candidate: dict,
    previous_scope_uuid: UUID,
    source_sync_run_uuid: UUID,
    business_date: date,
    pair_membership_change: dict,
) -> None:
    with engine.connect() as connection:
        require_frozen_scope(connection, candidate["scope_version_uuid"], settings.origin_cd)
        feature_through = connection.execute(
            text(
                """
                SELECT max(sales_date)
                FROM datamart.dm_pdd_venta_diaria
                WHERE scope_version_uuid = :scope_uuid
                """
            ),
            {"scope_uuid": candidate["scope_version_uuid"]},
        ).scalar_one()
    if feature_through is None or feature_through < business_date - timedelta(days=1):
        raise RuntimeError("Scope nuevo sin features hasta el cierre requerido")
    readiness = inspect_stock_readiness(
        engine, candidate["scope_version_uuid"], business_date, settings.origin_cd
    )
    if readiness.status != "READY":
        raise RuntimeError(
            "Scope nuevo no activable: " + ", ".join(readiness.blockers)
        )
    if candidate["status"] == "APPROVED":
        with engine.connect() as connection:
            approval = connection.execute(
                text(
                    """
                    SELECT detail #>> '{approval,approved_at}',
                           detail #>> '{approval,approved_by}'
                    FROM datamart.dm_pdd_scope_version
                    WHERE scope_version_uuid = :scope_uuid
                    """
                ),
                {"scope_uuid": candidate["scope_version_uuid"]},
            ).one()
        if not all(approval):
            raise RuntimeError("Scope APPROVED sin metadatos de aprobacion")
        return
    with transactional_connection(engine, settings) as connection:
        row = connection.execute(
            text(
                """
                UPDATE datamart.dm_pdd_scope_version
                SET status = 'APPROVED',
                    detail = coalesce(detail, '{}'::jsonb) ||
                        jsonb_build_object('approval', jsonb_build_object(
                            'environment', 'PROD',
                            'approved_at', clock_timestamp(),
                            'approved_by', :actor,
                            'reason', 'Renovacion automatica por sucursales excluidas',
                            'previous_scope_uuid', :previous_scope_uuid,
                            'source_sync_run_uuid', :source_sync_run_uuid,
                            'max_delta_percent', :max_delta_percent,
                            'added_pairs', :added_pairs,
                            'removed_pairs', :removed_pairs,
                            'pair_churn_percent', :pair_churn_percent
                        ))
                WHERE scope_version_uuid = :scope_uuid
                  AND status = 'DRAFT'
                  AND scope_checksum = :scope_checksum
                RETURNING scope_version_uuid
                """
            ),
            {
                "actor": AUTO_ACTOR,
                "previous_scope_uuid": str(previous_scope_uuid),
                "source_sync_run_uuid": str(source_sync_run_uuid),
                "max_delta_percent": float(
                    os.getenv("PDD_AUTO_SCOPE_MAX_DELTA_PERCENT", "10")
                ),
                "added_pairs": pair_membership_change["added_pairs"],
                "removed_pairs": pair_membership_change["removed_pairs"],
                "pair_churn_percent": pair_membership_change["churn_percent"],
                "scope_uuid": candidate["scope_version_uuid"],
                "scope_checksum": candidate["scope_checksum"],
            },
        ).scalar_one_or_none()
        if row is None:
            raise RuntimeError("El scope candidato cambio durante la aprobacion")


def ensure_daily_scope(
    settings: Settings,
    backfill: Callable[[UUID, date], None],
) -> dict:
    """Repara solo el drift de sucursales excluidas antes del flujo diario."""
    if settings.runtime_environment not in {"TEST", "PROD"}:
        return {"status": "SKIPPED", "reason": "ENVIRONMENT_NOT_AUTOMATED"}
    enabled = os.getenv("PDD_AUTO_SCOPE_ENABLED", "true").strip().lower()
    if enabled in {"false", "0", "off", "no"}:
        return {"status": "SKIPPED", "reason": "AUTO_SCOPE_DISABLED"}
    if enabled not in {"true", "1", "on", "yes"}:
        raise ValueError("PDD_AUTO_SCOPE_ENABLED invalido")
    engine = build_engine(settings)
    lock_name = "pdd.scope.maintenance.daily"
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_connection:
            lock_connection.execute(
                text("SELECT pg_advisory_lock(hashtext(:name))"), {"name": lock_name}
            )
            try:
                source = _source_contract(lock_connection)
                business_date = source["business_date"]
                binding = read_active_runtime_binding(
                    lock_connection,
                    settings.runtime_environment,
                    settings.runtime_process_code,
                )
                if binding is None:
                    raise RuntimeError("No existe binding runtime activo para renovar el scope")
                if business_date < binding.effective_business_date:
                    raise RuntimeError(
                        "El contrato de fuentes precede al binding runtime activo"
                    )
                old_scope = dict(
                    lock_connection.execute(
                        text(
                            """
                            SELECT article_count, pair_count
                            FROM datamart.dm_pdd_scope_version
                            WHERE scope_version_uuid = :scope_uuid
                            """
                        ),
                        {"scope_uuid": binding.scope_version_uuid},
                    ).mappings().one()
                )
                readiness = inspect_stock_readiness(
                    engine, binding.scope_version_uuid, business_date,
                    settings.origin_cd,
                )
                reopened_branches = _reopened_branches(
                    lock_connection, binding.scope_version_uuid
                )
                if readiness.status == "READY" and not reopened_branches:
                    return {"status": "CURRENT", "scope_version_uuid": str(binding.scope_version_uuid)}
                if readiness.blockers and set(readiness.blockers) != {SCOPE_BLOCKER}:
                    return {
                        "status": "BLOCKED_OTHER",
                        "blockers": list(readiness.blockers),
                    }
                candidate = _candidate(lock_connection, binding.scope_version_uuid)
                if candidate is None:
                    version_no = lock_connection.execute(
                        text(
                            """
                            SELECT coalesce(max(version_no), 0) + 1
                            FROM datamart.dm_pdd_scope_version
                            WHERE scope_code = 'CD41_DISTRIBUTABLE_ASSORTMENT'
                            """
                        )
                    ).scalar_one()
                    candidate_uuid = uuid4()
                    capture_scope_snapshot(
                        engine, settings, candidate_uuid, version_no, business_date,
                        AUTO_ACTOR, binding.scope_version_uuid,
                    )
                    candidate = _candidate(lock_connection, binding.scope_version_uuid)
                    if candidate is None or candidate["scope_version_uuid"] != candidate_uuid:
                        raise RuntimeError("El scope nuevo conserva sucursales excluidas")
                affected_branches = set(readiness.excluded_branches) | set(reopened_branches)
                _guard_change(old_scope, candidate, len(affected_branches))
                pair_membership_change = _guard_pair_membership(
                    lock_connection,
                    binding.scope_version_uuid,
                    candidate["scope_version_uuid"],
                    old_scope["pair_count"],
                )
                candidate_readiness = inspect_stock_readiness(
                    engine, candidate["scope_version_uuid"], business_date,
                    settings.origin_cd,
                )
                if candidate_readiness.status != "READY":
                    raise RuntimeError(
                        "Scope candidato sin fuentes operativas completas: "
                        + ", ".join(candidate_readiness.blockers)
                        + f"; pares_sin_stock={candidate_readiness.unexplained_missing_pairs}"
                    )
                if candidate["status"] == "DRAFT":
                    backfill(candidate["scope_version_uuid"], business_date)
                _approve_candidate(
                    engine, settings, candidate, binding.scope_version_uuid,
                    source["source_sync_run_uuid"], business_date,
                    pair_membership_change,
                )
                activated, reused = activate_runtime_binding(
                    engine, settings,
                    environment=settings.runtime_environment,
                    process_code=settings.runtime_process_code,
                    scope_version_uuid=candidate["scope_version_uuid"],
                    model_version_uuid=binding.model_version_uuid,
                    configuration_version_uuid=binding.configuration_version_uuid,
                    pipeline_revision=binding.pipeline_revision,
                    effective_business_date=business_date,
                    activated_by=AUTO_ACTOR,
                    reason=(
                        "Renovacion automatica de scope por cambios de sucursales "
                        + ",".join(str(v) for v in sorted(affected_branches))
                    ),
                )
                return {
                    "status": "ACTIVATED",
                    "environment": settings.runtime_environment,
                    "scope_version_uuid": str(activated.scope_version_uuid),
                    "runtime_revision": activated.revision_no,
                    "reused_binding": reused,
                    "excluded_branches": list(readiness.excluded_branches),
                    "excluded_branch_pairs": readiness.excluded_branch_pairs,
                    "reopened_branches": list(reopened_branches),
                    "pair_membership_change": pair_membership_change,
                }
            finally:
                try:
                    lock_connection.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:name))"),
                        {"name": lock_name},
                    )
                except Exception:
                    lock_connection.invalidate()
                    raise
    finally:
        engine.dispose()
