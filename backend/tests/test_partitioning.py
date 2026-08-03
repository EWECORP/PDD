from datetime import date

import pytest

from pdd_backend.partitioning import iter_months


def test_iter_months_crosses_year() -> None:
    months = list(iter_months(date(2025, 12, 15), date(2026, 2, 3)))
    assert [(m.start, m.end) for m in months] == [
        (date(2025, 12, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), date(2026, 2, 1)),
        (date(2026, 2, 1), date(2026, 3, 1)),
    ]


def test_iter_months_rejects_invalid_range() -> None:
    with pytest.raises(ValueError):
        list(iter_months(date(2026, 2, 1), date(2026, 1, 31)))

