from datetime import date
from decimal import Decimal

import pytest

from pdd_backend.backtest_metrics import (
    calculate_algo01_daily,
    calculate_croston_sba,
    calculate_error_metrics,
    classify_demand_regime,
    standardize_cumulative_actual,
)
from pdd_backend.jobs.backtest import BACKTEST_ESTIMATORS, iter_dates


def test_iter_dates_includes_both_bounds() -> None:
    assert list(iter_dates(date(2026, 8, 1), date(2026, 8, 3))) == [
        date(2026, 8, 1),
        date(2026, 8, 2),
        date(2026, 8, 3),
    ]


def test_backtest_declares_candidate_and_fair_benchmarks() -> None:
    assert BACKTEST_ESTIMATORS == (
        "PDVB_CANDIDATE",
        "MEAN_28",
        "ALGO_01_GROWTH",
        "ALGO_01_NORMALIZED",
        "OCCURRENCE_SIZE",
        "CROSTON_SBA",
        "HYBRID_EXPERIMENTAL",
    )


def test_error_metrics_and_bias_sign() -> None:
    metrics = calculate_error_metrics(
        [
            (Decimal("10"), Decimal("8")),
            (Decimal("0"), Decimal("2")),
        ]
    )
    assert metrics.mae == Decimal("2")
    assert metrics.wape == Decimal("40")
    assert metrics.bias == Decimal("0")
    assert metrics.rmse == Decimal("2.0")
    assert metrics.sample_size == 2
    assert metrics.zero_actual_count == 1


def test_algo01_growth_preserves_intentional_ten_percent_uplift() -> None:
    means = (Decimal("10"), Decimal("10"), Decimal("10"))
    assert calculate_algo01_daily(*means, normalize_available=False) == Decimal("11.0")
    assert calculate_algo01_daily(*means, normalize_available=True) == Decimal("10")


def test_wape_and_bias_are_undefined_when_all_actuals_are_zero() -> None:
    metrics = calculate_error_metrics([(Decimal("0"), Decimal("1"))])
    assert metrics.wape is None
    assert metrics.bias is None


def test_metrics_reject_empty_sample() -> None:
    with pytest.raises(ValueError, match="al menos una"):
        calculate_error_metrics([])


@pytest.mark.parametrize(
    ("nonzero_days", "adi", "cv2", "expected"),
    [
        (0, None, None, "NO_DEMAND"),
        (1, None, None, "UNCLASSIFIED"),
        (1, Decimal("3"), None, "SPARSE"),
        (10, Decimal("1"), Decimal("0.20"), "SMOOTH"),
        (10, Decimal("1"), Decimal("0.70"), "ERRATIC"),
        (10, Decimal("2"), Decimal("0.20"), "INTERMITTENT"),
        (10, Decimal("2"), Decimal("0.70"), "LUMPY"),
    ],
)
def test_classify_demand_regime(
    nonzero_days: int,
    adi: Decimal | None,
    cv2: Decimal | None,
    expected: str,
) -> None:
    assert classify_demand_regime(nonzero_days, adi, cv2) == expected


def test_croston_sba_updates_size_and_interval() -> None:
    result = calculate_croston_sba(
        [(Decimal("4"), Decimal("2")), (Decimal("8"), Decimal("4"))],
        alpha=Decimal("0.10"),
    )
    assert result == Decimal("1.90")


def test_cumulative_actual_is_scaled_only_when_coverage_is_sufficient() -> None:
    actual, coverage, valid = standardize_cumulative_actual(
        Decimal("12"), 6, 7, minimum_coverage=Decimal("0.70")
    )
    assert actual == Decimal("14")
    assert coverage == Decimal(6) / Decimal(7)
    assert valid

    _, low_coverage, low_valid = standardize_cumulative_actual(
        Decimal("4"), 2, 7, minimum_coverage=Decimal("0.70")
    )
    assert low_coverage == Decimal(2) / Decimal(7)
    assert not low_valid
