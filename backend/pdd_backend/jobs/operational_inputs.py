from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from ..config import OperationalSettings, Settings
from ..db import transactional_connection


LOGISTICS_COLUMNS = (
    "codigo_articulo",
    "base_unit",
    "units_per_package",
    "packages_per_pallet",
    "unit_weight_kg",
    "unit_volume_m3",
    "source_logistics_id",
    "supplier_code",
    "logistics_configuration_code",
    "source_valid_from",
    "sells_by_weight",
    "package_uom",
    "unit_gtin",
    "package_gtin",
    "source_reference",
    "unit_net_weight_kg",
    "unit_gross_weight_kg",
    "package_gross_weight_kg",
    "weight_basis",
    "package_length_cm",
    "package_width_cm",
    "package_height_cm",
    "package_volume_m3",
    "volume_method",
    "packages_per_layer",
    "layers_per_pallet",
    "units_per_pallet",
    "pallet_type",
    "pallet_length_cm",
    "pallet_width_cm",
    "loaded_pallet_height_cm",
    "pallet_gross_weight_kg",
    "stackable",
    "max_stack_levels",
    "fragile",
    "hazardous",
    "temperature_zone",
    "temperature_min_c",
    "temperature_max_c",
    "orientation_code",
    "packaging_quality_status",
    "weight_quality_status",
    "volume_quality_status",
    "pallet_quality_status",
    "quality_issue_codes",
    "verified_at",
    "verified_by",
    "attributes",
    "quality_status",
)

AXIS_QUALITY_VALUES = {"VERIFIED", "SOURCE", "ESTIMATED", "MISSING", "INVALID"}


@dataclass(frozen=True)
class LogisticsPublicationResult:
    calculation_run_uuid: UUID
    business_date: date
    scope_version_uuid: UUID
    source_as_of_ts: datetime
    source_rows: int
    published_rows: int
    quality_counts: dict[str, int]
    source_checksum: str
    target_database: str
    reused_publication: bool = False

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "calculation_run_uuid": str(self.calculation_run_uuid),
            "business_date": self.business_date.isoformat(),
            "scope_version_uuid": str(self.scope_version_uuid),
            "source_as_of_ts": self.source_as_of_ts.isoformat(),
        }


@dataclass(frozen=True)
class StockReadinessResult:
    scope_version_uuid: UUID
    expected_through: date
    stock_date: date | None
    source_as_of_ts: datetime | None
    scope_pairs: int
    covered_pairs: int
    missing_pairs: int
    excluded_branch_pairs: int
    unexplained_missing_pairs: int
    excluded_branch_count: int
    excluded_branches: tuple[int, ...]
    duplicate_pairs: int
    null_physical_stock: int
    scope_articles: int
    covered_cd_articles: int
    missing_cd_articles: int
    duplicate_cd_articles: int
    null_cd_physical_stock: int
    negative_purchase_orders: int
    negative_in_transit: int
    transfer_positive: int
    transfer_negative: int
    open_po_as_of_ts: datetime | None
    open_po_positive_lines: int
    open_po_excluded_negative_lines: int
    branch_pairs_with_open_po: int
    cd_articles_with_open_po: int
    status: str
    blockers: tuple[str, ...]
    mapping: dict[str, str]

    def serializable(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "scope_version_uuid": str(self.scope_version_uuid),
            "expected_through": self.expected_through.isoformat(),
            "stock_date": self.stock_date.isoformat() if self.stock_date else None,
            "source_as_of_ts": (
                self.source_as_of_ts.isoformat() if self.source_as_of_ts else None
            ),
            "open_po_as_of_ts": (
                self.open_po_as_of_ts.isoformat() if self.open_po_as_of_ts else None
            ),
            "blockers": list(self.blockers),
            "excluded_branches": list(self.excluded_branches),
        }


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _positive(value: Any) -> Decimal | None:
    number = _decimal(value)
    return number if number is not None and number > 0 else None


def _canonical_number(value: Any) -> str:
    number = _decimal(value)
    if number is None:
        return ""
    normalized = format(number.normalize(), "f")
    return "0" if normalized in {"-0", ""} else normalized


def _axis_quality(value: Any, *, source_present: bool) -> str:
    if not source_present:
        return "MISSING"
    normalized = str(value or "MISSING").strip().upper()
    return normalized if normalized in AXIS_QUALITY_VALUES else "INVALID"


def _effective_unit_weight(
    unit_gross_weight_kg: Decimal | None,
    package_gross_weight_kg: Decimal | None,
    units_per_package: Decimal | None,
    unit_net_weight_kg: Decimal | None,
) -> tuple[Decimal | None, str | None]:
    if unit_gross_weight_kg is not None:
        return unit_gross_weight_kg, "GROSS_UNIT"
    if package_gross_weight_kg is not None and units_per_package is not None:
        return (
            (package_gross_weight_kg / units_per_package).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            ),
            "GROSS_PACKAGE_DERIVED",
        )
    if unit_net_weight_kg is not None:
        return unit_net_weight_kg, "NET_UNIT_FALLBACK"
    return None, None


def normalize_logistics_row(row: Mapping[str, Any]) -> dict[str, Any]:
    source_present = row.get("source_codigo_articulo") is not None
    sells_by_weight = row.get("m_vende_por_peso") if source_present else None
    base_unit = str(row.get("c_unidad_base") or "UNKNOWN").strip().upper()
    if not source_present:
        base_unit = "UNKNOWN"

    units_per_package = _positive(row.get("q_unidades_por_bulto"))
    packages_per_pallet = _positive(row.get("q_bultos_por_pallet"))
    unit_net_weight_kg = _positive(row.get("q_peso_neto_unitario_kg"))
    unit_gross_weight_kg = _positive(row.get("q_peso_bruto_unitario_kg"))
    package_gross_weight_kg = _positive(row.get("q_peso_bruto_bulto_kg"))
    unit_weight_kg, weight_basis = _effective_unit_weight(
        unit_gross_weight_kg,
        package_gross_weight_kg,
        units_per_package,
        unit_net_weight_kg,
    )
    unit_volume_m3 = _positive(row.get("q_volumen_unitario_m3"))

    packaging_quality = _axis_quality(
        row.get("c_calidad_embalaje"), source_present=source_present
    )
    weight_quality = _axis_quality(
        row.get("c_calidad_peso"), source_present=source_present
    )
    volume_quality = _axis_quality(
        row.get("c_calidad_volumen"), source_present=source_present
    )
    pallet_quality = _axis_quality(
        row.get("c_calidad_pallet"), source_present=source_present
    )

    if packaging_quality not in {"MISSING", "INVALID"} and (
        base_unit == "UNKNOWN" or units_per_package is None
    ):
        packaging_quality = "INVALID"
    if weight_quality not in {"MISSING", "INVALID"} and unit_weight_kg is None:
        weight_quality = "INVALID"
    if volume_quality not in {"MISSING", "INVALID"} and unit_volume_m3 is None:
        volume_quality = "INVALID"
    if pallet_quality not in {"MISSING", "INVALID"} and packages_per_pallet is None:
        pallet_quality = "INVALID"

    axis_quality = (
        packaging_quality,
        weight_quality,
        volume_quality,
        pallet_quality,
    )
    if "INVALID" in axis_quality:
        quality_status = "INVALID"
    elif not source_present:
        quality_status = "MISSING"
    elif "MISSING" in axis_quality:
        quality_status = "PARTIAL"
    elif "ESTIMATED" in axis_quality:
        quality_status = "ESTIMATED"
    else:
        quality_status = "COMPLETE"

    issue_codes = []
    for axis, status, missing_code in (
        ("PACKAGING", packaging_quality, "PACKAGING_MISSING"),
        ("WEIGHT", weight_quality, "WEIGHT_MISSING"),
        ("VOLUME", volume_quality, "VOLUME_MISSING"),
        ("PALLET", pallet_quality, "PALLET_CONFIGURATION_MISSING"),
    ):
        if status == "MISSING":
            issue_codes.append(missing_code)
        elif status == "INVALID":
            issue_codes.append(f"{axis}_INVALID")
    if not source_present:
        issue_codes.append("SOURCE_LOGISTICS_MISSING")

    attributes = dict(row.get("atributos_adicionales") or {})
    if source_present:
        attributes.update(
            {
                "source_origin": row.get("fuente_origen"),
                "source_input_checksum": row.get("source_input_checksum"),
            }
        )

    normalized = {
        "codigo_articulo": int(row["codigo_articulo"]),
        "base_unit": base_unit,
        "units_per_package": units_per_package,
        "packages_per_pallet": packages_per_pallet,
        "unit_weight_kg": unit_weight_kg,
        "unit_volume_m3": unit_volume_m3,
        "source_logistics_id": row.get("articulo_logistica_id"),
        "supplier_code": row.get("c_proveedor"),
        "logistics_configuration_code": row.get("c_configuracion_logistica"),
        "source_valid_from": row.get("f_vigencia_desde"),
        "sells_by_weight": sells_by_weight,
        "package_uom": row.get("c_tipo_bulto"),
        "unit_gtin": row.get("c_gtin_unidad"),
        "package_gtin": row.get("c_gtin_bulto"),
        "source_reference": row.get("referencia_origen"),
        "unit_net_weight_kg": unit_net_weight_kg,
        "unit_gross_weight_kg": unit_gross_weight_kg,
        "package_gross_weight_kg": package_gross_weight_kg,
        "weight_basis": weight_basis,
        "package_length_cm": _positive(row.get("q_largo_bulto_cm")),
        "package_width_cm": _positive(row.get("q_ancho_bulto_cm")),
        "package_height_cm": _positive(row.get("q_alto_bulto_cm")),
        "package_volume_m3": _positive(row.get("q_volumen_bulto_m3")),
        "volume_method": row.get("c_metodo_volumen"),
        "packages_per_layer": row.get("q_bultos_por_capa"),
        "layers_per_pallet": row.get("q_capas_por_pallet"),
        "units_per_pallet": _positive(row.get("q_unidades_por_pallet")),
        "pallet_type": row.get("c_tipo_pallet"),
        "pallet_length_cm": _positive(row.get("q_largo_pallet_cm")),
        "pallet_width_cm": _positive(row.get("q_ancho_pallet_cm")),
        "loaded_pallet_height_cm": _positive(row.get("q_alto_pallet_cargado_cm")),
        "pallet_gross_weight_kg": _positive(row.get("q_peso_bruto_pallet_kg")),
        "stackable": row.get("m_apilable"),
        "max_stack_levels": row.get("q_max_niveles_apilado"),
        "fragile": row.get("m_fragil"),
        "hazardous": row.get("m_peligroso"),
        "temperature_zone": row.get("c_zona_temperatura"),
        "temperature_min_c": _decimal(row.get("q_temperatura_min_c")),
        "temperature_max_c": _decimal(row.get("q_temperatura_max_c")),
        "orientation_code": row.get("c_orientacion"),
        "packaging_quality_status": packaging_quality,
        "weight_quality_status": weight_quality,
        "volume_quality_status": volume_quality,
        "pallet_quality_status": pallet_quality,
        "quality_issue_codes": sorted(issue_codes),
        "verified_at": None,
        "verified_by": None,
        "attributes": attributes,
        "quality_status": quality_status,
    }
    normalized["input_checksum"] = logistics_row_checksum(normalized)
    return normalized


def logistics_row_checksum(row: Mapping[str, Any]) -> str:
    values = []
    for column in LOGISTICS_COLUMNS:
        value = row.get(column)
        if isinstance(value, Decimal) or isinstance(value, float):
            values.append(_canonical_number(value))
        elif isinstance(value, (dict, list, tuple, bool)):
            values.append(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")))
        elif isinstance(value, (date, datetime)):
            values.append(value.isoformat())
        elif value is None:
            values.append("")
        else:
            values.append(str(value))
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def logistics_checksum(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: int(item["codigo_articulo"])):
        digest.update(logistics_row_checksum(row).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _chunks(rows: Sequence[Mapping[str, Any]], size: int = 2_000):
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def _json(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _read_logistics_source(
    engine: Engine,
    scope_version_uuid: UUID,
    origin_cd: int,
) -> tuple[list[dict[str, Any]], datetime, int]:
    del origin_cd  # La fuente canonica es por articulo, no por sucursal/CD.
    query = text(
        """
        WITH scope_articles AS (
            SELECT codigo_articulo
            FROM datamart.dm_pdd_scope_article
            WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
        )
        SELECT
            s.codigo_articulo,
            l.c_articulo AS source_codigo_articulo,
            l.articulo_logistica_id,
            l.c_proveedor,
            l.c_configuracion_logistica,
            l.c_unidad_base,
            l.m_vende_por_peso,
            l.c_gtin_unidad,
            l.c_tipo_bulto,
            l.c_gtin_bulto,
            l.q_unidades_por_bulto,
            l.q_peso_neto_unitario_kg,
            l.q_peso_bruto_unitario_kg,
            l.q_peso_bruto_bulto_kg,
            l.q_largo_bulto_cm,
            l.q_ancho_bulto_cm,
            l.q_alto_bulto_cm,
            l.q_volumen_bulto_m3,
            l.q_volumen_unitario_m3,
            l.c_metodo_volumen,
            l.q_bultos_por_capa,
            l.q_capas_por_pallet,
            l.q_bultos_por_pallet,
            l.q_unidades_por_pallet,
            l.c_tipo_pallet,
            l.q_largo_pallet_cm,
            l.q_ancho_pallet_cm,
            l.q_alto_pallet_cargado_cm,
            l.q_peso_bruto_pallet_kg,
            l.m_apilable,
            l.q_max_niveles_apilado,
            l.m_fragil,
            l.m_peligroso,
            l.c_zona_temperatura,
            l.q_temperatura_min_c,
            l.q_temperatura_max_c,
            l.c_orientacion,
            l.c_calidad_embalaje,
            l.c_calidad_peso,
            l.c_calidad_volumen,
            l.c_calidad_pallet,
            l.f_vigencia_desde,
            l.fuente_origen,
            l.referencia_origen,
            l.fecha_extraccion,
            l.input_checksum AS source_input_checksum,
            l.atributos_adicionales
        FROM scope_articles AS s
        LEFT JOIN src.v_base_articulos_logistica_actual AS l
          ON l.c_articulo = s.codigo_articulo
        ORDER BY s.codigo_articulo
        """
    )
    with engine.connect() as connection:
        scope = connection.execute(
            text(
                """
                SELECT article_count, source_as_of_ts
                FROM datamart.dm_pdd_scope_version
                WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                """
            ),
            {"scope_version_uuid": scope_version_uuid},
        ).mappings().one_or_none()
        if scope is None:
            raise RuntimeError("La version de scope no existe en diarco_data")
        raw_rows = [
            dict(row)
            for row in connection.execute(
                query,
                {"scope_version_uuid": scope_version_uuid},
            ).mappings()
        ]
    if len(raw_rows) != scope["article_count"]:
        raise RuntimeError(
            "La extraccion logistica no cubre el scope congelado: "
            f"filas={len(raw_rows)}, scope={scope['article_count']}"
        )
    source_timestamps = [
        timestamp
        for row in raw_rows
        for timestamp in (row.get("fecha_extraccion"), row.get("f_vigencia_desde"))
        if timestamp is not None
    ]
    source_as_of_ts = max(source_timestamps) if source_timestamps else scope["source_as_of_ts"]
    if source_as_of_ts is None:
        raise RuntimeError("No se pudo determinar source_as_of_ts de articulos logistica")
    return [normalize_logistics_row(row) for row in raw_rows], source_as_of_ts, scope["article_count"]


def publish_item_logistics(
    source_engine: Engine,
    source_settings: Settings,
    target_engine: Engine,
    target_settings: OperationalSettings,
    business_date: date,
    scope_version_uuid: UUID,
    created_by: str,
    calculation_run_uuid: UUID | None = None,
) -> LogisticsPublicationResult:
    if not created_by.strip():
        raise ValueError("created_by es obligatorio")
    run_uuid = calculation_run_uuid or uuid4()
    rows, source_as_of_ts, expected_rows = _read_logistics_source(
        source_engine,
        scope_version_uuid,
        source_settings.origin_cd,
    )
    source_checksum = logistics_checksum(rows)
    quality_counts = dict(Counter(row["quality_status"] for row in rows))

    with transactional_connection(target_engine, target_settings) as target:
        target.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('pdd.publish.item_logistics'))")
        )
        missing = target.execute(
            text(
                """
                SELECT array_agg(name ORDER BY name)
                FROM unnest(ARRAY[
                    'stock_management.pdd_calculation_run',
                    'stock_management.pdd_source_snapshot',
                    'stock_management.pdd_distribution_scope_version',
                    'stock_management.pdd_distribution_scope_article',
                    'stock_management.pdd_item_logistics_snapshot'
                ]) AS required(name)
                WHERE to_regclass(name) IS NULL
                """
            )
        ).scalar_one()
        if missing:
            raise RuntimeError(f"Contrato operativo incompleto: {missing}")

        scope = target.execute(
            text(
                """
                SELECT scope_version_id, origin_cd, article_count
                FROM stock_management.pdd_distribution_scope_version
                WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                """
            ),
            {"scope_version_uuid": scope_version_uuid},
        ).mappings().one_or_none()
        if scope is None:
            raise RuntimeError(
                "El scope debe publicarse primero en stock_management"
            )
        if scope["origin_cd"] != source_settings.origin_cd:
            raise RuntimeError("El origen del scope operativo no coincide con CD41")
        if scope["article_count"] != expected_rows:
            raise RuntimeError("El scope analitico y el operativo tienen distinta cardinalidad")
        target_articles = {
            row[0]
            for row in target.execute(
                text(
                    """
                    SELECT codigo_articulo
                    FROM stock_management.pdd_distribution_scope_article
                    WHERE scope_version_id = :scope_version_id
                    """
                ),
                {"scope_version_id": scope["scope_version_id"]},
            )
        }
        source_articles = {row["codigo_articulo"] for row in rows}
        if target_articles != source_articles:
            raise RuntimeError(
                "La membresia de articulos del scope analitico y operativo difiere"
            )

        existing = target.execute(
            text(
                """
                SELECT r.calculation_run_id, r.business_date, r.status,
                       r.input_checksum, count(l.item_logistics_snapshot_id) AS rows
                FROM stock_management.pdd_calculation_run AS r
                LEFT JOIN stock_management.pdd_item_logistics_snapshot AS l
                  ON l.calculation_run_id = r.calculation_run_id
                WHERE r.calculation_run_uuid = CAST(:run_uuid AS uuid)
                GROUP BY r.calculation_run_id
                """
            ),
            {"run_uuid": run_uuid},
        ).mappings().one_or_none()
        if existing is not None:
            if (
                existing["business_date"] != business_date
                or existing["status"] != "SUCCEEDED"
                or existing["input_checksum"] != source_checksum
                or existing["rows"] != len(rows)
            ):
                raise RuntimeError("Existe una carga logistica incompatible para la corrida")
            reused = True
        else:
            reused = False
            attempt_no = target.execute(
                text(
                    """
                    SELECT COALESCE(max(attempt_no), 0) + 1
                    FROM stock_management.pdd_calculation_run
                    WHERE run_type = 'DATA_PREP' AND business_date = :business_date
                      AND scope_type = 'CD' AND scope_id = :scope_id
                    """
                ),
                {
                    "business_date": business_date,
                    "scope_id": str(source_settings.origin_cd),
                },
            ).scalar_one()
            calculation_run_id = target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_calculation_run (
                        calculation_run_uuid, run_type, business_date, cutoff_date,
                        scope_type, scope_id, attempt_no, scope_version_id,
                        formula_version, status, started_at, created_by,
                        input_row_count, output_row_count, warning_count,
                        error_count, input_checksum, summary
                    ) VALUES (
                        CAST(:run_uuid AS uuid), 'DATA_PREP', :business_date,
                        :cutoff_date, 'CD', :scope_id, :attempt_no,
                        :scope_version_id, 'ITEM_LOGISTICS_V2', 'RUNNING',
                        clock_timestamp(), :created_by, :row_count, :row_count,
                        :warning_count, 0, :checksum, CAST(:summary AS jsonb)
                    ) RETURNING calculation_run_id
                    """
                ),
                {
                    "run_uuid": run_uuid,
                    "business_date": business_date,
                    "cutoff_date": business_date - timedelta(days=1),
                    "scope_id": str(source_settings.origin_cd),
                    "attempt_no": attempt_no,
                    "scope_version_id": scope["scope_version_id"],
                    "created_by": created_by.strip(),
                    "row_count": len(rows),
                    "warning_count": sum(
                        count
                        for status, count in quality_counts.items()
                        if status != "COMPLETE"
                    ),
                    "checksum": source_checksum,
                    "summary": _json(
                        {
                            "entity": "pdd_item_logistics_snapshot",
                            "scope_version_uuid": str(scope_version_uuid),
                            "quality_counts": quality_counts,
                            "canonical_source": "src.v_base_articulos_logistica_actual",
                            "formula_version": "ITEM_LOGISTICS_V2",
                        }
                    ),
                },
            ).scalar_one()
            source_snapshot_id = target.execute(
                text(
                    """
                    INSERT INTO stock_management.pdd_source_snapshot (
                        calculation_run_id, source_code, source_database,
                        physical_relation, is_required, as_of_ts, row_count,
                        checksum, status, detail
                    ) VALUES (
                        :calculation_run_id, 'PRODUCT_LOGISTICS', :source_database,
                        'src.v_base_articulos_logistica_actual', true, :as_of_ts,
                        :row_count, :checksum, 'VALID', CAST(:detail AS jsonb)
                    ) RETURNING source_snapshot_id
                    """
                ),
                {
                    "calculation_run_id": calculation_run_id,
                    "source_database": source_settings.pg_database,
                    "as_of_ts": source_as_of_ts,
                    "row_count": len(rows),
                    "checksum": source_checksum,
                    "detail": _json(
                        {
                            "scope_version_uuid": str(scope_version_uuid),
                            "source_selector": {
                                "current": True,
                                "active": True,
                                "default_configuration": True,
                            },
                            "canonical_columns": LOGISTICS_COLUMNS,
                        }
                    ),
                },
            ).scalar_one()
            insert_sql = text(
                """
                INSERT INTO stock_management.pdd_item_logistics_snapshot (
                    calculation_run_id, origin_cd, codigo_articulo, base_unit,
                    units_per_package, packages_per_pallet, unit_weight_kg,
                    unit_volume_m3, source_snapshot_id, quality_status,
                    source_as_of_ts, input_checksum,
                    source_logistics_id, supplier_code,
                    logistics_configuration_code, source_valid_from,
                    sells_by_weight, package_uom, unit_gtin, package_gtin,
                    source_reference, unit_net_weight_kg, unit_gross_weight_kg,
                    package_gross_weight_kg, weight_basis, package_length_cm,
                    package_width_cm, package_height_cm, package_volume_m3,
                    volume_method, packages_per_layer, layers_per_pallet,
                    units_per_pallet, pallet_type, pallet_length_cm,
                    pallet_width_cm, loaded_pallet_height_cm,
                    pallet_gross_weight_kg, stackable, max_stack_levels,
                    fragile, hazardous, temperature_zone, temperature_min_c,
                    temperature_max_c, orientation_code,
                    packaging_quality_status, weight_quality_status,
                    volume_quality_status, pallet_quality_status,
                    quality_issue_codes, verified_at, verified_by, attributes
                ) VALUES (
                    :calculation_run_id, :origin_cd, :codigo_articulo, :base_unit,
                    :units_per_package, :packages_per_pallet, :unit_weight_kg,
                    :unit_volume_m3, :source_snapshot_id, :quality_status,
                    :source_as_of_ts, :input_checksum,
                    :source_logistics_id, :supplier_code,
                    :logistics_configuration_code, :source_valid_from,
                    :sells_by_weight, :package_uom, :unit_gtin, :package_gtin,
                    :source_reference, :unit_net_weight_kg, :unit_gross_weight_kg,
                    :package_gross_weight_kg, :weight_basis, :package_length_cm,
                    :package_width_cm, :package_height_cm, :package_volume_m3,
                    :volume_method, :packages_per_layer, :layers_per_pallet,
                    :units_per_pallet, :pallet_type, :pallet_length_cm,
                    :pallet_width_cm, :loaded_pallet_height_cm,
                    :pallet_gross_weight_kg, :stackable, :max_stack_levels,
                    :fragile, :hazardous, :temperature_zone, :temperature_min_c,
                    :temperature_max_c, :orientation_code,
                    :packaging_quality_status, :weight_quality_status,
                    :volume_quality_status, :pallet_quality_status,
                    :quality_issue_codes, :verified_at, :verified_by,
                    CAST(:attributes AS jsonb)
                )
                """
            )
            for chunk in _chunks(rows):
                target.execute(
                    insert_sql,
                    [
                        {
                            **row,
                            "calculation_run_id": calculation_run_id,
                            "origin_cd": source_settings.origin_cd,
                            "source_snapshot_id": source_snapshot_id,
                            "source_as_of_ts": source_as_of_ts,
                            "attributes": _json(row["attributes"]),
                        }
                        for row in chunk
                    ],
                )
            persisted = target.execute(
                text(
                    """
                    SELECT codigo_articulo, base_unit, units_per_package,
                           packages_per_pallet, unit_weight_kg, unit_volume_m3,
                           source_logistics_id, supplier_code,
                           logistics_configuration_code, source_valid_from,
                           sells_by_weight, package_uom, unit_gtin, package_gtin,
                           source_reference, unit_net_weight_kg,
                           unit_gross_weight_kg, package_gross_weight_kg,
                           weight_basis, package_length_cm, package_width_cm,
                           package_height_cm, package_volume_m3, volume_method,
                           packages_per_layer, layers_per_pallet,
                           units_per_pallet, pallet_type, pallet_length_cm,
                           pallet_width_cm, loaded_pallet_height_cm,
                           pallet_gross_weight_kg, stackable, max_stack_levels,
                           fragile, hazardous, temperature_zone,
                           temperature_min_c, temperature_max_c,
                           orientation_code, packaging_quality_status,
                           weight_quality_status, volume_quality_status,
                           pallet_quality_status, quality_issue_codes,
                           verified_at, verified_by, attributes,
                           quality_status, input_checksum
                    FROM stock_management.pdd_item_logistics_snapshot
                    WHERE calculation_run_id = :calculation_run_id
                    ORDER BY codigo_articulo
                    """
                ),
                {"calculation_run_id": calculation_run_id},
            ).mappings().all()
            if len(persisted) != len(rows) or logistics_checksum(persisted) != source_checksum:
                raise RuntimeError("La carga logistica persistida no coincide con la fuente")
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_calculation_run
                    SET is_current = false
                    WHERE run_type = 'DATA_PREP' AND business_date = :business_date
                      AND scope_type = 'CD' AND scope_id = :scope_id
                      AND calculation_run_id <> :calculation_run_id
                    """
                ),
                {
                    "business_date": business_date,
                    "scope_id": str(source_settings.origin_cd),
                    "calculation_run_id": calculation_run_id,
                },
            )
            target.execute(
                text(
                    """
                    UPDATE stock_management.pdd_calculation_run
                    SET status = 'SUCCEEDED', is_current = true,
                        finished_at = clock_timestamp(), output_checksum = :checksum
                    WHERE calculation_run_id = :calculation_run_id
                    """
                ),
                {"checksum": source_checksum, "calculation_run_id": calculation_run_id},
            )

    return LogisticsPublicationResult(
        calculation_run_uuid=run_uuid,
        business_date=business_date,
        scope_version_uuid=scope_version_uuid,
        source_as_of_ts=source_as_of_ts,
        source_rows=len(rows),
        published_rows=len(rows),
        quality_counts=quality_counts,
        source_checksum=source_checksum,
        target_database=target_settings.pg_database,
        reused_publication=reused,
    )


def inspect_stock_readiness(
    source_engine: Engine,
    scope_version_uuid: UUID,
    expected_through: date,
    origin_cd: int = 41,
) -> StockReadinessResult:
    with source_engine.connect() as connection:
        result = dict(connection.execute(
            text(
                """
                WITH scope_pairs AS (
                    SELECT codigo_articulo, destination_branch AS sucursal
                    FROM datamart.dm_pdd_scope_pair
                    WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                ),
                scope_articles AS (
                    SELECT codigo_articulo
                    FROM datamart.dm_pdd_scope_article
                    WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                ),
                excluded_branches AS (
                    SELECT DISTINCT c_sucu_empr::integer AS sucursal
                    FROM src.sucursales_excluidas
                    WHERE c_sucu_empr IS NOT NULL
                ),
                latest AS (
                    SELECT max(fecha_stock::date) AS stock_date,
                           max(fecha_extraccion) AS source_as_of_ts
                    FROM src.base_stock_sucursal
                ),
                stock_ranked AS (
                    SELECT s.codigo_articulo, s.codigo_sucursal,
                           s.stock, s.pedido_pendiente, s.transito_pendiente,
                           s.transfer_pendiente,
                           count(*) OVER (
                               PARTITION BY s.codigo_articulo, s.codigo_sucursal
                           ) AS pair_rows,
                           row_number() OVER (
                               PARTITION BY s.codigo_articulo, s.codigo_sucursal
                               ORDER BY s.fecha_extraccion DESC NULLS LAST
                           ) AS recency_rank
                    FROM src.base_stock_sucursal AS s
                    CROSS JOIN latest AS l
                    WHERE s.fecha_stock::date = l.stock_date
                ),
                stock_rows AS (
                    SELECT *
                    FROM stock_ranked
                    WHERE recency_rank = 1
                )
                SELECT
                    l.stock_date,
                    l.source_as_of_ts,
                    count(*) AS scope_pairs,
                    count(s.codigo_articulo) AS covered_pairs,
                    count(*) FILTER (WHERE s.codigo_articulo IS NULL) AS missing_pairs,
                    count(*) FILTER (
                        WHERE excluded.sucursal IS NOT NULL
                    ) AS excluded_branch_pairs,
                    count(*) FILTER (
                        WHERE s.codigo_articulo IS NULL
                          AND excluded.sucursal IS NULL
                    ) AS unexplained_missing_pairs,
                    count(DISTINCT excluded.sucursal) AS excluded_branch_count,
                    coalesce(
                        array_agg(DISTINCT excluded.sucursal ORDER BY excluded.sucursal)
                            FILTER (WHERE excluded.sucursal IS NOT NULL),
                        ARRAY[]::integer[]
                    ) AS excluded_branches,
                    count(*) FILTER (WHERE s.pair_rows > 1) AS duplicate_pairs,
                    count(*) FILTER (
                        WHERE s.codigo_articulo IS NOT NULL AND s.stock IS NULL
                    ) AS null_physical_stock,
                    (SELECT count(*) FROM scope_articles) AS scope_articles,
                    (SELECT count(*)
                     FROM scope_articles AS a
                     JOIN stock_rows AS cd
                       ON cd.codigo_articulo = a.codigo_articulo
                      AND cd.codigo_sucursal = :origin_cd
                    ) AS covered_cd_articles,
                    (SELECT count(*)
                     FROM scope_articles AS a
                     LEFT JOIN stock_rows AS cd
                       ON cd.codigo_articulo = a.codigo_articulo
                      AND cd.codigo_sucursal = :origin_cd
                     WHERE cd.codigo_articulo IS NULL
                    ) AS missing_cd_articles,
                    (SELECT count(*)
                     FROM scope_articles AS a
                     JOIN stock_rows AS cd
                       ON cd.codigo_articulo = a.codigo_articulo
                      AND cd.codigo_sucursal = :origin_cd
                     WHERE cd.pair_rows > 1
                    ) AS duplicate_cd_articles,
                    (SELECT count(*)
                     FROM scope_articles AS a
                     JOIN stock_rows AS cd
                       ON cd.codigo_articulo = a.codigo_articulo
                      AND cd.codigo_sucursal = :origin_cd
                     WHERE cd.stock IS NULL
                    ) AS null_cd_physical_stock,
                    count(*) FILTER (WHERE s.pedido_pendiente < 0) AS negative_purchase_orders,
                    count(*) FILTER (WHERE s.transito_pendiente < 0) AS negative_in_transit,
                    count(*) FILTER (WHERE s.transfer_pendiente > 0) AS transfer_positive,
                    count(*) FILTER (WHERE s.transfer_pendiente < 0) AS transfer_negative
                FROM scope_pairs AS p
                CROSS JOIN latest AS l
                LEFT JOIN stock_rows AS s
                  ON s.codigo_articulo = p.codigo_articulo
                 AND s.codigo_sucursal = p.sucursal
                LEFT JOIN excluded_branches AS excluded
                  ON excluded.sucursal = p.sucursal
                GROUP BY l.stock_date, l.source_as_of_ts
                """
            ),
            {
                "scope_version_uuid": scope_version_uuid,
                "origin_cd": origin_cd,
            },
        ).mappings().one())
        open_po = connection.execute(
            text(
                """
                WITH scope_pairs AS (
                    SELECT codigo_articulo, destination_branch AS destino
                    FROM datamart.dm_pdd_scope_pair
                    WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                ),
                scope_articles AS (
                    SELECT codigo_articulo
                    FROM datamart.dm_pdd_scope_article
                    WHERE scope_version_uuid = CAST(:scope_version_uuid AS uuid)
                ),
                relevant AS (
                    SELECT codigo_articulo, destino FROM scope_pairs
                    UNION
                    SELECT codigo_articulo, :origin_cd FROM scope_articles
                )
                SELECT
                    coalesce(
                        max(o.fecha_extraccion),
                        (SELECT max(fecha_extraccion)
                         FROM src.mv_base_oc_pendientes)
                    ) AS open_po_as_of_ts,
                    count(*) FILTER (WHERE o.pendientes > 0) AS positive_lines,
                    count(*) FILTER (WHERE o.pendientes < 0) AS negative_lines,
                    count(DISTINCT (o.c_articulo, o.c_sucu_destino)) FILTER (
                        WHERE o.pendientes > 0 AND o.c_sucu_destino <> 41
                    ) AS branch_pairs_with_open_po,
                    count(DISTINCT o.c_articulo) FILTER (
                        WHERE o.pendientes > 0 AND o.c_sucu_destino = 41
                    ) AS cd_articles_with_open_po
                FROM relevant AS r
                LEFT JOIN src.mv_base_oc_pendientes AS o
                  ON o.c_articulo = r.codigo_articulo
                 AND o.c_sucu_destino = r.destino
                """
            ),
            {
                "scope_version_uuid": scope_version_uuid,
                "origin_cd": origin_cd,
            },
        ).mappings().one()
        result.update(open_po)
    blockers = _stock_readiness_blockers(result, expected_through)

    return StockReadinessResult(
        scope_version_uuid=scope_version_uuid,
        expected_through=expected_through,
        stock_date=result["stock_date"],
        source_as_of_ts=result["source_as_of_ts"],
        scope_pairs=result["scope_pairs"],
        covered_pairs=result["covered_pairs"],
        missing_pairs=result["missing_pairs"],
        excluded_branch_pairs=result["excluded_branch_pairs"],
        unexplained_missing_pairs=result["unexplained_missing_pairs"],
        excluded_branch_count=result["excluded_branch_count"],
        excluded_branches=tuple(result["excluded_branches"]),
        duplicate_pairs=result["duplicate_pairs"],
        null_physical_stock=result["null_physical_stock"],
        scope_articles=result["scope_articles"],
        covered_cd_articles=result["covered_cd_articles"],
        missing_cd_articles=result["missing_cd_articles"],
        duplicate_cd_articles=result["duplicate_cd_articles"],
        null_cd_physical_stock=result["null_cd_physical_stock"],
        negative_purchase_orders=result["negative_purchase_orders"],
        negative_in_transit=result["negative_in_transit"],
        transfer_positive=result["transfer_positive"],
        transfer_negative=result["transfer_negative"],
        open_po_as_of_ts=result["open_po_as_of_ts"],
        open_po_positive_lines=result["positive_lines"],
        open_po_excluded_negative_lines=result["negative_lines"],
        branch_pairs_with_open_po=result["branch_pairs_with_open_po"],
        cd_articles_with_open_po=result["cd_articles_with_open_po"],
        status="READY" if not blockers else "BLOCKED",
        blockers=tuple(blockers),
        mapping={
            "physical_stock": "stock",
            "direct_po_inbound": (
                "SUM(src.mv_base_oc_pendientes.pendientes) BY article/branch "
                "WHERE pendientes > 0"
            ),
            "cd_open_po": (
                "SUM(src.mv_base_oc_pendientes.pendientes) BY article/CD41 "
                "WHERE pendientes > 0"
            ),
            "pedido_pendiente": "LEGACY_RECONCILIATION_ONLY_NOT_CALCULATED",
            "cd_in_transit": "GREATEST(transito_pendiente, 0)",
            "transfer_pendiente": "UNMAPPED_PENDING_SEMANTIC_CONFIRMATION",
        },
    )


def _stock_readiness_blockers(
    result: Mapping[str, Any],
    expected_through: date,
) -> list[str]:
    blockers: list[str] = []
    if result["scope_pairs"] == 0:
        blockers.append("EMPTY_OR_UNKNOWN_SCOPE")
    if result["stock_date"] is None or result["stock_date"] < expected_through:
        blockers.append("STOCK_SOURCE_STALE")
    if result["excluded_branch_pairs"]:
        blockers.append("SCOPE_CONTAINS_EXCLUDED_BRANCHES")
    if result["unexplained_missing_pairs"]:
        blockers.append("SCOPE_PAIRS_WITHOUT_STOCK")
    if result["duplicate_pairs"]:
        blockers.append("DUPLICATE_STOCK_PAIRS")
    if result["null_physical_stock"]:
        blockers.append("NULL_PHYSICAL_STOCK")
    if result.get("missing_cd_articles", 0):
        blockers.append("SCOPE_CD_ARTICLES_WITHOUT_STOCK")
    if result.get("duplicate_cd_articles", 0):
        blockers.append("DUPLICATE_CD_STOCK_ARTICLES")
    if result.get("null_cd_physical_stock", 0):
        blockers.append("NULL_CD_PHYSICAL_STOCK")
    open_po_as_of_ts = result.get("open_po_as_of_ts")
    if open_po_as_of_ts is None:
        blockers.append("OPEN_PURCHASE_ORDERS_MISSING")
    elif open_po_as_of_ts.date() < expected_through:
        blockers.append("OPEN_PURCHASE_ORDERS_STALE")
    if result["negative_in_transit"]:
        blockers.append("NEGATIVE_IN_TRANSIT")
    return blockers
