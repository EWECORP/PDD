from datetime import date, datetime
from decimal import Decimal
from inspect import getsource
from pathlib import Path

from pdd_backend.jobs.operational_inputs import (
    _stock_readiness_blockers,
    inspect_stock_readiness,
    logistics_checksum,
    normalize_logistics_row,
)


def test_logistics_normalization_maps_weight_and_packaging() -> None:
    normalized = normalize_logistics_row(
        {
            "codigo_articulo": 100,
            "source_codigo_articulo": 100,
            "articulo_logistica_id": 999,
            "c_unidad_base": "KG",
            "m_vende_por_peso": True,
            "q_unidades_por_bulto": 6,
            "q_bultos_por_pallet": 120,
            "q_unidades_por_pallet": 720,
            "q_peso_bruto_bulto_kg": Decimal("3.000"),
            "q_volumen_unitario_m3": Decimal("0.001"),
            "c_calidad_embalaje": "SOURCE",
            "c_calidad_peso": "SOURCE",
            "c_calidad_volumen": "SOURCE",
            "c_calidad_pallet": "SOURCE",
        }
    )
    assert normalized["base_unit"] == "KG"
    assert normalized["units_per_package"] == Decimal("6")
    assert normalized["packages_per_pallet"] == Decimal("120")
    assert normalized["unit_weight_kg"] == Decimal("0.500")
    assert normalized["weight_basis"] == "GROSS_PACKAGE_DERIVED"
    assert normalized["unit_volume_m3"] == Decimal("0.001")
    assert normalized["units_per_pallet"] == Decimal("720")
    assert normalized["quality_issue_codes"] == []
    assert normalized["quality_status"] == "COMPLETE"


def test_logistics_normalization_preserves_missing_and_invalid_evidence() -> None:
    missing = normalize_logistics_row(
        {
            "codigo_articulo": 101,
            "source_codigo_articulo": None,
        }
    )
    invalid = normalize_logistics_row(
        {
            "codigo_articulo": 102,
            "source_codigo_articulo": 102,
            "c_unidad_base": "UNIT",
            "m_vende_por_peso": False,
            "q_unidades_por_bulto": None,
            "q_bultos_por_pallet": None,
            "c_calidad_embalaje": "SOURCE",
            "c_calidad_peso": "MISSING",
            "c_calidad_volumen": "MISSING",
            "c_calidad_pallet": "SOURCE",
        }
    )
    assert missing["base_unit"] == "UNKNOWN"
    assert missing["quality_status"] == "MISSING"
    assert "SOURCE_LOGISTICS_MISSING" in missing["quality_issue_codes"]
    assert invalid["units_per_package"] is None
    assert invalid["packages_per_pallet"] is None
    assert invalid["quality_status"] == "INVALID"
    assert "PACKAGING_INVALID" in invalid["quality_issue_codes"]
    assert "PALLET_INVALID" in invalid["quality_issue_codes"]


def test_missing_weight_and_volume_remain_partial_without_legacy_fallback() -> None:
    normalized = normalize_logistics_row(
        {
            "codigo_articulo": 103,
            "source_codigo_articulo": 103,
            "c_unidad_base": "UNIT",
            "m_vende_por_peso": False,
            "q_unidades_por_bulto": 6,
            "q_bultos_por_pallet": 120,
            "q_peso_unit_art": 999,
            "c_calidad_embalaje": "SOURCE",
            "c_calidad_peso": "MISSING",
            "c_calidad_volumen": "MISSING",
            "c_calidad_pallet": "SOURCE",
        }
    )
    assert normalized["unit_weight_kg"] is None
    assert normalized["unit_volume_m3"] is None
    assert normalized["weight_quality_status"] == "MISSING"
    assert normalized["volume_quality_status"] == "MISSING"
    assert normalized["quality_issue_codes"] == ["VOLUME_MISSING", "WEIGHT_MISSING"]
    assert normalized["quality_status"] == "PARTIAL"


def test_logistics_checksum_recomputes_canonical_values() -> None:
    row = normalize_logistics_row(
        {
            "codigo_articulo": 100,
            "source_codigo_articulo": 100,
            "c_unidad_base": "UNIT",
            "m_vende_por_peso": False,
            "q_unidades_por_bulto": 6,
            "q_bultos_por_pallet": 120,
            "c_calidad_embalaje": "SOURCE",
            "c_calidad_peso": "MISSING",
            "c_calidad_volumen": "MISSING",
            "c_calidad_pallet": "SOURCE",
        }
    )
    changed = {**row, "packages_per_pallet": Decimal("121")}
    assert logistics_checksum([row]) != logistics_checksum([changed])


def test_logistics_publisher_uses_canonical_source_contract() -> None:
    from inspect import getsource

    from pdd_backend.jobs.operational_inputs import (
        _read_logistics_source,
        publish_item_logistics,
    )

    reader = getsource(_read_logistics_source)
    publisher = getsource(publish_item_logistics)
    assert "src.v_base_articulos_logistica_actual" in reader
    assert "src.base_productos_vigentes" not in reader
    assert "ITEM_LOGISTICS_V2" in publisher
    assert "src.v_base_articulos_logistica_actual" in publisher


def test_stock_readiness_uses_frozen_scope_physical_contract() -> None:
    source = getsource(inspect_stock_readiness)
    assert "destination_branch AS sucursal" in source
    assert "SELECT codigo_articulo, sucursal" not in source
    assert "src.sucursales_excluidas" in source
    assert "unexplained_missing_pairs" in source
    assert "covered_cd_articles" in source
    assert "missing_cd_articles" in source
    assert "src.mv_base_oc_pendientes" in source
    assert "o.pendientes > 0" in source


def test_stock_readiness_distinguishes_excluded_branch_from_missing_stock() -> None:
    result = {
        "scope_pairs": 100,
        "stock_date": date(2026, 8, 16),
        "excluded_branch_pairs": 39,
        "unexplained_missing_pairs": 0,
        "duplicate_pairs": 0,
        "null_physical_stock": 0,
        "negative_purchase_orders": 0,
        "negative_in_transit": 0,
        "open_po_as_of_ts": datetime(2026, 8, 16),
    }
    assert _stock_readiness_blockers(result, date(2026, 8, 15)) == [
        "SCOPE_CONTAINS_EXCLUDED_BRANCHES"
    ]
    result["excluded_branch_pairs"] = 0
    result["unexplained_missing_pairs"] = 1
    assert _stock_readiness_blockers(result, date(2026, 8, 15)) == [
        "SCOPE_PAIRS_WITHOUT_STOCK"
    ]


def test_stock_readiness_blocks_stale_canonical_purchase_orders() -> None:
    result = {
        "scope_pairs": 100,
        "stock_date": date(2026, 8, 16),
        "excluded_branch_pairs": 0,
        "unexplained_missing_pairs": 0,
        "duplicate_pairs": 0,
        "null_physical_stock": 0,
        "negative_purchase_orders": 0,
        "negative_in_transit": 0,
        "open_po_as_of_ts": datetime(2026, 8, 14),
    }
    assert _stock_readiness_blockers(result, date(2026, 8, 15)) == [
        "OPEN_PURCHASE_ORDERS_STALE"
    ]


def test_stock_readiness_requires_complete_cd_snapshot() -> None:
    result = {
        "scope_pairs": 100,
        "stock_date": date(2026, 8, 18),
        "excluded_branch_pairs": 0,
        "unexplained_missing_pairs": 0,
        "duplicate_pairs": 0,
        "null_physical_stock": 0,
        "missing_cd_articles": 1,
        "duplicate_cd_articles": 0,
        "null_cd_physical_stock": 0,
        "negative_in_transit": 0,
        "open_po_as_of_ts": datetime(2026, 8, 18),
    }
    assert _stock_readiness_blockers(result, date(2026, 8, 16)) == [
        "SCOPE_CD_ARTICLES_WITHOUT_STOCK"
    ]


def test_scope_snapshot_excludes_operational_branches() -> None:
    sql = (
        Path(__file__).parents[1]
        / "pdd_backend/sql/scope/prepare_scope_snapshot.sql"
    ).read_text(encoding="utf-8")
    assert "FROM src.sucursales_excluidas" in sql
    assert "pdd_scope_excluded_branches" in sql
    assert "pdd_scope_excluded_branch_pairs" in sql
    assert "excluded.destination_branch = bpv.c_sucu_empr::integer" in sql
    assert "bpv.cod_cd = '41CD'" in sql
    assert "bpv.abastecimiento = 0" in sql
    assert "c_sucu_empr < 300" not in sql
