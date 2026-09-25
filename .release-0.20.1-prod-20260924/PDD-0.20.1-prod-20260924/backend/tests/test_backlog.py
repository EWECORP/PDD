from datetime import date
from decimal import Decimal

import pytest

from pdd_backend.jobs.backlog import build_backlog_projection


BUSINESS_DATE = date(2026, 8, 16)


def _contribution(
    source_type: str,
    source_entity_id: int,
    open_quantity: str,
    **overrides,
) -> dict:
    open_value = Decimal(open_quantity)
    row = {
        "origin_cd": 41,
        "sucursal": 1,
        "codigo_articulo": 100,
        "c_proveedor_primario": 10,
        "source_type": source_type,
        "source_entity_id": source_entity_id,
        "source_business_date": BUSINESS_DATE,
        "contributed_quantity": open_value,
        "prepared_allocated_quantity": Decimal("0"),
        "open_quantity": open_value,
        "irq_score": Decimal("90"),
        "priority_score": Decimal("90"),
        "target_date": date(2026, 8, 20),
        "units_per_package": Decimal("6"),
        "packages_per_pallet": Decimal("10"),
        "unit_weight_kg": Decimal("0.5"),
        "unit_volume_m3": None,
        "alert_codes": [],
    }
    row.update(overrides)
    return row


def test_backlog_consolidates_d_and_s_without_losing_attribution() -> None:
    rows, allocations = build_backlog_projection(
        [
            _contribution("D", 1, "24"),
            _contribution("S", 2, "6"),
        ],
        {100: Decimal("120")},
        BUSINESS_DATE,
    )

    assert len(rows) == 1
    assert rows[0]["d_open_quantity"] == Decimal("24.000000")
    assert rows[0]["s_open_quantity"] == Decimal("6.000000")
    assert rows[0]["estimated_packages"] == Decimal("5.000000")
    assert rows[0]["estimated_pallets"] == Decimal("0.500000")
    assert rows[0]["estimated_weight_kg"] == Decimal("15.000000")
    assert rows[0]["cd_reference_stock"] == Decimal("120.000000")
    assert rows[0]["freshness_status"] == "CURRENT"
    assert [row["source_type"] for row in allocations] == ["D", "S"]
    assert [row["attribution_order"] for row in allocations] == [1, 2]


def test_attribution_order_follows_documented_ecdas_rule() -> None:
    contributions = [
        _contribution("S", 6, "1"),
        _contribution("A", 5, "1"),
        _contribution("D", 4, "2"),
        _contribution("C", 3, "3"),
        _contribution("E", 2, "4", target_date=date(2026, 8, 18)),
        _contribution(
            "E",
            1,
            "5",
            contributed_quantity=Decimal("8"),
            prepared_allocated_quantity=Decimal("3"),
            target_date=date(2026, 8, 15),
        ),
    ]

    rows, allocations = build_backlog_projection(
        contributions, {100: Decimal("20")}, BUSINESS_DATE
    )

    assert rows[0]["e_open_quantity"] == Decimal("9.000000")
    assert rows[0]["c_open_quantity"] == Decimal("3.000000")
    assert rows[0]["a_open_quantity"] == Decimal("1.000000")
    assert [row["source_type"] for row in allocations] == [
        "E", "E", "C", "D", "A", "S"
    ]
    assert allocations[0]["prepared_allocated_quantity"] == Decimal("3.000000")


def test_missing_pallet_factor_is_visible_but_does_not_hide_backlog() -> None:
    contribution = _contribution("D", 1, "12", packages_per_pallet=None)

    rows, _ = build_backlog_projection(
        [contribution], {100: Decimal("30")}, BUSINESS_DATE
    )

    assert rows[0]["freshness_status"] == "INCOMPLETE"
    assert rows[0]["estimated_packages"] == Decimal("2.000000")
    assert rows[0]["estimated_pallets"] is None
    assert "PACKAGES_PER_PALLET_MISSING" in rows[0]["alert_codes"]


def test_source_balance_must_reconcile_before_publication() -> None:
    contribution = _contribution(
        "E",
        1,
        "5",
        contributed_quantity=Decimal("8"),
        prepared_allocated_quantity=Decimal("2"),
    )

    with pytest.raises(ValueError, match="no concilia"):
        build_backlog_projection(
            [contribution], {100: Decimal("30")}, BUSINESS_DATE
        )
