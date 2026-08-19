from datetime import date
from decimal import Decimal
from inspect import getsource

from pdd_backend.jobs.daily_decas import (
    _read_source_stock,
    build_branch_position,
    build_need_rows,
    calculation_cutoff_date,
    calculate_irq,
    round_to_logistics,
)
from pdd_backend.operational_registry import load_operational_configuration
from uuid import UUID


def _estimate(pdvb: str = "2") -> dict:
    return {
        "origin_cd": 41,
        "sucursal": 1,
        "codigo_articulo": 100,
        "c_proveedor_primario": 10,
        "business_date": date(2026, 8, 16),
        "pdvb_estimate_id": 99,
        "pdvb_value": Decimal(pdvb),
        "status": "OK",
    }


def _source(**overrides) -> dict:
    row = {
        "stock": 3,
        "pedido_pendiente": 1,
        "direct_po_inbound": 1,
        "transito_pendiente": 2,
        "transfer_pendiente": 0,
        "dias_preparacion": 5,
        "q_dias_stock": 10,
        "q_dias_sobre_stock": 2,
    }
    row.update(overrides)
    return row


def _logistics() -> dict:
    return {
        "item_logistics_snapshot_id": 7,
        "units_per_package": Decimal("6"),
        "packages_per_pallet": Decimal("10"),
        "unit_weight_kg": Decimal("0.5"),
        "unit_volume_m3": None,
        "quality_status": "COMPLETE",
    }


def test_branch_position_applies_documented_formulas() -> None:
    row = build_branch_position(_source(), _estimate(), Decimal("15"))
    assert row["critical_stock"] == Decimal("10.000000")
    assert row["minimum_stock"] == Decimal("20.000000")
    assert row["maximum_stock"] == Decimal("20.000000")
    assert row["overstock_quantity"] == Decimal("4.000000")
    assert row["coverage_days"] == Decimal("3.000000")
    assert row["calculation_status"] == "OK"


def test_branch_position_uses_canonical_po_instead_of_legacy_stock_field() -> None:
    row = build_branch_position(
        _source(pedido_pendiente=999, direct_po_inbound=1),
        _estimate(),
        Decimal("15"),
    )
    assert row["direct_po_inbound"] == Decimal("1.000000")
    assert row["coverage_days"] == Decimal("3.000000")
    assert row["explanation"]["direct_po_source"] == "src.mv_base_oc_pendientes"
    assert row["explanation"]["legacy_pedido_pendiente_observed"] == 999


def test_missing_lead_time_uses_visible_fallback_and_warns() -> None:
    row = build_branch_position(
        _source(dias_preparacion=0), _estimate(), Decimal("15")
    )
    assert row["lead_time_days"] == Decimal("15.0000")
    assert row["calculation_status"] == "WARN"
    assert "LEAD_TIME_FALLBACK" in row["alert_codes"]
    assert row["explanation"]["lead_time_fallback_used"] is True


def test_zero_pdvb_has_position_but_zero_automatic_needs() -> None:
    branch = build_branch_position(_source(), _estimate("0"), Decimal("15"))
    needs = build_need_rows(branch, _logistics(), date(2026, 8, 16))
    assert branch["calculation_status"] == "ZERO_PDVB"
    assert len(needs) == 2
    assert all(row["calculation_status"] == "ZERO" for row in needs)
    assert all(row["open_quantity"] == 0 for row in needs)


def test_need_formulas_and_package_rounding_do_not_overlap_d_and_s() -> None:
    branch = build_branch_position(
        _source(
            stock=1,
            pedido_pendiente=0,
            direct_po_inbound=0,
            transito_pendiente=0,
        ),
        _estimate("2"),
        Decimal("15"),
    )
    demand, surplus = build_need_rows(branch, _logistics(), date(2026, 8, 16))
    assert demand["calculated_quantity"] == Decimal("19.000000")
    assert demand["rounded_quantity"] == Decimal("24.000000")
    assert surplus["calculated_quantity"] == Decimal("4.000000")
    assert surplus["rounded_quantity"] == Decimal("6.000000")
    assert demand["estimated_packages"] == Decimal("4.000000")
    assert demand["estimated_pallets"] == Decimal("0.400000")


def test_irq_and_rounding_boundaries() -> None:
    assert calculate_irq(Decimal("0"), None, Decimal("5"), Decimal("10")) == 100
    assert calculate_irq(Decimal("1"), Decimal("4"), Decimal("5"), Decimal("10")) == 90
    assert calculate_irq(Decimal("1"), Decimal("7"), Decimal("5"), Decimal("10")) == 50
    assert calculate_irq(Decimal("1"), Decimal("9"), Decimal("4"), Decimal("10")) == 25
    assert calculate_irq(Decimal("1"), Decimal("10"), Decimal("4"), Decimal("10")) == 0
    assert round_to_logistics(Decimal("13"), Decimal("6")) == Decimal("18.000000")


def test_daily_decas_cutoff_is_the_previous_closed_day() -> None:
    business_date = date(2026, 8, 16)
    cutoff_date = calculation_cutoff_date(business_date)

    assert cutoff_date == date(2026, 8, 15)
    assert cutoff_date < business_date


def test_source_stock_uses_explicit_effective_stock_date() -> None:
    source = getsource(_read_source_stock)
    assert source.count("fecha_stock::date = :stock_date") == 2
    assert "fecha_stock::date = :business_date" not in source


def test_pilot_configuration_is_versioned_and_explicit() -> None:
    manifest = load_operational_configuration(
        UUID("2f916828-c59d-4190-a795-29ac5cfc1a66")
    )
    assert manifest.status == "DRAFT"
    assert manifest.parameters["lead_time_days"]["fallback"] == 15
    assert manifest.parameters["confirmed_transfer_pending"]["status"].endswith(
        "PENDING"
    )
