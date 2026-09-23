from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from .config import Settings
from .db import transactional_connection
from .model_registry import load_model_version
from .operational_registry import load_operational_configuration
from .jobs.common import require_frozen_scope
from .jobs.operational_inputs import inspect_stock_readiness


RUNTIME_ENVIRONMENTS = ("TEST", "DESA", "PROD")
DEFAULT_RUNTIME_PROCESS = "DAILY_MASTER"


@dataclass(frozen=True)
class RuntimeBinding:
    runtime_binding_uuid: UUID
    environment: str
    process_code: str
    revision_no: int
    scope_version_uuid: UUID
    model_version_uuid: UUID
    configuration_version_uuid: UUID
    pipeline_revision: str
    effective_business_date: date
    status: str
    activated_at: datetime
    activated_by: str
    reason: str
    supersedes_runtime_binding_uuid: UUID | None
    detail: dict[str, Any]

    def serializable(self) -> dict[str, Any]:
        result = asdict(self)
        for key, value in tuple(result.items()):
            if isinstance(value, UUID):
                result[key] = str(value)
            elif isinstance(value, (date, datetime)):
                result[key] = value.isoformat()
        return result


@dataclass(frozen=True)
class RuntimeSelection:
    scope_version_uuid: UUID
    model_version_uuid: UUID
    configuration_version_uuid: UUID
    pipeline_revision: str
    source: str
    runtime_binding_uuid: UUID | None = None
    revision_no: int | None = None
    effective_business_date: date | None = None

    def serializable(self) -> dict[str, Any]:
        result = asdict(self)
        for key, value in tuple(result.items()):
            if isinstance(value, UUID):
                result[key] = str(value)
            elif isinstance(value, (date, datetime)):
                result[key] = value.isoformat()
        return result


def normalize_runtime_environment(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in RUNTIME_ENVIRONMENTS:
        raise ValueError(
            f"Ambiente runtime invalido: {value!r}; permitidos={RUNTIME_ENVIRONMENTS}"
        )
    return normalized


def normalize_process_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        for character in normalized
    ):
        raise ValueError(f"Codigo de proceso runtime invalido: {value!r}")
    return normalized


def _binding_from_row(row: dict[str, Any]) -> RuntimeBinding:
    detail = row.get("detail") or {}
    if isinstance(detail, str):
        detail = json.loads(detail)
    return RuntimeBinding(**{**row, "detail": detail})


def read_active_runtime_binding(
    connection: Connection,
    environment: str,
    process_code: str = DEFAULT_RUNTIME_PROCESS,
) -> RuntimeBinding | None:
    row = connection.execute(
        text(
            """
            SELECT runtime_binding_uuid,environment,process_code,revision_no,
                   scope_version_uuid,model_version_uuid,
                   configuration_version_uuid,pipeline_revision,
                   effective_business_date,status,activated_at,activated_by,
                   reason,supersedes_runtime_binding_uuid,detail
            FROM audit.pdd_runtime_binding
            WHERE environment=:environment
              AND process_code=:process_code
              AND status='ACTIVE'
            """
        ),
        {
            "environment": normalize_runtime_environment(environment),
            "process_code": normalize_process_code(process_code),
        },
    ).mappings().one_or_none()
    return _binding_from_row(dict(row)) if row else None


def list_runtime_bindings(
    connection: Connection,
    environment: str,
    process_code: str = DEFAULT_RUNTIME_PROCESS,
    limit: int = 20,
) -> tuple[RuntimeBinding, ...]:
    if limit <= 0 or limit > 500:
        raise ValueError("limit debe estar entre 1 y 500")
    rows = connection.execute(
        text(
            """
            SELECT runtime_binding_uuid,environment,process_code,revision_no,
                   scope_version_uuid,model_version_uuid,
                   configuration_version_uuid,pipeline_revision,
                   effective_business_date,status,activated_at,activated_by,
                   reason,supersedes_runtime_binding_uuid,detail
            FROM audit.pdd_runtime_binding
            WHERE environment=:environment AND process_code=:process_code
            ORDER BY revision_no DESC
            LIMIT :limit
            """
        ),
        {
            "environment": normalize_runtime_environment(environment),
            "process_code": normalize_process_code(process_code),
            "limit": limit,
        },
    ).mappings().all()
    return tuple(_binding_from_row(dict(row)) for row in rows)


def resolve_runtime_selection(
    connection: Connection,
    environment: str,
    process_code: str,
    *,
    explicit_scope_uuid: UUID | None = None,
    explicit_model_uuid: UUID | None = None,
    explicit_configuration_uuid: UUID | None = None,
    explicit_pipeline_revision: str | None = None,
    legacy_scope_uuid: UUID | None = None,
    legacy_model_uuid: UUID | None = None,
    default_configuration_uuid: UUID | None = None,
    default_pipeline_revision: str | None = None,
) -> RuntimeSelection:
    binding = read_active_runtime_binding(connection, environment, process_code)
    scope_uuid = explicit_scope_uuid or (
        binding.scope_version_uuid if binding else legacy_scope_uuid
    )
    model_uuid = explicit_model_uuid or (
        binding.model_version_uuid if binding else legacy_model_uuid
    )
    configuration_uuid = explicit_configuration_uuid or (
        binding.configuration_version_uuid if binding else default_configuration_uuid
    )
    pipeline_revision = (
        explicit_pipeline_revision
        or (binding.pipeline_revision if binding else None)
        or default_pipeline_revision
    )
    missing = [
        name
        for name, value in (
            ("scope_version_uuid", scope_uuid),
            ("model_version_uuid", model_uuid),
            ("configuration_version_uuid", configuration_uuid),
            ("pipeline_revision", pipeline_revision),
        )
        if value is None or (isinstance(value, str) and not value.strip())
    ]
    if missing:
        raise RuntimeError(
            "Configuracion runtime incompleta para "
            f"{normalize_runtime_environment(environment)}/{normalize_process_code(process_code)}: "
            + ", ".join(missing)
        )
    if all(
        value is None
        for value in (
            explicit_scope_uuid,
            explicit_model_uuid,
            explicit_configuration_uuid,
            explicit_pipeline_revision,
        )
    ):
        source = "RUNTIME_BINDING" if binding else "LEGACY_ENV"
    else:
        source = "EXPLICIT_OVERRIDE"
    return RuntimeSelection(
        scope_version_uuid=scope_uuid,
        model_version_uuid=model_uuid,
        configuration_version_uuid=configuration_uuid,
        pipeline_revision=pipeline_revision.strip().upper(),
        source=source,
        runtime_binding_uuid=binding.runtime_binding_uuid if binding else None,
        revision_no=binding.revision_no if binding else None,
        effective_business_date=(
            binding.effective_business_date
            if binding and source == "RUNTIME_BINDING" else None
        ),
    )


def _validate_runtime_candidate(
    source_engine: Engine,
    settings: Settings,
    environment: str,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    configuration_version_uuid: UUID,
    effective_business_date: date,
) -> dict[str, Any]:
    model = load_model_version(model_version_uuid)
    configuration = load_operational_configuration(configuration_version_uuid)
    if configuration.valid_from > effective_business_date:
        raise RuntimeError(
            f"Configuracion {configuration_version_uuid} vigente desde "
            f"{configuration.valid_from}; fecha efectiva solicitada="
            f"{effective_business_date}"
        )
    with source_engine.connect() as connection:
        require_frozen_scope(connection, scope_version_uuid, settings.origin_cd)
        scope = connection.execute(
            text(
                """
                SELECT status,business_date,scope_checksum,article_count,pair_count,
                       (SELECT max(sales_date)
                        FROM datamart.dm_pdd_venta_diaria
                        WHERE scope_version_uuid=:scope_uuid) AS feature_through
                FROM datamart.dm_pdd_scope_version
                WHERE scope_version_uuid=:scope_uuid
                """
            ),
            {"scope_uuid": scope_version_uuid},
        ).mappings().one()
    cutoff_date = effective_business_date - timedelta(days=1)
    if scope["feature_through"] is None or scope["feature_through"] < cutoff_date:
        raise RuntimeError(
            f"Scope {scope_version_uuid} sin backfill hasta {cutoff_date}; "
            f"disponible={scope['feature_through']}"
        )
    normalized_environment = normalize_runtime_environment(environment)
    if normalized_environment == "PROD":
        if scope["status"] != "APPROVED":
            raise RuntimeError("PROD requiere un scope APPROVED")
        if model.status not in {"APPROVED", "ACTIVE"}:
            raise RuntimeError("PROD requiere un modelo APPROVED o ACTIVE")
        if configuration.status not in {"APPROVED", "ACTIVE"}:
            raise RuntimeError("PROD requiere una configuracion APPROVED o ACTIVE")
    readiness = inspect_stock_readiness(
        source_engine,
        scope_version_uuid,
        effective_business_date,
        settings.origin_cd,
    )
    if readiness.status != "READY":
        raise RuntimeError(
            "Scope no activable; readiness bloqueado: " + ", ".join(readiness.blockers)
        )
    return {
        "scope_status": scope["status"],
        "scope_business_date": scope["business_date"].isoformat(),
        "scope_checksum": scope["scope_checksum"],
        "article_count": int(scope["article_count"]),
        "pair_count": int(scope["pair_count"]),
        "feature_through": scope["feature_through"].isoformat(),
        "model_code": model.model_code,
        "model_version_no": model.version_no,
        "model_status": model.status,
        "configuration_code": configuration.configuration_code,
        "configuration_version_no": configuration.version_no,
        "configuration_status": configuration.status,
        "readiness": readiness.serializable(),
    }


def activate_runtime_binding(
    engine: Engine,
    settings: Settings,
    *,
    environment: str,
    process_code: str,
    scope_version_uuid: UUID,
    model_version_uuid: UUID,
    configuration_version_uuid: UUID,
    pipeline_revision: str,
    effective_business_date: date,
    activated_by: str,
    reason: str,
) -> tuple[RuntimeBinding, bool]:
    if not activated_by.strip() or not reason.strip():
        raise ValueError("activated_by y reason son obligatorios")
    environment = normalize_runtime_environment(environment)
    process_code = normalize_process_code(process_code)
    pipeline_revision = pipeline_revision.strip().upper()
    if not pipeline_revision:
        raise ValueError("pipeline_revision es obligatorio")
    validation = _validate_runtime_candidate(
        engine,
        settings,
        environment,
        scope_version_uuid,
        model_version_uuid,
        configuration_version_uuid,
        effective_business_date,
    )
    with transactional_connection(engine, settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_name))"),
            {"lock_name": f"pdd.runtime:{environment}:{process_code}"},
        )
        current = read_active_runtime_binding(connection, environment, process_code)
        if current and (
            current.scope_version_uuid == scope_version_uuid
            and current.model_version_uuid == model_version_uuid
            and current.configuration_version_uuid == configuration_version_uuid
            and current.pipeline_revision == pipeline_revision
            and current.effective_business_date == effective_business_date
        ):
            return current, True
        revision_no = int(
            connection.execute(
                text(
                    """
                    SELECT coalesce(max(revision_no),0)+1
                    FROM audit.pdd_runtime_binding
                    WHERE environment=:environment AND process_code=:process_code
                    """
                ),
                {"environment": environment, "process_code": process_code},
            ).scalar_one()
        )
        if current:
            connection.execute(
                text(
                    """
                    UPDATE audit.pdd_runtime_binding
                    SET status='SUPERSEDED',superseded_at=clock_timestamp(),
                        superseded_by=:actor
                    WHERE runtime_binding_uuid=:binding_uuid AND status='ACTIVE'
                    """
                ),
                {
                    "actor": activated_by.strip(),
                    "binding_uuid": current.runtime_binding_uuid,
                },
            )
        binding_uuid = uuid4()
        row = connection.execute(
            text(
                """
                INSERT INTO audit.pdd_runtime_binding (
                    runtime_binding_uuid,environment,process_code,revision_no,
                    scope_version_uuid,model_version_uuid,
                    configuration_version_uuid,pipeline_revision,
                    effective_business_date,status,activated_by,reason,
                    supersedes_runtime_binding_uuid,detail
                ) VALUES (
                    :binding_uuid,:environment,:process_code,:revision_no,
                    :scope_uuid,:model_uuid,:configuration_uuid,:pipeline_revision,
                    :effective_business_date,'ACTIVE',:actor,:reason,
                    :supersedes_uuid,CAST(:detail AS jsonb)
                )
                RETURNING runtime_binding_uuid,environment,process_code,revision_no,
                          scope_version_uuid,model_version_uuid,
                          configuration_version_uuid,pipeline_revision,
                          effective_business_date,status,activated_at,activated_by,
                          reason,supersedes_runtime_binding_uuid,detail
                """
            ),
            {
                "binding_uuid": binding_uuid,
                "environment": environment,
                "process_code": process_code,
                "revision_no": revision_no,
                "scope_uuid": scope_version_uuid,
                "model_uuid": model_version_uuid,
                "configuration_uuid": configuration_version_uuid,
                "pipeline_revision": pipeline_revision,
                "effective_business_date": effective_business_date,
                "actor": activated_by.strip(),
                "reason": reason.strip(),
                "supersedes_uuid": (
                    current.runtime_binding_uuid if current else None
                ),
                "detail": json.dumps(validation, default=str, sort_keys=True),
            },
        ).mappings().one()
    return _binding_from_row(dict(row)), False


def rollback_runtime_binding(
    engine: Engine,
    settings: Settings,
    *,
    environment: str,
    process_code: str,
    target_revision_no: int,
    effective_business_date: date,
    activated_by: str,
    reason: str,
) -> RuntimeBinding:
    with engine.connect() as connection:
        target = connection.execute(
            text(
                """
                SELECT scope_version_uuid,model_version_uuid,
                       configuration_version_uuid,pipeline_revision
                FROM audit.pdd_runtime_binding
                WHERE environment=:environment AND process_code=:process_code
                  AND revision_no=:revision_no
                """
            ),
            {
                "environment": normalize_runtime_environment(environment),
                "process_code": normalize_process_code(process_code),
                "revision_no": target_revision_no,
            },
        ).mappings().one_or_none()
    if target is None:
        raise RuntimeError(f"Revision runtime inexistente: {target_revision_no}")
    binding, _ = activate_runtime_binding(
        engine,
        settings,
        environment=environment,
        process_code=process_code,
        scope_version_uuid=target["scope_version_uuid"],
        model_version_uuid=target["model_version_uuid"],
        configuration_version_uuid=target["configuration_version_uuid"],
        pipeline_revision=target["pipeline_revision"],
        effective_business_date=effective_business_date,
        activated_by=activated_by,
        reason=f"ROLLBACK_TO_REVISION_{target_revision_no}: {reason.strip()}",
    )
    return binding
