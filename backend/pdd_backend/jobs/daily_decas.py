from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from ..config import OperationalSettings, Settings
from ..db import transactional_connection
from ..operational_registry import (
    OperationalConfiguration,
    load_operational_configuration,
)


SIX_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class DailyDecasResult:
    calculation_run_uuid: UUID
    business_date: date
    scope_version_uuid: UUID
    pdvb_calculation_run_uuid: UUID
    configuration_version_uuid: UUID
    branch_positions: int
    excluded_blocked_pdvb: int
    need_rows: int
    cd_positions: int
    branch_status_counts: dict[str, int]
    need_status_counts: dict[str, int]
    source_checksum: str
    target_database: str
    reused_run: bool = False

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "business_date": self.business_date.isoformat(),
            "scope_version_uuid": str(self.scope_version_uuid),
            "pdvb_calculation_run_uuid": str(self.pdvb_calculation_run_uuid),
            "configuration_version_uuid": str(self.configuration_version_uuid),
        }


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    return Decimal(str(value))


def _nonnegative(value: Any) -> Decimal:
    number = _decimal(value, Decimal("0"))
    assert number is not None
    return max(number, Decimal("0"))


def _q6(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES)


def _canonical(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (Decimal, float)):
        number = Decimal(str(value))
        normalized = format(number.normalize(), "f")
        return "0" if normalized in {"", "-0"} else normalized
    if isinstance(value, (list, tuple)):
        return json.dumps(list(value), separators=(",", ":"), sort_keys=True)
    if isinstance(value, dict):
        return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)
    return str(value)


def _row_checksum(row: Mapping[str, Any], columns: Sequence[str]) -> str:
    payload = "|".join(_canonical(row.get(column)) for column in columns)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rows_checksum(rows: Sequence[Mapping[str, Any]], key_columns: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: tuple(item[column] for column in key_columns)):
        digest.update(str(row["input_checksum"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _chunks(rows: Sequence[Mapping[str, Any]], size: int = 2_000):
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def calculation_cutoff_date(business_date: date) -> date:
    """Return the last closed input date for a DAILY_DECAS business date."""
    return business_date - timedelta(days=1)


def calculate_irq(
    net_stock: Decimal,
    coverage_days: Decimal | None,
    lead_time_days: Decimal,
    target_stock_days: Decimal,
) -> Decimal:
    if net_stock <= 0:
        return Decimal("100")
    if coverage_days is None:
        return Decimal("0")
    if coverage_days < lead_time_days:
        return Decimal("90")
    if coverage_days < lead_time_days * 2:
        return Decimal("50")
    if coverage_days < target_stock_days:
        return Decimal("25")
    return Decimal("0")


def round_to_logistics(quantity: Decimal, rounding_unit: Decimal) -> Decimal:
    if quantity <= 0:
        return Decimal("0.000000")
    packages = (quantity / rounding_unit).to_integral_value(rounding=ROUND_CEILING)
    return _q6(packages * rounding_unit)


def build_branch_position(
    source: Mapping[str, Any],
    estimate: Mapping[str, Any],
    fallback_lead_time: Decimal,
) -> dict[str, Any]:
    pdvb = _decimal(estimate["pdvb_value"])
    if pdvb is None or pdvb < 0:
        raise RuntimeError("PDVB publicable nulo o negativo")
    target_days = _decimal(source.get("q_dias_stock"))
    overstock_days = _decimal(source.get("q_dias_sobre_stock"))
    if target_days is None or target_days < 0:
        raise RuntimeError("q_dias_stock faltante o negativo")
    if overstock_days is None or overstock_days < 0:
        raise RuntimeError("q_dias_sobre_stock faltante o negativo")

    source_lead = _decimal(source.get("dias_preparacion"))
    used_fallback = source_lead is None or source_lead <= 0
    lead_time = fallback_lead_time if used_fallback else source_lead
    assert lead_time is not None

    physical = _decimal(source.get("stock"))
    if physical is None:
        raise RuntimeError("Stock fisico nulo")
    direct_po = _nonnegative(source.get("pedido_pendiente"))
    transit = _nonnegative(source.get("transito_pendiente"))
    transfer_observed = _decimal(source.get("transfer_pendiente"), Decimal("0"))
    assert transfer_observed is not None
    net_stock = physical + direct_po + transit
    coverage = _q6(net_stock / pdvb) if pdvb > 0 else None

    alerts: list[str] = []
    if estimate["status"] == "WARN":
        alerts.append("PDVB_WARN")
    if used_fallback:
        alerts.append("LEAD_TIME_FALLBACK")
    if transfer_observed != 0:
        alerts.append("TRANSFER_PENDING_UNMAPPED")
    if pdvb == 0:
        status = "ZERO_PDVB"
    elif alerts:
        status = "WARN"
    else:
        status = "OK"

    row = {
        "origin_cd": int(estimate["origin_cd"]),
        "sucursal": int(estimate["sucursal"]),
        "codigo_articulo": int(estimate["codigo_articulo"]),
        "c_proveedor_primario": estimate.get("c_proveedor_primario"),
        "physical_stock": _q6(physical),
        "direct_po_inbound": _q6(direct_po),
        "cd_in_transit": _q6(transit),
        "special_sale_committed": Decimal("0.000000"),
        "confirmed_transfer_pending": Decimal("0.000000"),
        "pdvb_business_date": estimate["business_date"],
        "pdvb_estimate_id": estimate["pdvb_estimate_id"],
        "pdvb_value": _q6(pdvb),
        "lead_time_days": lead_time.quantize(Decimal("0.0001")),
        "target_stock_days": target_days.quantize(Decimal("0.0001")),
        "overstock_days": overstock_days.quantize(Decimal("0.0001")),
        "critical_stock": _q6(pdvb * lead_time),
        "minimum_stock": _q6(pdvb * lead_time * 2),
        "maximum_stock": _q6(pdvb * target_days),
        "overstock_quantity": _q6(pdvb * overstock_days),
        "coverage_days": coverage,
        "calculation_status": status,
        "alert_codes": alerts,
        "explanation": {
            "pdvb_status": estimate["status"],
            "lead_time_source_value": source_lead,
            "lead_time_fallback_used": used_fallback,
            "transfer_pendiente_observed": transfer_observed,
            "special_sale_committed": "SOURCE_PENDING_ASSUMED_ZERO",
            "confirmed_transfer_pending": "SEMANTIC_PENDING_ASSUMED_ZERO",
        },
    }
    row["input_checksum"] = _row_checksum(
        row,
        (
            "origin_cd", "sucursal", "codigo_articulo", "physical_stock",
            "direct_po_inbound", "cd_in_transit", "pdvb_estimate_id",
            "pdvb_value", "lead_time_days", "target_stock_days",
            "overstock_days", "calculation_status", "alert_codes",
        ),
    )
    return row


def build_need_rows(
    branch: Mapping[str, Any],
    logistics: Mapping[str, Any],
    business_date: date,
) -> list[dict[str, Any]]:
    pdvb = _decimal(branch["pdvb_value"], Decimal("0"))
    net_stock = (
        _decimal(branch["physical_stock"], Decimal("0"))
        + _decimal(branch["direct_po_inbound"], Decimal("0"))
        + _decimal(branch["cd_in_transit"], Decimal("0"))
    )
    assert pdvb is not None and net_stock is not None
    maximum = _decimal(branch["maximum_stock"], Decimal("0"))
    overstock = _decimal(branch["overstock_quantity"], Decimal("0"))
    assert maximum is not None and overstock is not None
    demand = max(maximum - net_stock, Decimal("0"))
    extra = max(maximum + overstock - max(net_stock, Decimal("0")), Decimal("0"))
    surplus = max(extra - demand, Decimal("0"))

    purchase_factor = _decimal(logistics.get("units_per_package")) or Decimal("1")
    packages_per_pallet = _decimal(logistics.get("packages_per_pallet"))
    unit_weight = _decimal(logistics.get("unit_weight_kg"))
    unit_volume = _decimal(logistics.get("unit_volume_m3"))
    irq = calculate_irq(
        net_stock,
        _decimal(branch.get("coverage_days")),
        _decimal(branch["lead_time_days"], Decimal("1")),
        _decimal(branch["target_stock_days"], Decimal("0")),
    )
    target_date = business_date + timedelta(
        days=int(_decimal(branch["lead_time_days"], Decimal("1")).to_integral_value(rounding=ROUND_CEILING))
    )

    result: list[dict[str, Any]] = []
    for need_type, mandatory, quantity in (
        ("D", True, demand),
        ("S", False, surplus),
    ):
        rounded = round_to_logistics(quantity, purchase_factor)
        estimated_packages = _q6(rounded / purchase_factor)
        estimated_pallets = (
            _q6(estimated_packages / packages_per_pallet)
            if packages_per_pallet is not None and packages_per_pallet > 0
            else None
        )
        row = {
            "origin_cd": branch["origin_cd"],
            "sucursal": branch["sucursal"],
            "codigo_articulo": branch["codigo_articulo"],
            "c_proveedor_primario": branch.get("c_proveedor_primario"),
            "need_type": need_type,
            "is_mandatory": mandatory,
            "calculated_quantity": _q6(quantity),
            "rounded_quantity": rounded,
            "rounding_unit": _q6(purchase_factor),
            "open_quantity": rounded,
            "irq_score": irq.quantize(Decimal("0.01")),
            "priority_score": irq.quantize(SIX_PLACES),
            "target_date": target_date,
            "formula_code": f"NDD_{need_type}",
            "formula_version": "V1_TEST_PILOT",
            "logistics_snapshot_id": logistics["item_logistics_snapshot_id"],
            "estimated_packages": estimated_packages,
            "estimated_pallets": estimated_pallets,
            "estimated_weight_kg": _q6(rounded * unit_weight) if unit_weight is not None else None,
            "estimated_volume_m3": _q6(rounded * unit_volume) if unit_volume is not None else None,
            "calculation_status": "CALCULATED" if rounded > 0 else "ZERO",
            "alert_codes": list(branch["alert_codes"]),
            "explanation": {
                "net_stock": net_stock,
                "maximum_stock": maximum,
                "overstock_quantity": overstock,
                "rounding_method": "CEIL_TO_PURCHASE_FACTOR",
                "logistics_quality_status": logistics["quality_status"],
            },
        }
        row["input_checksum"] = _row_checksum(
            row,
            (
                "origin_cd", "sucursal", "codigo_articulo", "need_type",
                "calculated_quantity", "rounded_quantity", "rounding_unit",
                "irq_score", "formula_version", "logistics_snapshot_id",
            ),
        )
        result.append(row)
    return result


def _ensure_partition(connection: Connection, parent: str, business_date: date) -> None:
    allowed = {
        "pdd_branch_stock_position",
        "pdd_cd_stock_position",
        "pdd_need_snapshot",
    }
    if parent not in allowed:
        raise ValueError(f"Tabla particionada no admitida: {parent}")
    month_start = business_date.replace(day=1)
    next_month = (
        date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else date(month_start.year, month_start.month + 1, 1)
    )
    partition = f"{parent}_y{month_start.year:04d}m{month_start.month:02d}"
    connection.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS stock_management.{partition}
            PARTITION OF stock_management.{parent}
            FOR VALUES FROM ('{month_start.isoformat()}') TO ('{next_month.isoformat()}')
            """
        )
    )


def _ensure_configuration(
    connection: Connection,
    configuration: OperationalConfiguration,
    created_by: str,
) -> int:
    existing = connection.execute(
        text(
            """
            SELECT configuration_version_id, configuration_code, version_no,
                   status, parameters, checksum
            FROM stock_management.pdd_configuration_version
            WHERE configuration_version_uuid = CAST(:uuid AS uuid)
            """
        ),
        {"uuid": configuration.configuration_version_uuid},
    ).mappings().one_or_none()
    if existing is not None:
        if (
            existing["configuration_code"] != configuration.configuration_code
            or existing["version_no"] != configuration.version_no
            or existing["status"] != configuration.status
            or existing["parameters"] != configuration.parameters
            or existing["checksum"].strip() != configuration.checksum
        ):
            raise RuntimeError("La configuracion operativa persistida difiere del manifiesto")
        return existing["configuration_version_id"]
    return connection.execute(
        text(
            """
            INSERT INTO stock_management.pdd_configuration_version (
                configuration_version_uuid, configuration_code, version_no,
                status, valid_from, parameters, checksum, created_by
            ) VALUES (
                CAST(:uuid AS uuid), :code, :version_no, :status, :valid_from,
                CAST(:parameters AS jsonb), :checksum, :created_by
            ) RETURNING configuration_version_id
            """
        ),
        {
            "uuid": configuration.configuration_version_uuid,
            "code": configuration.configuration_code,
            "version_no": configuration.version_no,
            "status": configuration.status,
            "valid_from": configuration.valid_from,
            "parameters": _json(configuration.parameters),
            "checksum": configuration.checksum,
            "created_by": created_by,
        },
    ).scalar_one()


def _read_source_stock(
    engine: Engine,
    scope_version_uuid: UUID,
    business_date: date,
    origin_cd: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], datetime]:
    with engine.connect() as connection:
        branch_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    WITH scope_pairs AS (
                        SELECT codigo_articulo, destination_branch AS sucursal
                        FROM datamart.dm_pdd_scope_pair
                        WHERE scope_version_uuid = CAST(:scope_uuid AS uuid)
                    ), ranked AS (
                        SELECT s.*, row_number() OVER (
                            PARTITION BY codigo_articulo, codigo_sucursal
                            ORDER BY fecha_extraccion DESC NULLS LAST
                        ) AS rn
                        FROM src.base_stock_sucursal AS s
                        WHERE fecha_stock::date = :business_date
                    )
                    SELECT p.codigo_articulo, p.sucursal, s.codigo_proveedor,
                           s.stock, s.pedido_pendiente, s.transito_pendiente,
                           s.transfer_pendiente, s.dias_preparacion,
                           s.q_dias_stock, s.q_dias_sobre_stock,
                           s.fecha_extraccion
                    FROM scope_pairs AS p
                    LEFT JOIN ranked AS s
                      ON s.codigo_articulo = p.codigo_articulo
                     AND s.codigo_sucursal = p.sucursal AND s.rn = 1
                    ORDER BY p.sucursal, p.codigo_articulo
                    """
                ),
                {"scope_uuid": scope_version_uuid, "business_date": business_date},
            ).mappings()
        ]
        cd_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    WITH scope_articles AS (
                        SELECT codigo_articulo
                        FROM datamart.dm_pdd_scope_article
                        WHERE scope_version_uuid = CAST(:scope_uuid AS uuid)
                    ), ranked AS (
                        SELECT s.*, row_number() OVER (
                            PARTITION BY codigo_articulo, codigo_sucursal
                            ORDER BY fecha_extraccion DESC NULLS LAST
                        ) AS rn
                        FROM src.base_stock_sucursal AS s
                        WHERE fecha_stock::date = :business_date
                          AND codigo_sucursal = :origin_cd
                    )
                    SELECT a.codigo_articulo, s.codigo_proveedor, s.stock,
                           s.pedido_pendiente, s.pedido_pendiente_fecha,
                           s.fecha_extraccion
                    FROM scope_articles AS a
                    LEFT JOIN ranked AS s
                      ON s.codigo_articulo = a.codigo_articulo AND s.rn = 1
                    ORDER BY a.codigo_articulo
                    """
                ),
                {
                    "scope_uuid": scope_version_uuid,
                    "business_date": business_date,
                    "origin_cd": origin_cd,
                },
            ).mappings()
        ]
    if any(row["stock"] is None for row in branch_rows + cd_rows):
        raise RuntimeError("La fuente de stock no cubre completamente el scope")
    timestamps = [
        row["fecha_extraccion"]
        for row in branch_rows + cd_rows
        if row["fecha_extraccion"] is not None
    ]
    if not timestamps:
        raise RuntimeError("La fuente de stock no posee fecha_extraccion")
    return branch_rows, cd_rows, max(timestamps)


def run_daily_decas(
    source_engine: Engine,
    source_settings: Settings,
    target_engine: Engine,
    target_settings: OperationalSettings,
    business_date: date,
    scope_version_uuid: UUID,
    pdvb_calculation_run_uuid: UUID,
    logistics_calculation_run_uuid: UUID,
    configuration_version_uuid: UUID,
    created_by: str,
    calculation_run_uuid: UUID | None = None,
) -> DailyDecasResult:
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")
    run_uuid = calculation_run_uuid or uuid4()
    configuration = load_operational_configuration(configuration_version_uuid)
    fallback_lead = Decimal(
        str(configuration.parameters["lead_time_days"]["fallback"])
    )
    source_branches, source_cd, source_as_of_ts = _read_source_stock(
        source_engine,
        scope_version_uuid,
        business_date,
        source_settings.origin_cd,
    )
    source_by_pair = {
        (row["codigo_articulo"], row["sucursal"]): row for row in source_branches
    }

    with transactional_connection(target_engine, target_settings) as target:
        target.execute(text("SELECT pg_advisory_xact_lock(hashtext('pdd.daily.decas'))"))
        required = (
            "pdd_calculation_run", "pdd_source_snapshot", "pdd_configuration_version",
            "pdd_distribution_scope_version", "pdd_distribution_scope_pair",
            "pdd_pdvb_estimate", "pdd_item_logistics_snapshot",
            "pdd_branch_stock_position", "pdd_cd_stock_position", "pdd_need_snapshot",
        )
        missing = target.execute(
            text(
                """
                SELECT array_agg(name ORDER BY name)
                FROM unnest(CAST(:names AS text[])) AS required(name)
                WHERE to_regclass('stock_management.' || name) IS NULL
                """
            ),
            {"names": list(required)},
        ).scalar_one()
        if missing:
            raise RuntimeError(f"Contrato operativo incompleto: {missing}")

        existing = target.execute(
            text(
                """
                SELECT calculation_run_id, business_date, status, input_checksum,
                       summary,
                       (SELECT count(*) FROM stock_management.pdd_branch_stock_position b
                        WHERE b.calculation_run_id=r.calculation_run_id) AS branches,
                       (SELECT count(*) FROM stock_management.pdd_need_snapshot n
                        WHERE n.calculation_run_id=r.calculation_run_id) AS needs,
                       (SELECT count(*) FROM stock_management.pdd_cd_stock_position c
                        WHERE c.calculation_run_id=r.calculation_run_id) AS cd_rows
                FROM stock_management.pdd_calculation_run r
                WHERE calculation_run_uuid=CAST(:run_uuid AS uuid)
                """
            ),
            {"run_uuid": run_uuid},
        ).mappings().one_or_none()
        if existing is not None:
            existing_summary = existing["summary"]
            if (
                existing["status"] != "SUCCEEDED"
                or existing["business_date"] != business_date
                or existing_summary.get("scope_version_uuid") != str(scope_version_uuid)
                or existing_summary.get("pdvb_calculation_run_uuid")
                != str(pdvb_calculation_run_uuid)
                or existing_summary.get("logistics_calculation_run_uuid")
                != str(logistics_calculation_run_uuid)
                or existing_summary.get("configuration_version_uuid")
                != str(configuration_version_uuid)
            ):
                raise RuntimeError("Existe una corrida DAILY_DECAS no reutilizable")
            return DailyDecasResult(
                calculation_run_uuid=run_uuid,
                business_date=business_date,
                scope_version_uuid=scope_version_uuid,
                pdvb_calculation_run_uuid=pdvb_calculation_run_uuid,
                configuration_version_uuid=configuration_version_uuid,
                branch_positions=existing["branches"],
                excluded_blocked_pdvb=existing_summary["excluded_blocked_pdvb"],
                need_rows=existing["needs"],
                cd_positions=existing["cd_rows"],
                branch_status_counts=existing_summary["branch_status_counts"],
                need_status_counts=existing_summary["need_status_counts"],
                source_checksum=existing["input_checksum"],
                target_database=target_settings.pg_database,
                reused_run=True,
            )

        pdvb_header = target.execute(
            text(
                """
                SELECT r.calculation_run_id, r.business_date, r.status,
                       r.scope_version_id, s.scope_version_uuid, s.pair_count
                FROM stock_management.pdd_calculation_run r
                JOIN stock_management.pdd_distribution_scope_version s
                  ON s.scope_version_id=r.scope_version_id
                WHERE r.calculation_run_uuid=CAST(:uuid AS uuid)
                """
            ),
            {"uuid": pdvb_calculation_run_uuid},
        ).mappings().one_or_none()
        if (
            pdvb_header is None
            or pdvb_header["status"] != "SUCCEEDED"
            or pdvb_header["scope_version_uuid"] != scope_version_uuid
            or pdvb_header["business_date"] > business_date
        ):
            raise RuntimeError("La corrida PDVB no es compatible con DAILY_DECAS")
        estimates = [
            dict(row)
            for row in target.execute(
                text(
                    """
                    SELECT e.business_date, e.pdvb_estimate_id, e.origin_cd,
                           e.codigo_articulo, e.sucursal, e.c_proveedor_primario,
                           e.status, e.pdvb_value
                    FROM stock_management.pdd_pdvb_estimate e
                    WHERE e.calculation_run_id=:run_id
                    ORDER BY e.sucursal,e.codigo_articulo
                    """
                ),
                {"run_id": pdvb_header["calculation_run_id"]},
            ).mappings()
        ]
        if len(estimates) != pdvb_header["pair_count"]:
            raise RuntimeError("La corrida PDVB no cubre el scope operativo")
        publicable = [row for row in estimates if row["status"] != "BLOCKED"]
        excluded_blocked = len(estimates) - len(publicable)

        logistics_header = target.execute(
            text(
                """
                SELECT calculation_run_id,status
                FROM stock_management.pdd_calculation_run
                WHERE calculation_run_uuid=CAST(:uuid AS uuid)
                """
            ),
            {"uuid": logistics_calculation_run_uuid},
        ).mappings().one_or_none()
        if logistics_header is None or logistics_header["status"] != "SUCCEEDED":
            raise RuntimeError("La corrida logistica no esta disponible")
        logistics = {
            row["codigo_articulo"]: dict(row)
            for row in target.execute(
                text(
                    """
                    SELECT item_logistics_snapshot_id,codigo_articulo,
                           units_per_package,packages_per_pallet,unit_weight_kg,
                           unit_volume_m3,quality_status
                    FROM stock_management.pdd_item_logistics_snapshot
                    WHERE calculation_run_id=:run_id
                    """
                ),
                {"run_id": logistics_header["calculation_run_id"]},
            ).mappings()
        }
        if len(logistics) == 0:
            raise RuntimeError("La corrida logistica no contiene articulos")

        branches = []
        for estimate in publicable:
            key = (estimate["codigo_articulo"], estimate["sucursal"])
            source = source_by_pair.get(key)
            if source is None:
                raise RuntimeError(f"Par sin stock fuente: {key}")
            branches.append(build_branch_position(source, estimate, fallback_lead))
        if len(branches) != len(publicable):
            raise RuntimeError("La posicion de sucursal no cubre los PDVB publicables")

        needs: list[dict[str, Any]] = []
        for branch in branches:
            item_logistics = logistics.get(branch["codigo_articulo"])
            if item_logistics is None:
                raise RuntimeError("Articulo sin snapshot logistico")
            needs.extend(build_need_rows(branch, item_logistics, business_date))

        mandatory = defaultdict(Decimal)
        optional = defaultdict(Decimal)
        for need in needs:
            target_map = mandatory if need["need_type"] == "D" else optional
            target_map[need["codigo_articulo"]] += need["open_quantity"]
        cd_positions: list[dict[str, Any]] = []
        for source in source_cd:
            article = source["codigo_articulo"]
            physical = _decimal(source["stock"])
            assert physical is not None
            po = _nonnegative(source.get("pedido_pendiente"))
            required_quantity = mandatory[article]
            available = physical + po
            coverage_index = (
                _q6(available / required_quantity) if required_quantity > 0 else None
            )
            alerts = ["PO_DUE_CLASSIFICATION_PENDING"] if po > 0 else []
            row = {
                "origin_cd": source_settings.origin_cd,
                "codigo_articulo": article,
                "c_proveedor_primario": source.get("codigo_proveedor"),
                "physical_stock": _q6(physical),
                "open_po_on_time": _q6(po),
                "open_po_overdue": Decimal("0.000000"),
                "mandatory_backlog": _q6(required_quantity),
                "optional_backlog": _q6(optional[article]),
                "coverage_index": coverage_index,
                "status": "WARN" if alerts else "OK",
                "alert_codes": alerts,
            }
            row["input_checksum"] = _row_checksum(
                row,
                (
                    "origin_cd", "codigo_articulo", "physical_stock",
                    "open_po_on_time", "open_po_overdue", "mandatory_backlog",
                    "optional_backlog", "coverage_index", "status",
                ),
            )
            cd_positions.append(row)

        branch_checksum = _rows_checksum(branches, ("sucursal", "codigo_articulo"))
        need_checksum = _rows_checksum(needs, ("sucursal", "codigo_articulo", "need_type"))
        cd_checksum = _rows_checksum(cd_positions, ("codigo_articulo",))
        source_checksum = hashlib.sha256(
            f"{branch_checksum}|{need_checksum}|{cd_checksum}".encode("ascii")
        ).hexdigest()
        branch_counts = dict(Counter(row["calculation_status"] for row in branches))
        need_counts = dict(Counter(row["calculation_status"] for row in needs))
        configuration_id = _ensure_configuration(target, configuration, created_by.strip())
        attempt_no = target.execute(
            text(
                """
                SELECT coalesce(max(attempt_no),0)+1
                FROM stock_management.pdd_calculation_run
                WHERE run_type='DAILY_DECAS' AND business_date=:business_date
                  AND scope_type='CD' AND scope_id=:scope_id
                """
            ),
            {"business_date": business_date, "scope_id": str(source_settings.origin_cd)},
        ).scalar_one()
        summary = {
            "entity": "PDD_DAILY_DECAS_TEST_PILOT",
            "scope_version_uuid": str(scope_version_uuid),
            "pdvb_calculation_run_uuid": str(pdvb_calculation_run_uuid),
            "logistics_calculation_run_uuid": str(logistics_calculation_run_uuid),
            "configuration_version_uuid": str(configuration_version_uuid),
            "branch_status_counts": branch_counts,
            "need_status_counts": need_counts,
            "excluded_blocked_pdvb": excluded_blocked,
            "assumptions": [
                "LEAD_TIME_FALLBACK_15_WHEN_MISSING_OR_NON_POSITIVE",
                "SPECIAL_SALE_COMMITMENT_ASSUMED_ZERO",
                "CONFIRMED_TRANSFER_PENDING_ASSUMED_ZERO",
                "ALL_OPEN_PO_TEMPORARILY_CLASSIFIED_ON_TIME",
            ],
        }
        calculation_run_id = target.execute(
            text(
                """
                INSERT INTO stock_management.pdd_calculation_run (
                    calculation_run_uuid,run_type,business_date,cutoff_date,
                    scope_type,scope_id,attempt_no,scope_version_id,
                    configuration_version_id,formula_version,status,started_at,
                    created_by,input_row_count,output_row_count,warning_count,
                    error_count,input_checksum,summary
                ) VALUES (
                    CAST(:uuid AS uuid),'DAILY_DECAS',:business_date,:cutoff_date,
                    'CD',:scope_id,:attempt_no,:scope_version_id,
                    :configuration_version_id,'DAILY_DECAS_V1_TEST_PILOT','RUNNING',
                    clock_timestamp(),:created_by,:input_rows,:output_rows,
                    :warning_count,0,:checksum,CAST(:summary AS jsonb)
                ) RETURNING calculation_run_id
                """
            ),
            {
                "uuid": run_uuid,
                "business_date": business_date,
                "cutoff_date": calculation_cutoff_date(business_date),
                "scope_id": str(source_settings.origin_cd),
                "attempt_no": attempt_no,
                "scope_version_id": pdvb_header["scope_version_id"],
                "configuration_version_id": configuration_id,
                "created_by": created_by.strip(),
                "input_rows": len(source_branches) + len(source_cd),
                "output_rows": len(branches) + len(needs) + len(cd_positions),
                "warning_count": branch_counts.get("WARN", 0),
                "checksum": source_checksum,
                "summary": _json(summary),
            },
        ).scalar_one()
        stock_snapshot_id = target.execute(
            text(
                """
                INSERT INTO stock_management.pdd_source_snapshot (
                    calculation_run_id,source_code,source_database,physical_relation,
                    is_required,min_business_date,max_business_date,as_of_ts,
                    row_count,checksum,status,detail
                ) VALUES (
                    :run_id,'BRANCH_AND_CD_STOCK',:source_database,
                    'src.base_stock_sucursal',true,:business_date,:business_date,
                    :as_of_ts,:row_count,:checksum,'VALID',CAST(:detail AS jsonb)
                ) RETURNING source_snapshot_id
                """
            ),
            {
                "run_id": calculation_run_id,
                "source_database": source_settings.pg_database,
                "business_date": business_date,
                "as_of_ts": source_as_of_ts,
                "row_count": len(source_branches) + len(source_cd),
                "checksum": source_checksum,
                "detail": _json({"scope_version_uuid": str(scope_version_uuid)}),
            },
        ).scalar_one()

        for parent in (
            "pdd_branch_stock_position", "pdd_cd_stock_position", "pdd_need_snapshot"
        ):
            _ensure_partition(target, parent, business_date)
        branch_insert = text(
            """
            INSERT INTO stock_management.pdd_branch_stock_position (
                business_date,calculation_run_id,scope_version_id,origin_cd,sucursal,
                codigo_articulo,c_proveedor_primario,physical_stock,direct_po_inbound,
                cd_in_transit,special_sale_committed,confirmed_transfer_pending,
                pdvb_business_date,pdvb_estimate_id,pdvb_value,lead_time_days,
                target_stock_days,overstock_days,critical_stock,minimum_stock,
                maximum_stock,overstock_quantity,coverage_days,
                stock_source_snapshot_id,direct_po_source_snapshot_id,
                transit_source_snapshot_id,configuration_version_id,
                calculation_status,explanation,alert_codes,input_checksum
            ) VALUES (
                :business_date,:calculation_run_id,:scope_version_id,:origin_cd,:sucursal,
                :codigo_articulo,:c_proveedor_primario,:physical_stock,:direct_po_inbound,
                :cd_in_transit,:special_sale_committed,:confirmed_transfer_pending,
                :pdvb_business_date,:pdvb_estimate_id,:pdvb_value,:lead_time_days,
                :target_stock_days,:overstock_days,:critical_stock,:minimum_stock,
                :maximum_stock,:overstock_quantity,:coverage_days,
                :stock_snapshot_id,:stock_snapshot_id,:stock_snapshot_id,
                :configuration_version_id,:calculation_status,CAST(:explanation AS jsonb),
                :alert_codes,:input_checksum
            )
            """
        )
        for chunk in _chunks(branches):
            target.execute(
                branch_insert,
                [
                    {
                        **row,
                        "business_date": business_date,
                        "calculation_run_id": calculation_run_id,
                        "scope_version_id": pdvb_header["scope_version_id"],
                        "stock_snapshot_id": stock_snapshot_id,
                        "configuration_version_id": configuration_id,
                        "explanation": _json(row["explanation"]),
                    }
                    for row in chunk
                ],
            )
        branch_ids = {
            (row["codigo_articulo"], row["sucursal"]): row["branch_stock_position_id"]
            for row in target.execute(
                text(
                    """
                    SELECT branch_stock_position_id,codigo_articulo,sucursal
                    FROM stock_management.pdd_branch_stock_position
                    WHERE business_date=:business_date AND calculation_run_id=:run_id
                    """
                ),
                {"business_date": business_date, "run_id": calculation_run_id},
            ).mappings()
        }
        need_insert = text(
            """
            INSERT INTO stock_management.pdd_need_snapshot (
                business_date,calculation_run_id,branch_stock_position_id,
                scope_version_id,origin_cd,sucursal,codigo_articulo,
                c_proveedor_primario,need_type,is_mandatory,calculated_quantity,
                rounded_quantity,rounding_unit,open_quantity,irq_score,priority_score,
                target_date,formula_code,formula_version,configuration_version_id,
                logistics_snapshot_id,estimated_packages,estimated_pallets,
                estimated_weight_kg,estimated_volume_m3,calculation_status,
                explanation,alert_codes,input_checksum
            ) VALUES (
                :business_date,:calculation_run_id,:branch_stock_position_id,
                :scope_version_id,:origin_cd,:sucursal,:codigo_articulo,
                :c_proveedor_primario,:need_type,:is_mandatory,:calculated_quantity,
                :rounded_quantity,:rounding_unit,:open_quantity,:irq_score,:priority_score,
                :target_date,:formula_code,:formula_version,:configuration_version_id,
                :logistics_snapshot_id,:estimated_packages,:estimated_pallets,
                :estimated_weight_kg,:estimated_volume_m3,:calculation_status,
                CAST(:explanation AS jsonb),:alert_codes,:input_checksum
            )
            """
        )
        for chunk in _chunks(needs):
            target.execute(
                need_insert,
                [
                    {
                        **row,
                        "business_date": business_date,
                        "calculation_run_id": calculation_run_id,
                        "branch_stock_position_id": branch_ids[(row["codigo_articulo"], row["sucursal"])],
                        "scope_version_id": pdvb_header["scope_version_id"],
                        "configuration_version_id": configuration_id,
                        "explanation": _json(row["explanation"]),
                    }
                    for row in chunk
                ],
            )
        cd_insert = text(
            """
            INSERT INTO stock_management.pdd_cd_stock_position (
                business_date,calculation_run_id,origin_cd,codigo_articulo,
                c_proveedor_primario,physical_stock,open_po_on_time,open_po_overdue,
                mandatory_backlog,optional_backlog,coverage_index,
                stock_source_snapshot_id,po_source_snapshot_id,status,alert_codes,
                input_checksum
            ) VALUES (
                :business_date,:calculation_run_id,:origin_cd,:codigo_articulo,
                :c_proveedor_primario,:physical_stock,:open_po_on_time,:open_po_overdue,
                :mandatory_backlog,:optional_backlog,:coverage_index,
                :stock_snapshot_id,:stock_snapshot_id,:status,:alert_codes,:input_checksum
            )
            """
        )
        for chunk in _chunks(cd_positions):
            target.execute(
                cd_insert,
                [
                    {
                        **row,
                        "business_date": business_date,
                        "calculation_run_id": calculation_run_id,
                        "stock_snapshot_id": stock_snapshot_id,
                    }
                    for row in chunk
                ],
            )
        persisted = target.execute(
            text(
                """
                SELECT
                  (SELECT count(*) FROM stock_management.pdd_branch_stock_position
                   WHERE business_date=:d AND calculation_run_id=:r) branches,
                  (SELECT count(*) FROM stock_management.pdd_need_snapshot
                   WHERE business_date=:d AND calculation_run_id=:r) needs,
                  (SELECT count(*) FROM stock_management.pdd_cd_stock_position
                   WHERE business_date=:d AND calculation_run_id=:r) cd_rows
                """
            ),
            {"d": business_date, "r": calculation_run_id},
        ).mappings().one()
        if (
            persisted["branches"] != len(branches)
            or persisted["needs"] != len(needs)
            or persisted["cd_rows"] != len(cd_positions)
        ):
            raise RuntimeError("La persistencia DAILY_DECAS quedo incompleta")
        target.execute(
            text(
                """
                UPDATE stock_management.pdd_calculation_run SET is_current=false
                WHERE run_type='DAILY_DECAS' AND business_date=:business_date
                  AND scope_type='CD' AND scope_id=:scope_id
                  AND calculation_run_id<>:run_id
                """
            ),
            {
                "business_date": business_date,
                "scope_id": str(source_settings.origin_cd),
                "run_id": calculation_run_id,
            },
        )
        target.execute(
            text(
                """
                UPDATE stock_management.pdd_calculation_run
                SET status='SUCCEEDED',is_current=true,finished_at=clock_timestamp(),
                    output_checksum=:checksum
                WHERE calculation_run_id=:run_id
                """
            ),
            {"checksum": source_checksum, "run_id": calculation_run_id},
        )

    return DailyDecasResult(
        calculation_run_uuid=run_uuid,
        business_date=business_date,
        scope_version_uuid=scope_version_uuid,
        pdvb_calculation_run_uuid=pdvb_calculation_run_uuid,
        configuration_version_uuid=configuration_version_uuid,
        branch_positions=len(branches),
        excluded_blocked_pdvb=excluded_blocked,
        need_rows=len(needs),
        cd_positions=len(cd_positions),
        branch_status_counts=branch_counts,
        need_status_counts=need_counts,
        source_checksum=source_checksum,
        target_database=target_settings.pg_database,
        reused_run=False,
    )
