from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from ..config import OperationalSettings
from ..db import transactional_connection
from .cursor import CursorPayload
from .errors import ApiError, not_found, version_conflict
from .models import (
    BacklogQuery,
    DirectedNeedCreate,
    DirectedNeedQuery,
    DirectedNeedReplace,
)


READ_TABLES = (
    "pdd_current_backlog_line",
    "pdd_backlog_source_allocation",
    "pdd_calculation_run",
    "pdd_source_snapshot",
    "pdd_branch_stock_position",
    "pdd_directed_need",
    "pdd_directed_need_line",
    "pdd_directed_need_version",
    "pdd_distribution_scope_pair",
    "pdd_item_logistics_snapshot",
    "pdd_need_snapshot",
    "pdd_integration_message",
    "pdd_business_event_log",
)


def _number(value: Any) -> Any:
    return Decimal("0") if value is None else value


def _quantities(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "d": _number(row.get("d_open_quantity", row.get("d"))),
        "e": _number(row.get("e_open_quantity", row.get("e"))),
        "c": _number(row.get("c_open_quantity", row.get("c"))),
        "a": _number(row.get("a_open_quantity", row.get("a"))),
        "s": _number(row.get("s_open_quantity", row.get("s"))),
        "mandatory": _number(row.get("mandatory_open_quantity", row.get("mandatory"))),
        "optional": _number(row.get("optional_open_quantity", row.get("optional"))),
        "total": _number(row.get("total_open_quantity", row.get("total"))),
    }


def _entity(identifier: int | None) -> dict[str, Any] | None:
    if identifier is None:
        return None
    return {"id": int(identifier), "name": None}


def _snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "snapshotVersion": row["snapshot_version"],
        "businessDate": row["business_date"],
        "calculationRunUuid": row["calculation_run_uuid"],
        "publishedAt": row["published_at"],
        "freshnessStatus": row["freshness_status"],
    }


def _backlog_line(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "backlogLineUuid": row["backlog_line_uuid"],
        "rowVersion": row["row_version"],
        "snapshotVersion": row["snapshot_version"],
        "businessDate": row["business_date"],
        "originCd": row["origin_cd"],
        "branch": _entity(row["sucursal"]),
        "article": _entity(row["codigo_articulo"]),
        "supplier": _entity(row.get("c_proveedor_primario")),
        "quantities": _quantities(row),
        "irqScore": row.get("irq_score"),
        "priorityScore": row["priority_score"],
        "oldestNeedDate": row.get("oldest_need_date"),
        "targetDate": row.get("target_date"),
        "activeImportedQuantity": row["active_imported_quantity"],
        "preparedQuantity": row["prepared_quantity"],
        "inTransitQuantity": row["in_transit_quantity"],
        "cdReferenceStock": row.get("cd_reference_stock"),
        "logistics": {
            "packages": row.get("estimated_packages"),
            "pallets": row.get("estimated_pallets"),
            "weightKg": row.get("estimated_weight_kg"),
            "volumeM3": row.get("estimated_volume_m3"),
        },
        "freshnessStatus": row["freshness_status"],
        "alertCodes": list(row.get("alert_codes") or []),
        "publishedAt": row["published_at"],
    }


def _source(row: Mapping[str, Any]) -> dict[str, Any]:
    contributed = _number(row["contributed_quantity"])
    prepared = _number(row["prepared_allocated_quantity"])
    return {
        "sourceType": row["source_type"],
        "sourceId": str(row["source_entity_id"]),
        "sourceBusinessDate": row.get("source_business_date"),
        "contributedQuantity": contributed,
        "preparedAllocatedQuantity": prepared,
        "openQuantity": contributed - prepared,
        "targetDate": row.get("target_date"),
        "attributionOrder": row["attribution_order"],
        "attributionRuleVersion": row["attribution_rule_version"],
    }


def _logistics(original: Decimal, row: Mapping[str, Any]) -> dict[str, Any]:
    units_per_package = row.get("units_per_package")
    packages_per_pallet = row.get("packages_per_pallet")
    packages = original / units_per_package if units_per_package else None
    pallets = packages / packages_per_pallet if packages is not None and packages_per_pallet else None
    weight = original * row["unit_weight_kg"] if row.get("unit_weight_kg") is not None else None
    volume = original * row["unit_volume_m3"] if row.get("unit_volume_m3") is not None else None
    return {"packages": packages, "pallets": pallets, "weightKg": weight, "volumeM3": volume}


def _directed_line(row: Mapping[str, Any]) -> dict[str, Any]:
    original = row["original_quantity"]
    return {
        "directedNeedLineId": str(row["directed_need_line_id"]),
        "branchId": row["sucursal"],
        "articleId": row["codigo_articulo"],
        "originalQuantity": original,
        "targetDate": row.get("target_date"),
        "slaAt": row.get("sla_at"),
        "unitCode": row["unit_code"],
        "preparedAllocatedQuantity": row["prepared_allocated_quantity"],
        "cancelledQuantity": row["cancelled_quantity"],
        "openQuantity": row["open_quantity"],
        "status": row["line_status"],
        "rowVersion": row["line_row_version"],
        "lastActivityAt": row["last_activity_at"],
        "logistics": _logistics(original, row),
    }


def _directed_header(row: Mapping[str, Any], lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "directedNeedUuid": row["directed_need_uuid"],
        "originCd": row["origin_cd"],
        "needType": row["need_type"],
        "businessReference": row["business_reference"],
        "supplierId": row.get("c_proveedor_primario"),
        "validFrom": row["valid_from"],
        "validTo": row.get("valid_to"),
        "priorityScore": row["priority_score"],
        "ownerUser": row["owner_user"],
        "approverUser": row.get("approver_user"),
        "status": row["status"],
        "versionNo": row["version_no"],
        "reason": row["reason"],
        "notes": row.get("notes"),
        "lines": [_directed_line(line) for line in lines],
        "createdAt": row["created_at"],
        "createdBy": row["created_by"],
        "updatedAt": row["updated_at"],
        "updatedBy": row["updated_by"],
        "approvedAt": row.get("approved_at"),
        "closedAt": row.get("closed_at"),
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def _json(value: Any) -> str:
    return json.dumps(value, default=_json_default, sort_keys=True, separators=(",", ":"))


BACKLOG_SELECT = """
    b.backlog_line_id,b.backlog_line_uuid,b.row_version,b.snapshot_version,
    b.business_date,b.calculation_run_id,b.origin_cd,b.sucursal,b.codigo_articulo,
    b.c_proveedor_primario,b.d_open_quantity,b.e_open_quantity,b.c_open_quantity,
    b.a_open_quantity,b.s_open_quantity,b.mandatory_open_quantity,
    b.optional_open_quantity,b.total_open_quantity,b.irq_score,b.priority_score,
    b.oldest_need_date,b.target_date,b.active_imported_quantity,b.prepared_quantity,
    b.in_transit_quantity,b.cd_reference_stock,b.estimated_packages,
    b.estimated_pallets,b.estimated_weight_kg,b.estimated_volume_m3,
    b.freshness_status,b.alert_codes,b.published_at
"""


DIRECTED_HEADER_SELECT = """
    d.directed_need_id,d.directed_need_uuid,d.origin_cd,d.need_type,
    d.business_reference,d.c_proveedor_primario,d.valid_from,d.valid_to,
    d.priority_score,d.owner_user,d.approver_user,d.status,d.version_no,
    d.reason,d.notes,d.created_at,d.created_by,d.updated_at,d.updated_by,
    d.approved_at,d.closed_at
"""


DIRECTED_LINE_SELECT = """
    l.directed_need_line_id,l.directed_need_id,l.sucursal,l.codigo_articulo,
    l.original_quantity,l.prepared_allocated_quantity,l.cancelled_quantity,
    l.open_quantity,l.target_date,l.sla_at,l.unit_code,l.units_per_package,
    l.packages_per_pallet,l.unit_weight_kg,l.unit_volume_m3,
    l.status AS line_status,l.last_activity_at,l.row_version AS line_row_version
"""


SORT_SPECS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "priority_desc": (
        ("b.priority_score", "DESC", "numeric"),
        ("COALESCE(b.irq_score,-1)", "DESC", "numeric"),
        ("COALESCE(b.target_date,DATE '9999-12-31')", "ASC", "date"),
        ("COALESCE(b.oldest_need_date,DATE '9999-12-31')", "ASC", "date"),
        ("b.backlog_line_uuid", "ASC", "uuid"),
    ),
    "irq_desc": (
        ("COALESCE(b.irq_score,-1)", "DESC", "numeric"),
        ("b.priority_score", "DESC", "numeric"),
        ("b.backlog_line_uuid", "ASC", "uuid"),
    ),
    "target_date_asc": (
        ("COALESCE(b.target_date,DATE '9999-12-31')", "ASC", "date"),
        ("b.priority_score", "DESC", "numeric"),
        ("b.backlog_line_uuid", "ASC", "uuid"),
    ),
    "quantity_desc": (
        ("b.total_open_quantity", "DESC", "numeric"),
        ("b.priority_score", "DESC", "numeric"),
        ("b.backlog_line_uuid", "ASC", "uuid"),
    ),
    "article_asc": (
        ("b.codigo_articulo", "ASC", "integer"),
        ("b.sucursal", "ASC", "integer"),
        ("b.backlog_line_uuid", "ASC", "uuid"),
    ),
}


class PddRepository:
    def __init__(self, engine: Engine, settings: OperationalSettings) -> None:
        self.engine = engine
        self.settings = settings

    def ensure_contract(self) -> None:
        with transactional_connection(self.engine, self.settings) as connection:
            missing = connection.execute(
                text(
                    """
                    SELECT array_agg(name ORDER BY name)
                    FROM unnest(CAST(:names AS text[])) required(name)
                    WHERE to_regclass('stock_management.'||name) IS NULL
                    """
                ),
                {"names": list(READ_TABLES)},
            ).scalar_one()
            if missing:
                raise RuntimeError(f"Contrato API PDD incompleto: {missing}")

    def current_snapshot(self, connection: Connection | None = None) -> dict[str, Any] | None:
        if connection is None:
            with transactional_connection(self.engine, self.settings) as owned:
                return self.current_snapshot(owned)
        row = connection.execute(
            text(
                """
                SELECT b.snapshot_version,min(b.business_date) AS business_date,
                       r.calculation_run_uuid,max(b.published_at) AS published_at,
                       CASE
                         WHEN bool_or(b.freshness_status='INCOMPLETE') THEN 'INCOMPLETE'
                         WHEN bool_or(b.freshness_status='STALE') THEN 'STALE'
                         ELSE 'CURRENT'
                       END AS freshness_status,
                       count(*) AS line_count,r.formula_version,r.calculation_run_id
                FROM stock_management.pdd_current_backlog_line b
                JOIN stock_management.pdd_calculation_run r
                  ON r.calculation_run_id=b.calculation_run_id
                WHERE r.run_type='PUBLISH' AND r.scope_id='41:BACKLOG'
                  AND r.status='SUCCEEDED' AND r.is_current
                GROUP BY b.snapshot_version,r.calculation_run_uuid,r.formula_version,
                         r.calculation_run_id,r.finished_at
                ORDER BY r.finished_at DESC NULLS LAST
                LIMIT 1
                """
            )
        ).mappings().first()
        return dict(row) if row else None

    def dashboard(self) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            snapshot = self.current_snapshot(connection)
            if snapshot is None:
                raise ApiError(404, "NO_CURRENT_SNAPSHOT", "No existe una foto vigente")
            totals = connection.execute(
                text(
                    """
                    SELECT count(*) AS line_count,
                           count(DISTINCT codigo_articulo) AS article_count,
                           count(DISTINCT sucursal) AS branch_count,
                           count(DISTINCT c_proveedor_primario) AS supplier_count,
                           sum(d_open_quantity) AS d,sum(e_open_quantity) AS e,
                           sum(c_open_quantity) AS c,sum(a_open_quantity) AS a,
                           sum(s_open_quantity) AS s,
                           sum(mandatory_open_quantity) AS mandatory,
                           sum(optional_open_quantity) AS optional,
                           sum(total_open_quantity) AS total,
                           count(*) FILTER (WHERE irq_score>=90) AS critical_irq_line_count,
                           count(*) FILTER (WHERE freshness_status='CURRENT') AS current_lines,
                           count(*) FILTER (WHERE freshness_status='STALE') AS stale_lines,
                           count(*) FILTER (WHERE freshness_status='INCOMPLETE') AS incomplete_lines
                    FROM stock_management.pdd_current_backlog_line
                    WHERE snapshot_version=:snapshot
                    """
                ),
                {"snapshot": snapshot["snapshot_version"]},
            ).mappings().one()
            alerts = connection.execute(
                text(
                    """
                    SELECT alert_code,count(*) AS line_count
                    FROM stock_management.pdd_current_backlog_line b
                    CROSS JOIN LATERAL unnest(b.alert_codes) alert(alert_code)
                    WHERE b.snapshot_version=:snapshot
                    GROUP BY alert_code ORDER BY line_count DESC,alert_code
                    """
                ),
                {"snapshot": snapshot["snapshot_version"]},
            ).all()
            return {
                "snapshot": _snapshot(snapshot),
                "lineCount": totals["line_count"],
                "articleCount": totals["article_count"],
                "branchCount": totals["branch_count"],
                "supplierCount": totals["supplier_count"],
                "quantities": _quantities(totals),
                "freshnessCounts": {
                    "CURRENT": totals["current_lines"],
                    "STALE": totals["stale_lines"],
                    "INCOMPLETE": totals["incomplete_lines"],
                },
                "criticalIrqLineCount": totals["critical_irq_line_count"],
                "alertCounts": {row.alert_code: row.line_count for row in alerts},
            }

    def list_backlog(
        self,
        query: BacklogQuery,
        cursor: CursorPayload | None,
    ) -> tuple[dict[str, Any], tuple[Any, ...] | None]:
        with transactional_connection(self.engine, self.settings) as connection:
            snapshot = self.current_snapshot(connection)
            if snapshot is None:
                raise ApiError(404, "NO_CURRENT_SNAPSHOT", "No existe una foto vigente")
            snapshot_value = str(snapshot["snapshot_version"])
            if cursor and (cursor.snapshot != snapshot_value or cursor.sort != query.sort):
                raise ApiError(409, "SNAPSHOT_CHANGED", "La foto o el orden del cursor ya no están vigentes")
            where, parameters = self._backlog_filters(query, snapshot["snapshot_version"])
            spec = SORT_SPECS[query.sort]
            cursor_predicate = ""
            if cursor:
                if len(cursor.values) != len(spec):
                    raise ApiError(400, "INVALID_QUERY", "pageCursor no corresponde al orden")
                cursor_predicate = " AND (" + self._keyset_predicate(spec, cursor.values, parameters) + ")"
            select_cursor = ",".join(
                f"{expression} AS _cursor_{index}" for index, (expression, _, _) in enumerate(spec)
            )
            order_by = ",".join(f"{expression} {direction}" for expression, direction, _ in spec)
            rows = connection.execute(
                text(
                    f"""
                    SELECT {BACKLOG_SELECT},{select_cursor}
                    FROM stock_management.pdd_current_backlog_line b
                    WHERE {where}{cursor_predicate}
                    ORDER BY {order_by}
                    LIMIT :limit
                    """
                ),
                {**parameters, "limit": query.page_size + 1},
            ).mappings().all()
            summary = connection.execute(
                text(
                    f"""
                    SELECT count(*) AS total_items,
                           sum(d_open_quantity) AS d,sum(e_open_quantity) AS e,
                           sum(c_open_quantity) AS c,sum(a_open_quantity) AS a,
                           sum(s_open_quantity) AS s,
                           sum(mandatory_open_quantity) AS mandatory,
                           sum(optional_open_quantity) AS optional,
                           sum(total_open_quantity) AS total
                    FROM stock_management.pdd_current_backlog_line b
                    WHERE {where}
                    """
                ),
                parameters,
            ).mappings().one()
            has_next = len(rows) > query.page_size
            page_rows = rows[: query.page_size]
            next_values = None
            if has_next and page_rows:
                last = page_rows[-1]
                next_values = tuple(str(last[f"_cursor_{i}"]) for i in range(len(spec)))
            page = {
                "data": [_backlog_line(row) for row in page_rows],
                "meta": {
                    "pageSize": query.page_size,
                    "hasNextPage": has_next,
                    "nextCursor": None,
                    "totalItems": summary["total_items"],
                    "snapshot": _snapshot(snapshot),
                },
                "totals": _quantities(summary),
            }
            return page, next_values

    @staticmethod
    def _backlog_filters(query: BacklogQuery, snapshot: UUID) -> tuple[str, dict[str, Any]]:
        clauses = ["b.snapshot_version=:snapshot"]
        params: dict[str, Any] = {"snapshot": snapshot}
        array_filters = (
            (query.branch_ids, "b.sucursal", "branch_ids", "integer"),
            (query.article_ids, "b.codigo_articulo", "article_ids", "integer"),
            (query.supplier_ids, "b.c_proveedor_primario", "supplier_ids", "integer"),
            (query.freshness_statuses, "b.freshness_status", "freshness", "text"),
        )
        for values, column, name, pg_type in array_filters:
            if values:
                clauses.append(f"{column}=ANY(CAST(:{name} AS {pg_type}[]))")
                params[name] = list(values)
        if query.need_types:
            need_columns = {
                "D": "b.d_open_quantity",
                "E": "b.e_open_quantity",
                "C": "b.c_open_quantity",
                "A": "b.a_open_quantity",
                "S": "b.s_open_quantity",
            }
            clauses.append("(" + " OR ".join(f"{need_columns[value]}>0" for value in query.need_types) + ")")
        if query.mandatory is not None:
            clauses.append("b.mandatory_open_quantity>0" if query.mandatory else "b.mandatory_open_quantity=0")
        if query.minimum_irq is not None:
            clauses.append("b.irq_score>=:minimum_irq")
            params["minimum_irq"] = query.minimum_irq
        if query.target_date_to is not None:
            clauses.append("b.target_date<=:target_date_to")
            params["target_date_to"] = query.target_date_to
        if query.with_alerts is not None:
            clauses.append("cardinality(b.alert_codes)>0" if query.with_alerts else "cardinality(b.alert_codes)=0")
        if query.search:
            clauses.append(
                "(b.sucursal::text ILIKE :search OR b.codigo_articulo::text ILIKE :search "
                "OR b.c_proveedor_primario::text ILIKE :search)"
            )
            params["search"] = f"%{query.search}%"
        return " AND ".join(clauses), params

    @staticmethod
    def _keyset_predicate(
        spec: Sequence[tuple[str, str, str]],
        values: Sequence[Any],
        parameters: dict[str, Any],
    ) -> str:
        alternatives: list[str] = []
        equalities: list[str] = []
        for index, ((expression, direction, pg_type), value) in enumerate(zip(spec, values)):
            name = f"cursor_{index}"
            casted = f"CAST(:{name} AS {pg_type})"
            operator = ">" if direction == "ASC" else "<"
            alternatives.append("(" + " AND ".join([*equalities, f"{expression}{operator}{casted}"]) + ")")
            equalities.append(f"{expression}={casted}")
            parameters[name] = value
        return " OR ".join(alternatives)

    def get_backlog(self, backlog_uuid: UUID) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            row = connection.execute(
                text(f"SELECT {BACKLOG_SELECT} FROM stock_management.pdd_current_backlog_line b WHERE b.backlog_line_uuid=:uuid"),
                {"uuid": backlog_uuid},
            ).mappings().first()
            if row is None:
                raise not_found("la línea de backlog")
            result = _backlog_line(row)
            result["sources"] = self._sources(connection, row["backlog_line_id"])
            return result

    def _sources(self, connection: Connection, backlog_line_id: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                """
                SELECT a.*,
                       CASE WHEN a.source_type IN ('D','S') THEN n.target_date
                            ELSE l.target_date END AS target_date
                FROM stock_management.pdd_backlog_source_allocation a
                LEFT JOIN stock_management.pdd_need_snapshot n
                  ON a.source_type IN ('D','S')
                 AND n.need_snapshot_id=a.source_entity_id
                 AND n.business_date=a.source_business_date
                LEFT JOIN stock_management.pdd_directed_need_line l
                  ON a.source_type IN ('E','C','A')
                 AND l.directed_need_line_id=a.source_entity_id
                WHERE a.backlog_line_id=:id ORDER BY a.attribution_order
                """
            ),
            {"id": backlog_line_id},
        ).mappings().all()
        return [_source(row) for row in rows]

    def backlog_explanation(self, backlog_uuid: UUID) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            row = connection.execute(
                text(
                    f"""
                    SELECT {BACKLOG_SELECT},r.summary
                    FROM stock_management.pdd_current_backlog_line b
                    JOIN stock_management.pdd_calculation_run r
                      ON r.calculation_run_id=b.calculation_run_id
                    WHERE b.backlog_line_uuid=:uuid
                    """
                ),
                {"uuid": backlog_uuid},
            ).mappings().first()
            if row is None:
                raise not_found("la línea de backlog")
            daily_uuid = (row.get("summary") or {}).get("source_daily_run_uuid")
            position = connection.execute(
                text(
                    """
                    SELECT r.calculation_run_uuid,r.formula_version,
                           cv.configuration_version_uuid,p.*
                    FROM stock_management.pdd_calculation_run r
                    JOIN stock_management.pdd_branch_stock_position p
                      ON p.calculation_run_id=r.calculation_run_id
                     AND p.sucursal=:branch AND p.codigo_articulo=:article
                    LEFT JOIN stock_management.pdd_configuration_version cv
                      ON cv.configuration_version_id=p.configuration_version_id
                    WHERE r.calculation_run_uuid=CAST(:run_uuid AS uuid)
                    """
                ),
                {"branch": row["sucursal"], "article": row["codigo_articulo"], "run_uuid": daily_uuid},
            ).mappings().first()
            if position is None:
                raise ApiError(503, "DATA_UNAVAILABLE", "No está disponible la posición que explica la línea")
            return {
                "backlogLineUuid": backlog_uuid,
                "snapshotVersion": row["snapshot_version"],
                "formulaVersion": position["formula_version"] or "UNKNOWN",
                "calculationRunUuid": position["calculation_run_uuid"],
                "configurationVersionUuid": position.get("configuration_version_uuid"),
                "stock": {
                    "physicalStock": position["physical_stock"],
                    "directPoInbound": position["direct_po_inbound"],
                    "cdInTransit": position["cd_in_transit"],
                    "specialSaleCommitted": position["special_sale_committed"],
                    "confirmedTransferPending": position["confirmed_transfer_pending"],
                    "netStock": position["net_stock"],
                    "coverageDays": position.get("coverage_days"),
                    "pdvbBusinessDate": position["pdvb_business_date"],
                    "pdvbValue": position["pdvb_value"],
                    "leadTimeDays": position["lead_time_days"],
                    "targetStockDays": position["target_stock_days"],
                    "overstockDays": position["overstock_days"],
                    "criticalStock": position["critical_stock"],
                    "minimumStock": position["minimum_stock"],
                    "maximumStock": position["maximum_stock"],
                    "overstockQuantity": position["overstock_quantity"],
                },
                "formula": position.get("explanation") or {},
                "sources": self._sources(connection, row["backlog_line_id"]),
                "alertCodes": sorted(set(row.get("alert_codes") or []).union(position.get("alert_codes") or [])),
            }

    def filter_catalogs(self) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            snapshot = self.current_snapshot(connection)
            if snapshot is None:
                raise ApiError(404, "NO_CURRENT_SNAPSHOT", "No existe una foto vigente")
            rows = connection.execute(
                text(
                    """
                    SELECT array_agg(DISTINCT sucursal ORDER BY sucursal) AS branches,
                           array_agg(DISTINCT codigo_articulo ORDER BY codigo_articulo) AS articles,
                           array_agg(DISTINCT c_proveedor_primario ORDER BY c_proveedor_primario)
                             FILTER (WHERE c_proveedor_primario IS NOT NULL) AS suppliers
                    FROM stock_management.pdd_current_backlog_line
                    WHERE snapshot_version=:snapshot
                    """
                ),
                {"snapshot": snapshot["snapshot_version"]},
            ).mappings().one()
            return {
                "snapshotVersion": snapshot["snapshot_version"],
                "branches": [_entity(value) for value in rows["branches"] or []],
                "articles": [_entity(value) for value in rows["articles"] or []],
                "suppliers": [_entity(value) for value in rows["suppliers"] or []],
            }

    def calculation_run(self, run_uuid: UUID) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            run = connection.execute(
                text("SELECT * FROM stock_management.pdd_calculation_run WHERE calculation_run_uuid=:uuid"),
                {"uuid": run_uuid},
            ).mappings().first()
            if run is None:
                raise not_found("la corrida")
            sources = connection.execute(
                text("SELECT * FROM stock_management.pdd_source_snapshot WHERE calculation_run_id=:id ORDER BY source_code"),
                {"id": run["calculation_run_id"]},
            ).mappings().all()
            return {
                "calculationRunUuid": run["calculation_run_uuid"],
                "runType": run["run_type"],
                "businessDate": run["business_date"],
                "cutoffDate": run["cutoff_date"],
                "formulaVersion": run.get("formula_version"),
                "status": run["status"],
                "current": run["is_current"],
                "startedAt": run.get("started_at"),
                "finishedAt": run.get("finished_at"),
                "createdBy": run["created_by"],
                "inputRowCount": run.get("input_row_count"),
                "outputRowCount": run.get("output_row_count"),
                "warningCount": run["warning_count"],
                "errorCount": run["error_count"],
                "summary": run.get("summary") or {},
                "sourceSnapshots": [
                    {
                        "sourceCode": source["source_code"],
                        "physicalRelation": source["physical_relation"],
                        "required": source["is_required"],
                        "asOfTs": source["as_of_ts"],
                        "rowCount": source.get("row_count") or 0,
                        "checksum": source.get("checksum"),
                        "status": source["status"],
                        "detail": source.get("detail") or {},
                    }
                    for source in sources
                ],
            }

    def list_directed(
        self,
        query: DirectedNeedQuery,
        cursor: CursorPayload | None,
    ) -> tuple[dict[str, Any], tuple[Any, ...] | None]:
        clauses = ["d.origin_cd=41"]
        params: dict[str, Any] = {"limit": query.page_size + 1}
        if query.need_types:
            clauses.append("d.need_type=ANY(CAST(:need_types AS text[]))")
            params["need_types"] = list(query.need_types)
        if query.statuses:
            clauses.append("d.status=ANY(CAST(:statuses AS text[]))")
            params["statuses"] = list(query.statuses)
        if query.valid_on:
            clauses.append("d.valid_from<=:valid_on AND (d.valid_to IS NULL OR d.valid_to>=:valid_on)")
            params["valid_on"] = query.valid_on
        if query.owner_user:
            clauses.append("d.owner_user=:owner")
            params["owner"] = query.owner_user
        if query.search:
            clauses.append("(d.business_reference ILIKE :search OR d.reason ILIKE :search)")
            params["search"] = f"%{query.search}%"
        base_where = " AND ".join(clauses)
        if cursor:
            if cursor.snapshot != "directed-needs" or cursor.sort != "updated_desc" or len(cursor.values) != 2:
                raise ApiError(400, "INVALID_QUERY", "pageCursor no corresponde a necesidades dirigidas")
            clauses.append(
                "(d.updated_at<CAST(:cursor_updated AS timestamptz) OR "
                "(d.updated_at=CAST(:cursor_updated AS timestamptz) "
                "AND d.directed_need_uuid>CAST(:cursor_uuid AS uuid)))"
            )
            params.update(cursor_updated=cursor.values[0], cursor_uuid=cursor.values[1])
        where = " AND ".join(clauses)
        with transactional_connection(self.engine, self.settings) as connection:
            rows = connection.execute(
                text(
                    f"SELECT {DIRECTED_HEADER_SELECT} FROM stock_management.pdd_directed_need d "
                    f"WHERE {where} ORDER BY d.updated_at DESC,d.directed_need_uuid LIMIT :limit"
                ),
                params,
            ).mappings().all()
            total = connection.execute(
                text(f"SELECT count(*) FROM stock_management.pdd_directed_need d WHERE {base_where}"),
                {key: value for key, value in params.items() if not key.startswith("cursor_") and key != "limit"},
            ).scalar_one()
            has_next = len(rows) > query.page_size
            page_rows = rows[: query.page_size]
            line_map = self._directed_lines(connection, [row["directed_need_id"] for row in page_rows])
            data = [_directed_header(row, line_map.get(row["directed_need_id"], [])) for row in page_rows]
            next_values = None
            if has_next and page_rows:
                last = page_rows[-1]
                next_values = (last["updated_at"].isoformat(), str(last["directed_need_uuid"]))
            return {
                "data": data,
                "pageSize": query.page_size,
                "hasNextPage": has_next,
                "nextCursor": None,
                "totalItems": total,
            }, next_values

    def get_directed(self, directed_uuid: UUID, connection: Connection | None = None, for_update: bool = False) -> dict[str, Any]:
        if connection is None:
            with transactional_connection(self.engine, self.settings) as owned:
                return self.get_directed(directed_uuid, owned, for_update)
        suffix = " FOR UPDATE" if for_update else ""
        row = connection.execute(
            text(
                f"SELECT {DIRECTED_HEADER_SELECT} FROM stock_management.pdd_directed_need d "
                f"WHERE d.directed_need_uuid=:uuid{suffix}"
            ),
            {"uuid": directed_uuid},
        ).mappings().first()
        if row is None:
            raise not_found("la necesidad dirigida")
        lines = self._directed_lines(connection, [row["directed_need_id"]], for_update=for_update)
        return _directed_header(row, lines.get(row["directed_need_id"], []))

    @staticmethod
    def _directed_lines(
        connection: Connection,
        directed_ids: Sequence[int],
        for_update: bool = False,
    ) -> dict[int, list[Mapping[str, Any]]]:
        if not directed_ids:
            return {}
        suffix = " FOR UPDATE OF l" if for_update else ""
        rows = connection.execute(
            text(
                f"SELECT {DIRECTED_LINE_SELECT} FROM stock_management.pdd_directed_need_line l "
                f"WHERE l.directed_need_id=ANY(CAST(:ids AS bigint[])) "
                f"ORDER BY l.sucursal,l.codigo_articulo{suffix}"
            ),
            {"ids": list(directed_ids)},
        ).mappings().all()
        grouped: dict[int, list[Mapping[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["directed_need_id"], []).append(row)
        return grouped

    def directed_versions(self, directed_uuid: UUID) -> list[dict[str, Any]]:
        with transactional_connection(self.engine, self.settings) as connection:
            directed = connection.execute(
                text("SELECT directed_need_id FROM stock_management.pdd_directed_need WHERE directed_need_uuid=:uuid"),
                {"uuid": directed_uuid},
            ).first()
            if directed is None:
                raise not_found("la necesidad dirigida")
            rows = connection.execute(
                text(
                    """
                    SELECT version_no,valid_from_ts,changed_by,change_reason,
                           before_state,after_state,correlation_id
                    FROM stock_management.pdd_directed_need_version
                    WHERE directed_need_id=:id ORDER BY version_no DESC
                    """
                ),
                {"id": directed.directed_need_id},
            ).mappings().all()
            return [
                {
                    "versionNo": row["version_no"],
                    "validFromTs": row["valid_from_ts"],
                    "changedBy": row["changed_by"],
                    "changeReason": row["change_reason"],
                    "beforeState": row.get("before_state"),
                    "afterState": row["after_state"],
                    "correlationId": row.get("correlation_id"),
                }
                for row in rows
            ]

    def create_directed(
        self,
        payload: DirectedNeedCreate,
        actor: str,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> tuple[dict[str, Any], bool]:
        normalized = payload.model_dump(by_alias=True, mode="json")
        payload_hash = hashlib.sha256(_json(normalized).encode("utf-8")).hexdigest()
        try:
            with transactional_connection(self.engine, self.settings) as connection:
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                    {"key": f"PDD_DIRECTED_NEED_CREATE:{idempotency_key}"},
                )
                prior = connection.execute(
                    text(
                        """
                        SELECT payload_hash,payload_reference
                        FROM stock_management.pdd_integration_message
                        WHERE interface_code='PDD_API_DIRECTED_NEED'
                          AND direction='INBOUND' AND idempotency_key=:key
                        """
                    ),
                    {"key": idempotency_key},
                ).mappings().first()
                if prior:
                    if prior["payload_hash"] != payload_hash:
                        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "La clave ya fue usada con otro payload")
                    return self.get_directed(UUID(prior["payload_reference"]), connection), True
                self._validate_scope_pairs(connection, payload.lines)
                header = connection.execute(
                    text(
                        """
                        INSERT INTO stock_management.pdd_directed_need (
                            origin_cd,need_type,business_reference,c_proveedor_primario,
                            valid_from,valid_to,priority_score,owner_user,status,version_no,
                            reason,notes,created_by,updated_by
                        ) VALUES (
                            41,:need_type,:reference,:supplier,:valid_from,:valid_to,:priority,
                            :owner,'DRAFT',1,:reason,:notes,:actor,:actor
                        ) RETURNING directed_need_id,directed_need_uuid
                        """
                    ),
                    {
                        "need_type": payload.need_type,
                        "reference": payload.business_reference,
                        "supplier": payload.supplier_id,
                        "valid_from": payload.valid_from,
                        "valid_to": payload.valid_to,
                        "priority": payload.priority_score,
                        "owner": payload.owner_user,
                        "actor": actor,
                        "reason": payload.reason,
                        "notes": payload.notes,
                    },
                ).mappings().one()
                self._insert_directed_lines(connection, header["directed_need_id"], payload.lines)
                result = self.get_directed(header["directed_need_uuid"], connection)
                self._append_version(connection, header["directed_need_id"], 1, actor, "CREATE", None, result, correlation_id)
                self._business_event(connection, result, "DIRECTED_NEED_CREATED", actor, payload.reason, None, correlation_id)
                connection.execute(
                    text(
                        """
                        INSERT INTO stock_management.pdd_integration_message (
                            correlation_id,idempotency_key,interface_code,direction,message_type,
                            status,payload_reference,payload_hash,attempt_count,received_at,processed_at
                        ) VALUES (
                            :correlation,:key,'PDD_API_DIRECTED_NEED','INBOUND',
                            'DIRECTED_NEED_CREATE','PROCESSED',:reference,:hash,1,
                            clock_timestamp(),clock_timestamp()
                        )
                        """
                    ),
                    {"correlation": correlation_id, "key": idempotency_key, "reference": str(header["directed_need_uuid"]), "hash": payload_hash},
                )
                return result, False
        except IntegrityError as exc:
            message = str(exc.orig)
            if "uq_pdd_directed_need_reference" in message:
                raise ApiError(409, "DIRECTED_NEED_DUPLICATE", "Ya existe la referencia de negocio") from exc
            raise

    def replace_directed(
        self,
        directed_uuid: UUID,
        expected_version: int,
        payload: DirectedNeedReplace,
        actor: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        with transactional_connection(self.engine, self.settings) as connection:
            before = self.get_directed(directed_uuid, connection, for_update=True)
            self._assert_version(before, expected_version)
            if before["status"] != "DRAFT":
                raise ApiError(422, "INVALID_STATE_TRANSITION", "Solo una necesidad DRAFT es editable")
            self._validate_scope_pairs(connection, payload.lines)
            directed_id = self._directed_id(connection, directed_uuid)
            version = expected_version + 1
            connection.execute(
                text(
                    """
                    UPDATE stock_management.pdd_directed_need SET
                        need_type=:need_type,business_reference=:reference,
                        c_proveedor_primario=:supplier,valid_from=:valid_from,valid_to=:valid_to,
                        priority_score=:priority,owner_user=:owner,reason=:reason,notes=:notes,
                        version_no=:version,updated_at=clock_timestamp(),updated_by=:actor
                    WHERE directed_need_id=:id
                    """
                ),
                {
                    "need_type": payload.need_type, "reference": payload.business_reference,
                    "supplier": payload.supplier_id, "valid_from": payload.valid_from,
                    "valid_to": payload.valid_to, "priority": payload.priority_score,
                    "owner": payload.owner_user, "actor": actor,
                    "reason": payload.reason, "notes": payload.notes,
                    "version": version, "id": directed_id,
                },
            )
            connection.execute(
                text("DELETE FROM stock_management.pdd_directed_need_line WHERE directed_need_id=:id"),
                {"id": directed_id},
            )
            self._insert_directed_lines(connection, directed_id, payload.lines)
            after = self.get_directed(directed_uuid, connection)
            self._append_version(connection, directed_id, version, actor, payload.change_reason, before, after, correlation_id)
            self._business_event(connection, after, "DIRECTED_NEED_REPLACED", actor, payload.change_reason, before, correlation_id)
            return after

    def transition_directed(
        self,
        directed_uuid: UUID,
        expected_version: int,
        action: str,
        reason: str,
        actor: str,
        correlation_id: UUID,
    ) -> dict[str, Any]:
        transitions = {
            "activate": ({"DRAFT"}, "ACTIVE", "DIRECTED_NEED_ACTIVATED"),
            "cancel": ({"DRAFT", "ACTIVE"}, "CANCELLED", "DIRECTED_NEED_CANCELLED"),
            "close": ({"ACTIVE"}, "CLOSED", "DIRECTED_NEED_CLOSED"),
        }
        allowed, target, event = transitions[action]
        with transactional_connection(self.engine, self.settings) as connection:
            before = self.get_directed(directed_uuid, connection, for_update=True)
            self._assert_version(before, expected_version)
            if before["status"] not in allowed:
                raise ApiError(
                    422,
                    "INVALID_STATE_TRANSITION",
                    f"No se permite {action} desde {before['status']}",
                )
            directed_id = self._directed_id(connection, directed_uuid)
            if action == "activate":
                self._validate_scope_pairs_from_state(connection, before)
            if action in {"cancel", "close"}:
                connection.execute(
                    text(
                        """
                        UPDATE stock_management.pdd_directed_need_line SET
                            cancelled_quantity=original_quantity-prepared_allocated_quantity,
                            status=CASE WHEN prepared_allocated_quantity>=original_quantity
                                        THEN 'FULFILLED' ELSE 'CANCELLED' END,
                            row_version=row_version+1,last_activity_at=clock_timestamp()
                        WHERE directed_need_id=:id AND open_quantity>0
                        """
                    ),
                    {"id": directed_id},
                )
            version = expected_version + 1
            connection.execute(
                text(
                    """
                    UPDATE stock_management.pdd_directed_need SET
                        status=:status,version_no=:version,updated_at=clock_timestamp(),updated_by=:actor,
                        approver_user=CASE WHEN :status='ACTIVE' THEN :actor ELSE approver_user END,
                        approved_at=CASE WHEN :status='ACTIVE' THEN clock_timestamp() ELSE approved_at END,
                        closed_at=CASE WHEN :status IN ('CLOSED','CANCELLED')
                                       THEN clock_timestamp() ELSE closed_at END
                    WHERE directed_need_id=:id
                    """
                ),
                {"status": target, "version": version, "actor": actor, "id": directed_id},
            )
            after = self.get_directed(directed_uuid, connection)
            self._append_version(connection, directed_id, version, actor, reason, before, after, correlation_id)
            self._business_event(connection, after, event, actor, reason, before, correlation_id)
            return after

    @staticmethod
    def _assert_version(current: Mapping[str, Any], expected: int) -> None:
        actual = int(current["versionNo"])
        if actual != expected:
            raise version_conflict(expected, actual)

    @staticmethod
    def _directed_id(connection: Connection, directed_uuid: UUID) -> int:
        return int(
            connection.execute(
                text("SELECT directed_need_id FROM stock_management.pdd_directed_need WHERE directed_need_uuid=:uuid"),
                {"uuid": directed_uuid},
            ).scalar_one()
        )

    def _validate_scope_pairs_from_state(self, connection: Connection, state: Mapping[str, Any]) -> None:
        class Line:
            def __init__(self, row: Mapping[str, Any]) -> None:
                self.branch_id = row["branchId"]
                self.article_id = row["articleId"]
        self._validate_scope_pairs(connection, [Line(line) for line in state["lines"]])

    @staticmethod
    def _validate_scope_pairs(connection: Connection, lines: Iterable[Any]) -> None:
        values = list(lines)
        branches = [line.branch_id for line in values]
        articles = [line.article_id for line in values]
        scope_id = connection.execute(
            text(
                """
                SELECT scope_version_id FROM stock_management.pdd_calculation_run
                WHERE run_type='PUBLISH' AND scope_id='41:BACKLOG'
                  AND status='SUCCEEDED' AND is_current
                ORDER BY finished_at DESC NULLS LAST LIMIT 1
                """
            )
        ).scalar_one_or_none()
        if scope_id is None:
            raise ApiError(503, "DATA_UNAVAILABLE", "No existe un scope operativo vigente")
        missing = connection.execute(
            text(
                """
                WITH input AS (
                    SELECT * FROM unnest(CAST(:branches AS integer[]),CAST(:articles AS integer[]))
                      AS x(sucursal,codigo_articulo)
                )
                SELECT i.sucursal,i.codigo_articulo
                FROM input i
                LEFT JOIN stock_management.pdd_distribution_scope_pair p
                  ON p.scope_version_id=:scope_id
                 AND p.destination_branch=i.sucursal AND p.codigo_articulo=i.codigo_articulo
                WHERE p.codigo_articulo IS NULL
                """
            ),
            {"branches": branches, "articles": articles, "scope_id": scope_id},
        ).mappings().all()
        if missing:
            evidence = ", ".join(f"{row['codigo_articulo']}@{row['sucursal']}" for row in missing[:10])
            raise ApiError(422, "OUT_OF_SCOPE", f"Pares fuera del scope vigente: {evidence}")

    @staticmethod
    def _logistics_by_article(connection: Connection, article_ids: Sequence[int]) -> dict[int, Mapping[str, Any]]:
        rows = connection.execute(
            text(
                """
                SELECT DISTINCT ON (l.codigo_articulo)
                       l.codigo_articulo,l.base_unit,l.units_per_package,
                       l.packages_per_pallet,l.unit_weight_kg,l.unit_volume_m3
                FROM stock_management.pdd_item_logistics_snapshot l
                JOIN stock_management.pdd_calculation_run r
                  ON r.calculation_run_id=l.calculation_run_id
                WHERE l.codigo_articulo=ANY(CAST(:articles AS integer[]))
                  AND r.status='SUCCEEDED'
                ORDER BY l.codigo_articulo,r.is_current DESC,l.created_at DESC
                """
            ),
            {"articles": list(article_ids)},
        ).mappings().all()
        return {row["codigo_articulo"]: row for row in rows}

    def _insert_directed_lines(self, connection: Connection, directed_id: int, lines: Sequence[Any]) -> None:
        logistics = self._logistics_by_article(connection, [line.article_id for line in lines])
        statement = text(
            """
            INSERT INTO stock_management.pdd_directed_need_line (
                directed_need_id,sucursal,codigo_articulo,original_quantity,
                target_date,sla_at,unit_code,units_per_package,packages_per_pallet,
                unit_weight_kg,unit_volume_m3,status
            ) VALUES (
                :directed_id,:branch,:article,:quantity,:target_date,:sla_at,:unit_code,
                :units_per_package,:packages_per_pallet,:unit_weight_kg,:unit_volume_m3,'OPEN'
            )
            """
        )
        params = []
        for line in lines:
            item = logistics.get(line.article_id, {})
            params.append(
                {
                    "directed_id": directed_id, "branch": line.branch_id,
                    "article": line.article_id, "quantity": line.original_quantity,
                    "target_date": line.target_date, "sla_at": line.sla_at,
                    "unit_code": line.unit_code or item.get("base_unit") or "UN",
                    "units_per_package": item.get("units_per_package"),
                    "packages_per_pallet": item.get("packages_per_pallet"),
                    "unit_weight_kg": item.get("unit_weight_kg"),
                    "unit_volume_m3": item.get("unit_volume_m3"),
                }
            )
        connection.execute(statement, params)

    @staticmethod
    def _append_version(
        connection: Connection,
        directed_id: int,
        version: int,
        actor: str,
        reason: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any],
        correlation_id: UUID,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO stock_management.pdd_directed_need_version (
                    directed_need_id,version_no,changed_by,change_reason,
                    before_state,after_state,correlation_id
                ) VALUES (
                    :id,:version,:actor,:reason,CAST(:before AS jsonb),CAST(:after AS jsonb),:correlation
                )
                """
            ),
            {
                "id": directed_id, "version": version, "actor": actor, "reason": reason,
                "before": _json(before) if before is not None else None,
                "after": _json(after), "correlation": correlation_id,
            },
        )

    @staticmethod
    def _business_event(
        connection: Connection,
        after: Mapping[str, Any],
        event_type: str,
        actor: str,
        reason: str,
        before: Mapping[str, Any] | None,
        correlation_id: UUID,
    ) -> None:
        connection.execute(
            text(
                """
                INSERT INTO stock_management.pdd_business_event_log (
                    entity_type,entity_id,event_type,actor_type,actor_id,correlation_id,
                    reason,before_state,after_state,metadata
                ) VALUES (
                    'DIRECTED_NEED',:entity,:event,'USER',:actor,:correlation,:reason,
                    CAST(:before AS jsonb),CAST(:after AS jsonb),
                    jsonb_build_object('api_version','v1')
                )
                """
            ),
            {
                "entity": str(after["directedNeedUuid"]), "event": event_type,
                "actor": actor, "correlation": correlation_id, "reason": reason,
                "before": _json(before) if before is not None else None, "after": _json(after),
            },
        )
