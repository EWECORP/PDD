from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, text

from ..config import OperationalSettings
from ..db import transactional_connection
from .backlog import BacklogPublicationResult, publish_current_backlog


SIMULATION_TYPES = ("E", "C", "A")
SIMULATION_REASON = "SIMULATED_FRONTEND_TEST_DATA"
_BATCH_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,39}$")


@dataclass(frozen=True)
class DirectedNeedSimulationResult:
    batch_code: str
    business_date: date
    daily_calculation_run_uuid: UUID
    header_count: int
    line_count: int
    shared_pair_count: int
    reused_seed: bool
    type_totals: dict[str, Decimal]
    target_database: str
    target_environment: str

    def serializable(self) -> dict[str, Any]:
        return {**self.__dict__}


@dataclass(frozen=True)
class SimulationPipelineResult:
    simulation: DirectedNeedSimulationResult
    backlog: BacklogPublicationResult

    def serializable(self) -> dict[str, Any]:
        return {
            "simulation": self.simulation.serializable(),
            "backlog": self.backlog.serializable(),
        }


def normalize_batch_code(batch_code: str) -> str:
    normalized = batch_code.strip().upper()
    if not _BATCH_PATTERN.fullmatch(normalized):
        raise ValueError(
            "batch_code debe tener entre 3 y 40 caracteres A-Z, 0-9, _ o -"
        )
    return normalized


def simulation_backlog_run_uuid(
    target_environment: str,
    target_database: str,
    daily_calculation_run_uuid: UUID,
    batch_code: str,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        "connexa:pdd:simulated-eca-backlog:"
        f"{target_environment}:{target_database}:"
        f"{daily_calculation_run_uuid}:{normalize_batch_code(batch_code)}",
    )


def allocate_simulation_pairs(
    candidates: Sequence[Mapping[str, Any]],
    lines_per_type: int,
    shared_pairs: int,
) -> dict[str, list[dict[str, Any]]]:
    if lines_per_type < 2 or lines_per_type > 50:
        raise ValueError("lines_per_type debe estar entre 2 y 50")
    if shared_pairs < 1 or shared_pairs >= lines_per_type:
        raise ValueError("shared_pairs debe estar entre 1 y lines_per_type-1")
    required = shared_pairs + len(SIMULATION_TYPES) * (
        lines_per_type - shared_pairs
    )
    if len(candidates) < required:
        raise ValueError(
            f"Pares elegibles insuficientes para la simulacion: {len(candidates)}/{required}"
        )
    shared = [dict(row) for row in candidates[:shared_pairs]]
    cursor = shared_pairs
    allocated: dict[str, list[dict[str, Any]]] = {}
    exclusive_count = lines_per_type - shared_pairs
    for need_type in SIMULATION_TYPES:
        exclusive = [
            dict(row) for row in candidates[cursor : cursor + exclusive_count]
        ]
        allocated[need_type] = [*shared, *exclusive]
        cursor += exclusive_count
    return allocated


def build_simulated_line_specs(
    allocated: Mapping[str, Sequence[Mapping[str, Any]]],
    business_date: date,
) -> dict[str, list[dict[str, Any]]]:
    bases = {"E": Decimal("24"), "C": Decimal("36"), "A": Decimal("18")}
    increments = {"E": Decimal("6"), "C": Decimal("12"), "A": Decimal("6")}
    target_offsets = {"E": 2, "C": 7, "A": 14}
    result: dict[str, list[dict[str, Any]]] = {}
    for need_type in SIMULATION_TYPES:
        lines: list[dict[str, Any]] = []
        for index, pair in enumerate(allocated[need_type]):
            original = bases[need_type] + increments[need_type] * index
            prepared = original / Decimal("4") if index == 0 else Decimal("0")
            cancelled = Decimal("0")
            lines.append(
                {
                    **dict(pair),
                    "original_quantity": original,
                    "prepared_allocated_quantity": prepared,
                    "cancelled_quantity": cancelled,
                    "open_quantity": original - prepared - cancelled,
                    "target_date": business_date
                    + timedelta(days=target_offsets[need_type] + index),
                    "status": "PARTIAL" if prepared > 0 else "OPEN",
                }
            )
        result[need_type] = lines
    return result


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _validate_environment(settings: OperationalSettings) -> None:
    if settings.target_environment != "DESA":
        raise RuntimeError(
            "La carga simulada E/C/A solo esta habilitada en el ambiente DESA"
        )


def _read_daily_run(connection, daily_calculation_run_uuid: UUID | None):
    rows = connection.execute(
        text(
            """
            SELECT r.calculation_run_id,r.calculation_run_uuid,r.business_date,
                   r.status,r.is_current,s.origin_cd
            FROM stock_management.pdd_calculation_run r
            JOIN stock_management.pdd_distribution_scope_version s
              ON s.scope_version_id=r.scope_version_id
            WHERE r.run_type='DAILY_DECAS'
              AND r.status='SUCCEEDED' AND r.is_current
              AND (
                    CAST(:daily_uuid AS uuid) IS NULL
                    OR r.calculation_run_uuid=CAST(:daily_uuid AS uuid)
              )
            ORDER BY r.business_date DESC,r.calculation_run_id DESC
            LIMIT 2
            """
        ),
        {
            "daily_uuid": (
                str(daily_calculation_run_uuid)
                if daily_calculation_run_uuid is not None
                else None
            )
        },
    ).mappings().all()
    if len(rows) != 1:
        raise RuntimeError(
            "No se encontro una unica corrida DAILY_DECAS vigente y exitosa"
        )
    if rows[0]["origin_cd"] != 41:
        raise RuntimeError("La corrida DAILY_DECAS no pertenece al CD 41")
    return rows[0]


def _read_candidates(
    connection,
    daily_run_id: int,
    batch_code: str,
    required: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            """
            SELECT n.sucursal,n.codigo_articulo,n.c_proveedor_primario,
                   l.units_per_package,l.packages_per_pallet,
                   l.unit_weight_kg,l.unit_volume_m3
            FROM stock_management.pdd_need_snapshot n
            LEFT JOIN stock_management.pdd_item_logistics_snapshot l
              ON l.item_logistics_snapshot_id=n.logistics_snapshot_id
            WHERE n.calculation_run_id=:daily_run_id
              AND n.need_type='D' AND n.calculation_status='CALCULATED'
              AND NOT EXISTS (
                  SELECT 1
                  FROM stock_management.pdd_directed_need d0
                  JOIN stock_management.pdd_directed_need_line l0
                    ON l0.directed_need_id=d0.directed_need_id
                  WHERE d0.status='ACTIVE' AND l0.open_quantity>0
                    AND l0.sucursal=n.sucursal
                    AND l0.codigo_articulo=n.codigo_articulo
              )
            ORDER BY md5(
                :batch_code || ':' || n.sucursal::text || ':' || n.codigo_articulo::text
            )
            LIMIT :required
            """
        ),
        {
            "daily_run_id": daily_run_id,
            "batch_code": batch_code,
            "required": required,
        },
    ).mappings().all()
    return [dict(row) for row in rows]


def _validate_seed(
    connection,
    daily_run_id: int,
    business_date: date,
    references: Sequence[str],
    expected_lines: int,
) -> tuple[dict[str, Decimal], int]:
    validation = connection.execute(
        text(
            """
            SELECT count(DISTINCT d.directed_need_id)::integer AS headers,
                   count(*)::integer AS lines,
                   count(DISTINCT d.need_type)::integer AS types,
                   count(*) FILTER (
                       WHERE d.status<>'ACTIVE'
                          OR d.approver_user IS NULL OR d.approved_at IS NULL
                          OR d.valid_from>:business_date
                          OR (d.valid_to IS NOT NULL AND d.valid_to<:business_date)
                   )::integer AS invalid_headers,
                   count(*) FILTER (
                       WHERE l.open_quantity<=0
                          OR l.original_quantity-l.prepared_allocated_quantity
                             -l.cancelled_quantity<>l.open_quantity
                   )::integer AS invalid_lines,
                   count(*) FILTER (
                       WHERE b.branch_stock_position_id IS NULL
                   )::integer AS orphan_lines,
                   count(v.directed_need_version_id)::integer AS version_rows
            FROM stock_management.pdd_directed_need d
            JOIN stock_management.pdd_directed_need_line l
              ON l.directed_need_id=d.directed_need_id
            LEFT JOIN stock_management.pdd_directed_need_version v
              ON v.directed_need_id=d.directed_need_id AND v.version_no=d.version_no
            LEFT JOIN stock_management.pdd_branch_stock_position b
              ON b.calculation_run_id=:daily_run_id
             AND b.sucursal=l.sucursal AND b.codigo_articulo=l.codigo_articulo
            WHERE d.business_reference=ANY(CAST(:references AS varchar[]))
            """
        ),
        {
            "daily_run_id": daily_run_id,
            "business_date": business_date,
            "references": list(references),
        },
    ).mappings().one()
    if (
        validation["headers"] != len(SIMULATION_TYPES)
        or validation["lines"] != expected_lines
        or validation["types"] != len(SIMULATION_TYPES)
        or validation["invalid_headers"]
        or validation["invalid_lines"]
        or validation["orphan_lines"]
        or validation["version_rows"] != expected_lines
    ):
        raise RuntimeError(f"Validacion E/C/A simulada fallida: {dict(validation)}")
    totals = {
        row["need_type"]: Decimal(row["open_quantity"])
        for row in connection.execute(
            text(
                """
                SELECT d.need_type,
                       sum(l.open_quantity)::numeric AS open_quantity
                FROM stock_management.pdd_directed_need d
                JOIN stock_management.pdd_directed_need_line l
                  ON l.directed_need_id=d.directed_need_id
                WHERE d.business_reference=ANY(CAST(:references AS varchar[]))
                GROUP BY d.need_type
                ORDER BY d.need_type
                """
            ),
            {"references": list(references)},
        ).mappings()
    }
    return totals, validation["lines"]


def seed_simulated_directed_needs(
    target_engine: Engine,
    target_settings: OperationalSettings,
    batch_code: str,
    created_by: str,
    lines_per_type: int = 6,
    shared_pairs: int = 2,
    daily_calculation_run_uuid: UUID | None = None,
) -> DirectedNeedSimulationResult:
    _validate_environment(target_settings)
    normalized_batch = normalize_batch_code(batch_code)
    actor = created_by.strip()
    if not actor:
        raise ValueError("created_by es obligatorio")
    required = shared_pairs + len(SIMULATION_TYPES) * (
        lines_per_type - shared_pairs
    )
    references = [
        f"SIM-FRONTEND-{normalized_batch}-{need_type}"
        for need_type in SIMULATION_TYPES
    ]
    if any(len(reference) > 120 for reference in references):
        raise ValueError("La referencia simulada supera 120 caracteres")

    with transactional_connection(target_engine, target_settings) as connection:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('pdd.simulate.directed-needs'))")
        )
        missing = connection.execute(
            text(
                """
                SELECT array_agg(name ORDER BY name)
                FROM unnest(ARRAY[
                    'stock_management.pdd_calculation_run',
                    'stock_management.pdd_distribution_scope_version',
                    'stock_management.pdd_need_snapshot',
                    'stock_management.pdd_branch_stock_position',
                    'stock_management.pdd_directed_need',
                    'stock_management.pdd_directed_need_line',
                    'stock_management.pdd_directed_need_version'
                ]) required(name)
                WHERE to_regclass(name) IS NULL
                """
            )
        ).scalar_one()
        if missing:
            raise RuntimeError(f"Contrato operativo incompleto: {missing}")
        daily = _read_daily_run(connection, daily_calculation_run_uuid)
        existing = connection.execute(
            text(
                """
                SELECT directed_need_id,business_reference,status,reason,notes
                FROM stock_management.pdd_directed_need
                WHERE business_reference=ANY(CAST(:references AS varchar[]))
                ORDER BY business_reference
                """
            ),
            {"references": references},
        ).mappings().all()
        if existing and len(existing) != len(SIMULATION_TYPES):
            raise RuntimeError("El lote simulado existe de forma parcial")
        if existing:
            if any(
                row["status"] != "ACTIVE" or row["reason"] != SIMULATION_REASON
                for row in existing
            ):
                raise RuntimeError(
                    "El batch_code ya corresponde a un lote no reutilizable"
                )
            seed_parameters = [json.loads(row["notes"] or "{}") for row in existing]
            if any(
                parameters.get("linesPerType") != lines_per_type
                or parameters.get("sharedPairs") != shared_pairs
                for parameters in seed_parameters
            ):
                raise RuntimeError(
                    "El batch_code ya existe con otros parametros de simulacion"
                )
            reused_seed = True
        else:
            reused_seed = False
            candidates = _read_candidates(
                connection,
                daily["calculation_run_id"],
                normalized_batch,
                required,
            )
            allocated = allocate_simulation_pairs(
                candidates,
                lines_per_type,
                shared_pairs,
            )
            line_specs = build_simulated_line_specs(
                allocated,
                daily["business_date"],
            )
            correlation_id = uuid5(
                NAMESPACE_URL,
                f"connexa:pdd:simulated-eca:{normalized_batch}",
            )
            for need_type, reference in zip(SIMULATION_TYPES, references):
                directed_need_uuid = uuid5(
                    NAMESPACE_URL,
                    f"connexa:pdd:simulated-eca:{normalized_batch}:{need_type}",
                )
                directed_need_id = connection.execute(
                    text(
                        """
                        INSERT INTO stock_management.pdd_directed_need (
                            directed_need_uuid,origin_cd,need_type,business_reference,
                            c_proveedor_primario,valid_from,valid_to,priority_score,
                            owner_user,approver_user,status,version_no,reason,notes,
                            created_by,updated_by,approved_at
                        ) VALUES (
                            CAST(:uuid AS uuid),41,:need_type,:reference,NULL,
                            :valid_from,:valid_to,:priority_score,
                            :actor,:actor,'ACTIVE',1,:reason,:notes,
                            :actor,:actor,clock_timestamp()
                        ) RETURNING directed_need_id
                        """
                    ),
                    {
                        "uuid": directed_need_uuid,
                        "need_type": need_type,
                        "reference": reference,
                        "valid_from": daily["business_date"],
                        "valid_to": daily["business_date"] + timedelta(days=30),
                        "priority_score": {
                            "E": Decimal("95"),
                            "C": Decimal("75"),
                            "A": Decimal("40"),
                        }[need_type],
                        "actor": actor,
                        "reason": SIMULATION_REASON,
                        "notes": _json(
                            {
                                "simulation": True,
                                "batchCode": normalized_batch,
                                "dailyCalculationRunUuid": str(
                                    daily["calculation_run_uuid"]
                                ),
                                "linesPerType": lines_per_type,
                                "sharedPairs": shared_pairs,
                            }
                        ),
                    },
                ).scalar_one()
                for line in line_specs[need_type]:
                    connection.execute(
                        text(
                            """
                            INSERT INTO stock_management.pdd_directed_need_line (
                                directed_need_id,sucursal,codigo_articulo,
                                original_quantity,prepared_allocated_quantity,
                                cancelled_quantity,target_date,unit_code,
                                units_per_package,packages_per_pallet,
                                unit_weight_kg,unit_volume_m3,status
                            ) VALUES (
                                :directed_need_id,:sucursal,:codigo_articulo,
                                :original_quantity,:prepared_allocated_quantity,
                                :cancelled_quantity,:target_date,'UN',
                                :units_per_package,:packages_per_pallet,
                                :unit_weight_kg,:unit_volume_m3,:status
                            )
                            """
                        ),
                        {**line, "directed_need_id": directed_need_id},
                    )
                after_state = {
                    "directedNeedUuid": str(directed_need_uuid),
                    "needType": need_type,
                    "businessReference": reference,
                    "status": "ACTIVE",
                    "simulation": True,
                    "batchCode": normalized_batch,
                    "lines": line_specs[need_type],
                }
                connection.execute(
                    text(
                        """
                        INSERT INTO stock_management.pdd_directed_need_version (
                            directed_need_id,version_no,changed_by,change_reason,
                            before_state,after_state,correlation_id
                        ) VALUES (
                            :directed_need_id,1,:actor,:reason,NULL,
                            CAST(:after_state AS jsonb),CAST(:correlation_id AS uuid)
                        )
                        """
                    ),
                    {
                        "directed_need_id": directed_need_id,
                        "actor": actor,
                        "reason": SIMULATION_REASON,
                        "after_state": _json(after_state),
                        "correlation_id": correlation_id,
                    },
                )

        totals, persisted_lines = _validate_seed(
            connection,
            daily["calculation_run_id"],
            daily["business_date"],
            references,
            len(SIMULATION_TYPES) * lines_per_type,
        )

    return DirectedNeedSimulationResult(
        batch_code=normalized_batch,
        business_date=daily["business_date"],
        daily_calculation_run_uuid=UUID(str(daily["calculation_run_uuid"])),
        header_count=len(SIMULATION_TYPES),
        line_count=persisted_lines,
        shared_pair_count=shared_pairs,
        reused_seed=reused_seed,
        type_totals=totals,
        target_database=target_settings.pg_database,
        target_environment=target_settings.target_environment,
    )


def simulate_directed_needs_and_publish(
    target_engine: Engine,
    target_settings: OperationalSettings,
    batch_code: str,
    created_by: str,
    lines_per_type: int = 6,
    shared_pairs: int = 2,
    daily_calculation_run_uuid: UUID | None = None,
) -> SimulationPipelineResult:
    simulation = seed_simulated_directed_needs(
        target_engine=target_engine,
        target_settings=target_settings,
        batch_code=batch_code,
        created_by=created_by,
        lines_per_type=lines_per_type,
        shared_pairs=shared_pairs,
        daily_calculation_run_uuid=daily_calculation_run_uuid,
    )
    backlog_run_uuid = simulation_backlog_run_uuid(
        target_settings.target_environment,
        target_settings.pg_database,
        simulation.daily_calculation_run_uuid,
        simulation.batch_code,
    )
    backlog = publish_current_backlog(
        target_engine=target_engine,
        target_settings=target_settings,
        source_daily_run_uuid=simulation.daily_calculation_run_uuid,
        created_by=created_by,
        calculation_run_uuid=backlog_run_uuid,
    )
    return SimulationPipelineResult(simulation=simulation, backlog=backlog)
