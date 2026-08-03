from datetime import date

from pdd_backend.windows import build_pdvb_windows, shift_one_year_back


def test_default_windows_are_disjoint() -> None:
    windows = build_pdvb_windows(date(2026, 8, 3))
    assert windows.recent_start == date(2026, 7, 6)
    assert windows.recent_end == date(2026, 8, 2)
    assert windows.previous_start == date(2026, 6, 8)
    assert windows.previous_end == date(2026, 7, 5)
    assert windows.seasonal_start == date(2025, 7, 6)
    assert windows.seasonal_end == date(2025, 8, 2)


def test_shift_leap_day() -> None:
    assert shift_one_year_back(date(2024, 2, 29)) == date(2023, 2, 28)
