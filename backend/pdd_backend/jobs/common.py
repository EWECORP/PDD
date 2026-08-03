from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class JobResult:
    job_name: str
    start_date: date
    end_date: date
    affected_rows: int
    partitions: tuple[str, ...] = ()


def validate_date_range(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("end_date no puede ser anterior a start_date")

