from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from ..config import OperationalSettings
from ..db import transactional_connection


SIX_PLACES = Decimal("0.000001")
NINE_PLACES = Decimal("0.000000001")
BACKLOG_SCOPE_ID = "41:BACKLOG"
ORIGIN_CD = 41
FORMULA_VERSION = "BACKLOG_V1_TEST_PILOT"
ATTRIBUTION_VERSION = "DECAS_ATTRIBUTION_V1"
DECAS_TYPES = ("D", "E", "C", "A", "S")


@dataclass(frozen=True)
class BacklogPublicationResult:
    calculation_run_uuid: UUID
    source_daily_run_uuid: UUID
    snapshot_version: UUID
    business_date: date
    backlog_lines: int
    allocation_rows: int
    directed_source_rows: int
    type_totals: dict[str, Decimal]
    freshness_counts: dict[str, int]
    source_checksum: str
    output_checksum: str
    target_database: str
    reused_publication: bool = False

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "source_daily_run_uuid": str(self.source_daily_run_uuid),
            "snapshot_version": str(self.snapshot_version),
            "business_date": self.business_date.isoformat(),
            "type_totals": {
                key: str(value) for key, value in self.type_totals.items()
            },
        }


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    return Decimal(str(value))


def _q6(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES)


def _q9(value: Decimal) -> Decimal:
    return value.quantize(NINE_PLACES)


def _canonical(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (Decimal, float)):
        normalized = format(Decimal(str(value)).normalize(), "f")
        return "0" if normalized in {"", "-0"} else normalized
    if isinstance(value, (list, tuple, set)):
        return json.dumps(sorted(value), separators=(",", ":"), default=str)
    return str(value)


def _checksum_rows(
    rows: Sequence[Mapping[str, Any]],
    sort_columns: Sequence[str],
    value_columns: Sequence[str],
) -> str:
    digest = hashlib.sha256()
    ordered = sorted(
        rows,
        key=lambda row: tuple(_canonical(row.get(column)) for column in sort_columns),
    )
    for row in ordered:
        payload = "|".join(_canonical(row.get(column)) for column in value_columns)
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def _chunks(rows: Sequence[Mapping[str, Any]], size: int = 2_000):
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _grain(row: Mapping[str, Any]) -> tuple[int, int, int, int | None]:
    provider = row.get("c_proveedor_primario")
    return (
        int(row["origin_cd"]),
        int(row["sucursal"]),
        int(row["codigo_articulo"]),
        int(provider) if provider is not None else None,
    )


def _allocation_sort_key(row: Mapping[str, Any], business_date: date) -> tuple:
    source_type = str(row["source_type"])
    target_date = row.get("target_date")
    if source_type == "E" and target_date is not None and target_date < business_date:
        rank = 1
    else:
        rank = {"E": 2, "C": 3, "D": 4, "A": 5, "S": 6}[source_type]
    return (
        rank,
        target_date is None,
        target_date or date.max,
        row.get("source_business_date") or date.max,
        int(row["source_entity_id"]),
    )


def build_backlog_projection(
    contributions: Sequence[Mapping[str, Any]],
    cd_stock_by_article: Mapping[int, Decimal],
    business_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Consolidate open DECAS sources without assigning or reserving CD stock."""
    grouped: dict[tuple[int, int, int, int | None], dict[str, Any]] = {}
    for raw in contributions:
        source_type = str(raw["source_type"])
        if source_type not in DECAS_TYPES:
            raise ValueError(f"Tipo de necesidad no soportado: {source_type}")
        open_quantity = _decimal(raw.get("open_quantity"), Decimal("0"))
        contributed = _decimal(raw.get("contributed_quantity"), Decimal("0"))
        prepared = _decimal(raw.get("prepared_allocated_quantity"), Decimal("0"))
        assert open_quantity is not None and contributed is not None and prepared is not None
        if open_quantity <= 0:
            continue
        if contributed <= 0 or prepared < 0 or prepared > contributed:
            raise ValueError("Atribucion de fuente DECAS invalida")
        if abs((contributed - prepared) - open_quantity) > SIX_PLACES:
            raise ValueError("El saldo de la fuente no concilia con su contribucion")

        key = _grain(raw)
        group = grouped.setdefault(
            key,
            {
                "origin_cd": key[0],
                "sucursal": key[1],
                "codigo_articulo": key[2],
                "c_proveedor_primario": key[3],
                "quantities": defaultdict(Decimal),
                "irq_scores": [],
                "priority_scores": [],
                "source_dates": [],
                "target_dates": [],
                "alerts": set(),
                "logistics": {},
                "sources": [],
            },
        )
        group["quantities"][source_type] += open_quantity
        if raw.get("irq_score") is not None:
            group["irq_scores"].append(_decimal(raw["irq_score"]))
        if raw.get("priority_score") is not None:
            group["priority_scores"].append(_decimal(raw["priority_score"]))
        if raw.get("source_business_date") is not None:
            group["source_dates"].append(raw["source_business_date"])
        if raw.get("target_date") is not None:
            group["target_dates"].append(raw["target_date"])
        group["alerts"].update(raw.get("alert_codes") or [])
        for field in (
            "units_per_package",
            "packages_per_pallet",
            "unit_weight_kg",
            "unit_volume_m3",
        ):
            value = _decimal(raw.get(field))
            previous = group["logistics"].get(field)
            if previous is None and value is not None:
                group["logistics"][field] = value
            elif previous is not None and value is not None and previous != value:
                group["alerts"].add("LOGISTICS_CONFLICT")
        group["sources"].append(
            {
                "source_type": source_type,
                "source_entity_id": int(raw["source_entity_id"]),
                "source_business_date": raw.get("source_business_date"),
                "contributed_quantity": _q6(contributed),
                "prepared_allocated_quantity": _q6(prepared),
                "target_date": raw.get("target_date"),
            }
        )

    backlog_rows: list[dict[str, Any]] = []
    allocations: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: (item[0], item[1], item[2], item[3] or -1)):
        group = grouped[key]
        quantities = {
            source_type: _q6(group["quantities"].get(source_type, Decimal("0")))
            for source_type in DECAS_TYPES
        }
        total = sum(quantities.values(), Decimal("0"))
        if total <= 0:
            continue
        logistics = group["logistics"]
        units_per_package = logistics.get("units_per_package")
        packages_per_pallet = logistics.get("packages_per_pallet")
        unit_weight = logistics.get("unit_weight_kg")
        unit_volume = logistics.get("unit_volume_m3")
        alerts = set(group["alerts"])
        incomplete = False
        if units_per_package is None or units_per_package <= 0:
            alerts.add("UNITS_PER_PACKAGE_MISSING")
            incomplete = True
        if packages_per_pallet is None or packages_per_pallet <= 0:
            alerts.add("PACKAGES_PER_PALLET_MISSING")
            incomplete = True
        cd_reference_stock = cd_stock_by_article.get(key[2])
        if cd_reference_stock is None:
            alerts.add("CD_REFERENCE_STOCK_MISSING")
            incomplete = True
        estimated_packages = (
            _q6(total / units_per_package) if units_per_package else None
        )
        estimated_pallets = (
            _q6(estimated_packages / packages_per_pallet)
            if estimated_packages is not None and packages_per_pallet
            else None
        )
        row = {
            "origin_cd": key[0],
            "sucursal": key[1],
            "codigo_articulo": key[2],
            "c_proveedor_primario": key[3],
            "d_open_quantity": quantities["D"],
            "e_open_quantity": quantities["E"],
            "c_open_quantity": quantities["C"],
            "a_open_quantity": quantities["A"],
            "s_open_quantity": quantities["S"],
            "irq_score": max(group["irq_scores"]) if group["irq_scores"] else None,
            "priority_score": _q6(
                max(group["priority_scores"])
                if group["priority_scores"]
                else Decimal("0")
            ),
            "oldest_need_date": min(group["source_dates"]) if group["source_dates"] else None,
            "target_date": min(group["target_dates"]) if group["target_dates"] else None,
            "active_imported_quantity": Decimal("0.000000"),
            "prepared_quantity": Decimal("0.000000"),
            "in_transit_quantity": Decimal("0.000000"),
            "cd_reference_stock": _q6(cd_reference_stock) if cd_reference_stock is not None else None,
            "estimated_packages": estimated_packages,
            "estimated_pallets": estimated_pallets,
            "estimated_weight_kg": _q6(total * unit_weight) if unit_weight is not None else None,
            "estimated_volume_m3": _q9(total * unit_volume) if unit_volume is not None else None,
            "freshness_status": "INCOMPLETE" if incomplete else "CURRENT",
            "alert_codes": sorted(alerts),
        }
        row["input_checksum"] = _checksum_rows(
            [row],
            ("origin_cd", "sucursal", "codigo_articulo", "c_proveedor_primario"),
            (
                "origin_cd", "sucursal", "codigo_articulo", "c_proveedor_primario",
                "d_open_quantity", "e_open_quantity", "c_open_quantity",
                "a_open_quantity", "s_open_quantity", "irq_score", "priority_score",
                "oldest_need_date", "target_date", "cd_reference_stock",
                "estimated_packages", "estimated_pallets", "estimated_weight_kg",
                "estimated_volume_m3", "freshness_status", "alert_codes",
            ),
        )
        backlog_rows.append(row)
        ordered_sources = sorted(
            group["sources"], key=lambda source: _allocation_sort_key(source, business_date)
        )
        for order, source in enumerate(ordered_sources, start=1):
            allocations.append(
                {
                    **source,
                    "grain": key,
                    "attribution_order": order,
                    "attribution_rule_version": ATTRIBUTION_VERSION,
                }
            )
    return backlog_rows, allocations


def _read_contributions(connection, daily_run_id: int, business_date: date):
    orphaned = connection.execute(
        text(
            """
            SELECT count(*)
            FROM stock_management.pdd_directed_need d
            JOIN stock_management.pdd_directed_need_line l
              ON l.directed_need_id=d.directed_need_id
            LEFT JOIN stock_management.pdd_branch_stock_position b
              ON b.calculation_run_id=:daily_run_id
             AND b.sucursal=l.sucursal AND b.codigo_articulo=l.codigo_articulo
            WHERE d.status='ACTIVE' AND d.valid_from<=:business_date
              AND (d.valid_to IS NULL OR d.valid_to>=:business_date)
              AND l.open_quantity>0 AND b.branch_stock_position_id IS NULL
            """
        ),
        {"daily_run_id": daily_run_id, "business_date": business_date},
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"Hay {orphaned} lineas E/C/A activas fuera del scope DAILY_DECAS"
        )

    rows = connection.execute(
        text(
            """
            WITH pair_context AS (
                SELECT
                    n.sucursal,n.codigo_articulo,n.c_proveedor_primario,
                    n.irq_score,n.logistics_snapshot_id,
                    l.units_per_package,l.packages_per_pallet,
                    l.unit_weight_kg,l.unit_volume_m3
                FROM stock_management.pdd_need_snapshot n
                LEFT JOIN stock_management.pdd_item_logistics_snapshot l
                  ON l.item_logistics_snapshot_id=n.logistics_snapshot_id
                WHERE n.calculation_run_id=:daily_run_id AND n.need_type='D'
            ),
            automatic_sources AS (
                SELECT
                    n.origin_cd,n.sucursal,n.codigo_articulo,n.c_proveedor_primario,
                    n.need_type::text AS source_type,
                    n.need_snapshot_id AS source_entity_id,
                    n.business_date AS source_business_date,
                    n.open_quantity AS contributed_quantity,
                    0::numeric AS prepared_allocated_quantity,
                    n.open_quantity,n.irq_score,n.priority_score,n.target_date,
                    l.units_per_package,l.packages_per_pallet,
                    l.unit_weight_kg,l.unit_volume_m3,n.alert_codes
                FROM stock_management.pdd_need_snapshot n
                LEFT JOIN stock_management.pdd_item_logistics_snapshot l
                  ON l.item_logistics_snapshot_id=n.logistics_snapshot_id
                WHERE n.calculation_run_id=:daily_run_id
                  AND n.calculation_status='CALCULATED' AND n.open_quantity>0
            ),
            directed_sources AS (
                SELECT
                    d.origin_cd,l.sucursal,l.codigo_articulo,
                    coalesce(d.c_proveedor_primario,c.c_proveedor_primario)
                        AS c_proveedor_primario,
                    d.need_type::text AS source_type,
                    l.directed_need_line_id AS source_entity_id,
                    d.valid_from AS source_business_date,
                    (l.original_quantity-l.cancelled_quantity) AS contributed_quantity,
                    l.prepared_allocated_quantity,
                    l.open_quantity,c.irq_score,d.priority_score,l.target_date,
                    c.units_per_package,c.packages_per_pallet,
                    c.unit_weight_kg,c.unit_volume_m3,ARRAY[]::text[] AS alert_codes
                FROM stock_management.pdd_directed_need d
                JOIN stock_management.pdd_directed_need_line l
                  ON l.directed_need_id=d.directed_need_id
                JOIN pair_context c
                  ON c.sucursal=l.sucursal AND c.codigo_articulo=l.codigo_articulo
                WHERE d.status='ACTIVE' AND d.valid_from<=:business_date
                  AND (d.valid_to IS NULL OR d.valid_to>=:business_date)
                  AND l.open_quantity>0
            )
            SELECT * FROM automatic_sources
            UNION ALL
            SELECT * FROM directed_sources
            ORDER BY sucursal,codigo_articulo,source_type,source_entity_id
            """
        ),
        {"daily_run_id": daily_run_id, "business_date": business_date},
    ).mappings().all()
    return [dict(row) for row in rows]


def publish_current_backlog(
    target_engine: Engine,
    target_settings: OperationalSettings,
    source_daily_run_uuid: UUID,
    created_by: str,
    calculation_run_uuid: UUID | None = None,
) -> BacklogPublicationResult:
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")
    run_uuid = calculation_run_uuid or uuid4()
    snapshot_version = uuid4()

    with transactional_connection(target_engine, target_settings) as target:
        target.execute(text("SELECT pg_advisory_xact_lock(hashtext('pdd.publish.backlog'))"))
        missing = target.execute(
            text(
                """
                SELECT array_agg(name ORDER BY name)
                FROM unnest(ARRAY[
                    'stock_management.pdd_calculation_run',
                    'stock_management.pdd_source_snapshot',
                    'stock_management.pdd_need_snapshot',
                    'stock_management.pdd_branch_stock_position',
                    'stock_management.pdd_cd_stock_position',
                    'stock_management.pdd_item_logistics_snapshot',
                    'stock_management.pdd_directed_need',
                    'stock_management.pdd_directed_need_line',
                    'stock_management.pdd_current_backlog_line',
                    'stock_management.pdd_backlog_source_allocation',
                    'stock_management.pdd_valkimia_import'
                ]) required(name)
                WHERE to_regclass(name) IS NULL
                """
            )
        ).scalar_one()
        if missing:
            raise RuntimeError(f"Contrato operativo incompleto: {missing}")

        daily = target.execute(
            text(
                """
                SELECT r.calculation_run_id,r.business_date,r.status,r.is_current,
                       r.scope_version_id,r.configuration_version_id,r.output_checksum,
                       s.origin_cd
                FROM stock_management.pdd_calculation_run r
                JOIN stock_management.pdd_distribution_scope_version s
                  ON s.scope_version_id=r.scope_version_id
                WHERE r.calculation_run_uuid=CAST(:uuid AS uuid)
                  AND r.run_type='DAILY_DECAS'
                """
            ),
            {"uuid": source_daily_run_uuid},
        ).mappings().one_or_none()
        if daily is None or daily["status"] != "SUCCEEDED" or not daily["is_current"]:
            raise RuntimeError("La corrida DAILY_DECAS fuente no es vigente y exitosa")
        business_date = daily["business_date"]
        origin_cd = daily["origin_cd"]
        if origin_cd != ORIGIN_CD:
            raise RuntimeError("El origen de DAILY_DECAS no coincide con el CD configurado")

        active_imports = target.execute(
            text(
                """
                SELECT count(*) FROM stock_management.pdd_valkimia_import
                WHERE origin_cd=:origin_cd
                  AND status IN ('PENDING','ACCEPTED','PARTIAL')
                """
            ),
            {"origin_cd": origin_cd},
        ).scalar_one()
        if active_imports:
            raise RuntimeError(
                "Hay importaciones Valkimia activas; falta habilitar su conciliacion en backlog"
            )

        contributions = _read_contributions(
            target, daily["calculation_run_id"], business_date
        )
        cd_stock_by_article = {
            int(row["codigo_articulo"]): _decimal(row["physical_stock"], Decimal("0"))
            for row in target.execute(
                text(
                    """
                    SELECT codigo_articulo,physical_stock
                    FROM stock_management.pdd_cd_stock_position
                    WHERE calculation_run_id=:daily_run_id
                    """
                ),
                {"daily_run_id": daily["calculation_run_id"]},
            ).mappings()
        }
        backlog_rows, allocations = build_backlog_projection(
            contributions, cd_stock_by_article, business_date
        )
        source_checksum = _checksum_rows(
            contributions,
            ("source_type", "source_entity_id", "source_business_date"),
            (
                "origin_cd", "sucursal", "codigo_articulo", "c_proveedor_primario",
                "source_type", "source_entity_id", "source_business_date",
                "contributed_quantity", "prepared_allocated_quantity", "open_quantity",
                "irq_score", "priority_score", "target_date", "units_per_package",
                "packages_per_pallet", "unit_weight_kg", "unit_volume_m3", "alert_codes",
            ),
        )
        output_checksum = _checksum_rows(
            backlog_rows,
            ("origin_cd", "sucursal", "codigo_articulo", "c_proveedor_primario"),
            (
                "origin_cd", "sucursal", "codigo_articulo", "c_proveedor_primario",
                "d_open_quantity", "e_open_quantity", "c_open_quantity",
                "a_open_quantity", "s_open_quantity", "irq_score", "priority_score",
                "oldest_need_date", "target_date", "cd_reference_stock",
                "estimated_packages", "estimated_pallets", "estimated_weight_kg",
                "estimated_volume_m3", "freshness_status", "alert_codes", "input_checksum",
            ),
        )
        type_totals = {
            source_type: _q6(
                sum(
                    (_decimal(row[f"{source_type.lower()}_open_quantity"], Decimal("0")) for row in backlog_rows),
                    Decimal("0"),
                )
            )
            for source_type in DECAS_TYPES
        }
        freshness_counts = {
            status: sum(1 for row in backlog_rows if row["freshness_status"] == status)
            for status in ("CURRENT", "STALE", "INCOMPLETE")
        }
        directed_source_rows = sum(
            1 for row in contributions if row["source_type"] in {"E", "C", "A"}
        )

        existing_run = target.execute(
            text(
                """
                SELECT calculation_run_id,business_date,status,is_current,input_checksum,
                       output_checksum,output_row_count,summary
                FROM stock_management.pdd_calculation_run
                WHERE calculation_run_uuid=CAST(:uuid AS uuid)
                """
            ),
            {"uuid": run_uuid},
        ).mappings().one_or_none()
        if existing_run is not None:
            summary = existing_run["summary"]
            if (
                existing_run["status"] != "SUCCEEDED"
                or not existing_run["is_current"]
                or existing_run["business_date"] != business_date
                or existing_run["input_checksum"] != source_checksum
                or existing_run["output_checksum"] != output_checksum
                or summary.get("source_daily_run_uuid") != str(source_daily_run_uuid)
            ):
                raise RuntimeError("Existe una publicacion de backlog no reutilizable")
            persisted = target.execute(
                text(
                    """
                    SELECT count(*) FROM stock_management.pdd_current_backlog_line
                    WHERE calculation_run_id=:run_id
                    """
                ),
                {"run_id": existing_run["calculation_run_id"]},
            ).scalar_one()
            if persisted != len(backlog_rows):
                raise RuntimeError("La publicacion idempotente ya no es la foto vigente")
            allocation_count = target.execute(
                text(
                    """
                    SELECT count(*)
                    FROM stock_management.pdd_backlog_source_allocation a
                    JOIN stock_management.pdd_current_backlog_line b
                      ON b.backlog_line_id=a.backlog_line_id
                    WHERE b.calculation_run_id=:run_id
                    """
                ),
                {"run_id": existing_run["calculation_run_id"]},
            ).scalar_one()
            return BacklogPublicationResult(
                calculation_run_uuid=run_uuid,
                source_daily_run_uuid=source_daily_run_uuid,
                snapshot_version=UUID(summary["snapshot_version"]),
                business_date=business_date,
                backlog_lines=persisted,
                allocation_rows=allocation_count,
                directed_source_rows=directed_source_rows,
                type_totals=type_totals,
                freshness_counts=freshness_counts,
                source_checksum=source_checksum,
                output_checksum=output_checksum,
                target_database=target_settings.pg_database,
                reused_publication=True,
            )

        attempt_no = target.execute(
            text(
                """
                SELECT coalesce(max(attempt_no),0)+1
                FROM stock_management.pdd_calculation_run
                WHERE run_type='PUBLISH' AND business_date=:business_date
                  AND scope_type='CD' AND scope_id=:scope_id
                """
            ),
            {"business_date": business_date, "scope_id": BACKLOG_SCOPE_ID},
        ).scalar_one()
        summary = {
            "entity": "pdd_current_backlog_line",
            "source_daily_run_uuid": str(source_daily_run_uuid),
            "snapshot_version": str(snapshot_version),
            "backlog_lines": len(backlog_rows),
            "allocation_rows": len(allocations),
            "directed_source_rows": directed_source_rows,
            "type_totals": type_totals,
            "freshness_counts": freshness_counts,
            "attribution_rule_version": ATTRIBUTION_VERSION,
            "pipeline_status": "NO_ACTIVE_VALKIMIA_IMPORTS",
        }
        calculation_run_id = target.execute(
            text(
                """
                INSERT INTO stock_management.pdd_calculation_run (
                    calculation_run_uuid,run_type,business_date,cutoff_date,
                    scope_type,scope_id,attempt_no,scope_version_id,
                    configuration_version_id,formula_version,status,started_at,
                    created_by,input_row_count,output_row_count,warning_count,
                    error_count,input_checksum,output_checksum,summary
                ) VALUES (
                    CAST(:uuid AS uuid),'PUBLISH',:business_date,:cutoff_date,
                    'CD',:scope_id,:attempt_no,:scope_version_id,
                    :configuration_version_id,:formula_version,'RUNNING',clock_timestamp(),
                    :created_by,:input_rows,:output_rows,:warning_count,
                    0,:input_checksum,:output_checksum,CAST(:summary AS jsonb)
                ) RETURNING calculation_run_id
                """
            ),
            {
                "uuid": run_uuid,
                "business_date": business_date,
                "cutoff_date": business_date - timedelta(days=1),
                "scope_id": BACKLOG_SCOPE_ID,
                "attempt_no": attempt_no,
                "scope_version_id": daily["scope_version_id"],
                "configuration_version_id": daily["configuration_version_id"],
                "formula_version": FORMULA_VERSION,
                "created_by": created_by.strip(),
                "input_rows": len(contributions),
                "output_rows": len(backlog_rows),
                "warning_count": len(backlog_rows) - freshness_counts["CURRENT"],
                "input_checksum": source_checksum,
                "output_checksum": output_checksum,
                "summary": _json(summary),
            },
        ).scalar_one()
        target.execute(
            text(
                """
                INSERT INTO stock_management.pdd_source_snapshot (
                    calculation_run_id,source_code,source_database,physical_relation,
                    is_required,min_business_date,max_business_date,as_of_ts,
                    row_count,checksum,status,detail
                ) VALUES (
                    :run_id,'DECAS_OPEN_SOURCES',:database,
                    'stock_management.pdd_need_snapshot + pdd_directed_need_line',
                    true,:business_date,:business_date,clock_timestamp(),
                    :row_count,:checksum,'VALID',CAST(:detail AS jsonb)
                )
                """
            ),
            {
                "run_id": calculation_run_id,
                "database": target_settings.pg_database,
                "business_date": business_date,
                "row_count": len(contributions),
                "checksum": source_checksum,
                "detail": _json(
                    {
                        "source_daily_run_uuid": str(source_daily_run_uuid),
                        "directed_source_rows": directed_source_rows,
                    }
                ),
            },
        )

        existing_rows = {
            _grain(row): dict(row)
            for row in target.execute(
                text(
                    """
                    SELECT backlog_line_id,backlog_line_uuid,row_version,
                           origin_cd,sucursal,codigo_articulo,c_proveedor_primario
                    FROM stock_management.pdd_current_backlog_line
                    """
                )
            ).mappings()
        }
        new_keys = {_grain(row) for row in backlog_rows}
        obsolete_ids = [
            row["backlog_line_id"]
            for key, row in existing_rows.items()
            if key not in new_keys
        ]
        if obsolete_ids:
            target.execute(
                text(
                    """
                    DELETE FROM stock_management.pdd_current_backlog_line
                    WHERE backlog_line_id=ANY(CAST(:ids AS bigint[]))
                    """
                ),
                {"ids": obsolete_ids},
            )

        update_sql = text(
            """
            UPDATE stock_management.pdd_current_backlog_line SET
                snapshot_version=CAST(:snapshot_version AS uuid),
                business_date=:business_date,calculation_run_id=:calculation_run_id,
                d_open_quantity=:d_open_quantity,e_open_quantity=:e_open_quantity,
                c_open_quantity=:c_open_quantity,a_open_quantity=:a_open_quantity,
                s_open_quantity=:s_open_quantity,irq_score=:irq_score,
                priority_score=:priority_score,oldest_need_date=:oldest_need_date,
                target_date=:target_date,active_imported_quantity=:active_imported_quantity,
                prepared_quantity=:prepared_quantity,in_transit_quantity=:in_transit_quantity,
                cd_reference_stock=:cd_reference_stock,estimated_packages=:estimated_packages,
                estimated_pallets=:estimated_pallets,estimated_weight_kg=:estimated_weight_kg,
                estimated_volume_m3=:estimated_volume_m3,
                freshness_status=:freshness_status,alert_codes=:alert_codes,
                row_version=row_version+1,input_checksum=:input_checksum,
                published_at=clock_timestamp()
            WHERE backlog_line_id=:backlog_line_id
            """
        )
        insert_sql = text(
            """
            INSERT INTO stock_management.pdd_current_backlog_line (
                snapshot_version,business_date,calculation_run_id,origin_cd,sucursal,
                codigo_articulo,c_proveedor_primario,d_open_quantity,e_open_quantity,
                c_open_quantity,a_open_quantity,s_open_quantity,irq_score,priority_score,
                oldest_need_date,target_date,active_imported_quantity,prepared_quantity,
                in_transit_quantity,cd_reference_stock,estimated_packages,estimated_pallets,
                estimated_weight_kg,estimated_volume_m3,freshness_status,alert_codes,
                input_checksum
            ) VALUES (
                CAST(:snapshot_version AS uuid),:business_date,:calculation_run_id,
                :origin_cd,:sucursal,:codigo_articulo,:c_proveedor_primario,
                :d_open_quantity,:e_open_quantity,:c_open_quantity,:a_open_quantity,
                :s_open_quantity,:irq_score,:priority_score,:oldest_need_date,:target_date,
                :active_imported_quantity,:prepared_quantity,:in_transit_quantity,
                :cd_reference_stock,:estimated_packages,:estimated_pallets,
                :estimated_weight_kg,:estimated_volume_m3,:freshness_status,:alert_codes,
                :input_checksum
            )
            """
        )
        update_rows = []
        insert_rows = []
        for row in backlog_rows:
            params = {
                **row,
                "snapshot_version": snapshot_version,
                "business_date": business_date,
                "calculation_run_id": calculation_run_id,
            }
            existing = existing_rows.get(_grain(row))
            if existing is None:
                insert_rows.append(params)
            else:
                update_rows.append(
                    {**params, "backlog_line_id": existing["backlog_line_id"]}
                )
        for chunk in _chunks(update_rows):
            target.execute(update_sql, list(chunk))
        for chunk in _chunks(insert_rows):
            target.execute(insert_sql, list(chunk))

        persisted_map = {
            _grain(row): row["backlog_line_id"]
            for row in target.execute(
                text(
                    """
                    SELECT backlog_line_id,origin_cd,sucursal,codigo_articulo,
                           c_proveedor_primario
                    FROM stock_management.pdd_current_backlog_line
                    WHERE snapshot_version=CAST(:snapshot_version AS uuid)
                    """
                ),
                {"snapshot_version": snapshot_version},
            ).mappings()
        }
        if len(persisted_map) != len(backlog_rows):
            raise RuntimeError("La foto de backlog no cubre todas las lineas calculadas")
        backlog_ids = list(persisted_map.values())
        if backlog_ids:
            target.execute(
                text(
                    """
                    DELETE FROM stock_management.pdd_backlog_source_allocation
                    WHERE backlog_line_id=ANY(CAST(:ids AS bigint[]))
                    """
                ),
                {"ids": backlog_ids},
            )
        allocation_insert = text(
            """
            INSERT INTO stock_management.pdd_backlog_source_allocation (
                backlog_line_id,source_type,source_entity_id,source_business_date,
                contributed_quantity,prepared_allocated_quantity,attribution_order,
                attribution_rule_version
            ) VALUES (
                :backlog_line_id,:source_type,:source_entity_id,:source_business_date,
                :contributed_quantity,:prepared_allocated_quantity,:attribution_order,
                :attribution_rule_version
            )
            """
        )
        allocation_params = [
            {**row, "backlog_line_id": persisted_map[row["grain"]]}
            for row in allocations
        ]
        for chunk in _chunks(allocation_params):
            target.execute(allocation_insert, list(chunk))

        persisted = target.execute(
            text(
                """
                SELECT count(*) AS lines,
                       coalesce(sum(d_open_quantity),0) AS d_total,
                       coalesce(sum(e_open_quantity),0) AS e_total,
                       coalesce(sum(c_open_quantity),0) AS c_total,
                       coalesce(sum(a_open_quantity),0) AS a_total,
                       coalesce(sum(s_open_quantity),0) AS s_total
                FROM stock_management.pdd_current_backlog_line
                WHERE snapshot_version=CAST(:snapshot_version AS uuid)
                """
            ),
            {"snapshot_version": snapshot_version},
        ).mappings().one()
        allocation_count = target.execute(
            text(
                """
                SELECT count(*)
                FROM stock_management.pdd_backlog_source_allocation
                WHERE backlog_line_id=ANY(CAST(:ids AS bigint[]))
                """
            ),
            {"ids": backlog_ids},
        ).scalar_one() if backlog_ids else 0
        persisted_totals = {
            source_type: _q6(_decimal(persisted[f"{source_type.lower()}_total"], Decimal("0")))
            for source_type in DECAS_TYPES
        }
        if (
            persisted["lines"] != len(backlog_rows)
            or allocation_count != len(allocations)
            or persisted_totals != type_totals
        ):
            raise RuntimeError("La publicacion del backlog no concilia con sus fuentes")

        target.execute(
            text(
                """
                UPDATE stock_management.pdd_calculation_run SET is_current=false
                WHERE run_type='PUBLISH' AND scope_type='CD' AND scope_id=:scope_id
                  AND calculation_run_id<>:run_id
                """
            ),
            {"scope_id": BACKLOG_SCOPE_ID, "run_id": calculation_run_id},
        )
        target.execute(
            text(
                """
                UPDATE stock_management.pdd_calculation_run
                SET status='SUCCEEDED',is_current=true,finished_at=clock_timestamp()
                WHERE calculation_run_id=:run_id
                """
            ),
            {"run_id": calculation_run_id},
        )

    return BacklogPublicationResult(
        calculation_run_uuid=run_uuid,
        source_daily_run_uuid=source_daily_run_uuid,
        snapshot_version=snapshot_version,
        business_date=business_date,
        backlog_lines=len(backlog_rows),
        allocation_rows=len(allocations),
        directed_source_rows=directed_source_rows,
        type_totals=type_totals,
        freshness_counts=freshness_counts,
        source_checksum=source_checksum,
        output_checksum=output_checksum,
        target_database=target_settings.pg_database,
        reused_publication=False,
    )
