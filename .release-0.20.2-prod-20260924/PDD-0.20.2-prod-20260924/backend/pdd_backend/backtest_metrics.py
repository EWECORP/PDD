from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Iterable


@dataclass(frozen=True)
class ErrorMetrics:
    mae: Decimal
    wape: Decimal | None
    bias: Decimal | None
    rmse: Decimal
    sample_size: int
    zero_actual_count: int


def classify_demand_regime(
    nonzero_days: int,
    adi: Decimal | None,
    cv2: Decimal | None,
    *,
    adi_threshold: Decimal = Decimal("1.32"),
    cv2_threshold: Decimal = Decimal("0.49"),
) -> str:
    """Clasifica la intermitencia con los umbrales ADI/CV2 configurables."""
    if nonzero_days == 0:
        return "NO_DEMAND"
    if adi is None:
        return "UNCLASSIFIED"
    if cv2 is None:
        return "SPARSE"
    if adi <= adi_threshold:
        return "SMOOTH" if cv2 <= cv2_threshold else "ERRATIC"
    return "INTERMITTENT" if cv2 <= cv2_threshold else "LUMPY"


def calculate_croston_sba(
    events: Iterable[tuple[Decimal, Decimal]],
    *,
    alpha: Decimal = Decimal("0.10"),
) -> Decimal | None:
    """Calcula Croston con correccion SBA desde pares (cantidad, intervalo)."""
    rows = list(events)
    if not rows:
        return None
    if not Decimal("0") < alpha <= Decimal("1"):
        raise ValueError("alpha debe estar en (0, 1]")

    demand_size, interval = rows[0]
    if interval <= 0:
        raise ValueError("Los intervalos deben ser positivos")
    for observed_size, observed_interval in rows[1:]:
        if observed_interval <= 0:
            raise ValueError("Los intervalos deben ser positivos")
        demand_size += alpha * (observed_size - demand_size)
        interval += alpha * (observed_interval - interval)
    return (Decimal("1") - alpha / 2) * demand_size / interval


def standardize_cumulative_actual(
    observed_eligible_units: Decimal,
    eligible_days: int,
    window_days: int,
    *,
    minimum_coverage: Decimal = Decimal("0.70"),
) -> tuple[Decimal | None, Decimal, bool]:
    """Escala lo observado a la ventana completa si la cobertura es suficiente."""
    if not Decimal("0") < minimum_coverage <= Decimal("1"):
        raise ValueError("minimum_coverage debe estar en (0, 1]")
    if window_days <= 0 or not 0 <= eligible_days <= window_days:
        raise ValueError("Dias elegibles/ventana invalidos")
    coverage = Decimal(eligible_days) / Decimal(window_days)
    is_valid = eligible_days > 0 and coverage >= minimum_coverage
    standardized = (
        observed_eligible_units * Decimal(window_days) / Decimal(eligible_days)
        if eligible_days > 0
        else None
    )
    return standardized, coverage, is_valid


def calculate_algo01_daily(
    recent_mean: Decimal | None,
    previous_mean: Decimal | None,
    seasonal_mean: Decimal | None,
    *,
    normalize_available: bool,
    recent_weight: Decimal = Decimal("0.80"),
    previous_weight: Decimal = Decimal("0.10"),
    seasonal_weight: Decimal = Decimal("0.20"),
) -> Decimal | None:
    components = (
        (recent_mean, recent_weight),
        (previous_mean, previous_weight),
        (seasonal_mean, seasonal_weight),
    )
    available = [(value, weight) for value, weight in components if value is not None]
    if not available:
        return None
    numerator = sum((value * weight for value, weight in available), Decimal("0"))
    if not normalize_available:
        return numerator
    denominator = sum((weight for _, weight in available), Decimal("0"))
    return numerator / denominator if denominator > 0 else None


def calculate_error_metrics(
    observations: Iterable[tuple[Decimal, Decimal]],
) -> ErrorMetrics:
    rows = list(observations)
    if not rows:
        raise ValueError("Se requiere al menos una observacion valida")

    actual_sum = sum((actual for actual, _ in rows), Decimal("0"))
    errors = [actual - predicted for actual, predicted in rows]
    absolute_sum = sum((abs(error) for error in errors), Decimal("0"))
    squared_sum = sum((error * error for error in errors), Decimal("0"))
    sample_size = len(rows)

    return ErrorMetrics(
        mae=absolute_sum / sample_size,
        wape=(Decimal("100") * absolute_sum / actual_sum) if actual_sum > 0 else None,
        # Convencion: BIAS positivo = subpronostico; negativo = sobrepronostico.
        bias=(Decimal("100") * sum(errors, Decimal("0")) / actual_sum)
        if actual_sum > 0
        else None,
        rmse=Decimal(str(sqrt(float(squared_sum / sample_size)))),
        sample_size=sample_size,
        zero_actual_count=sum(1 for actual, _ in rows if actual == 0),
    )
