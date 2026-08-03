from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


def shift_one_year_back(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        # 29 de febrero -> 28 de febrero.
        return value.replace(year=value.year - 1, day=28)


@dataclass(frozen=True)
class PdvbWindows:
    business_date: date
    cutoff_date: date
    recent_start: date
    recent_end: date
    previous_start: date
    previous_end: date
    seasonal_start: date
    seasonal_end: date

    @property
    def feature_start(self) -> date:
        return min(self.recent_start, self.previous_start, self.seasonal_start)


def build_pdvb_windows(
    business_date: date,
    recent_days: int = 28,
    previous_days: int = 28,
    seasonal_days: int = 28,
) -> PdvbWindows:
    if min(recent_days, previous_days, seasonal_days) <= 0:
        raise ValueError("Todas las ventanas deben tener al menos un dia")
    cutoff = business_date - timedelta(days=1)
    recent_start = cutoff - timedelta(days=recent_days - 1)
    previous_end = recent_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=previous_days - 1)
    seasonal_end = shift_one_year_back(cutoff)
    seasonal_start = seasonal_end - timedelta(days=seasonal_days - 1)
    return PdvbWindows(
        business_date=business_date,
        cutoff_date=cutoff,
        recent_start=recent_start,
        recent_end=cutoff,
        previous_start=previous_start,
        previous_end=previous_end,
        seasonal_start=seasonal_start,
        seasonal_end=seasonal_end,
    )

