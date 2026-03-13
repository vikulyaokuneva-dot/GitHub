from __future__ import annotations

from typing import Any, Iterable, List

from .models import DistributionCoefficients


WB_IRP_EFFECTIVE_DATE_DEFAULT = '2026-03-23'


COEFFICIENT_TABLE: List[DistributionCoefficients] = [
    DistributionCoefficients(0.00, 4.99, 2.00, 0.0250),
    DistributionCoefficients(5.00, 9.99, 1.80, 0.0245),
    DistributionCoefficients(10.00, 14.99, 1.75, 0.0235),
    DistributionCoefficients(15.00, 19.99, 1.70, 0.0230),
    DistributionCoefficients(20.00, 24.99, 1.60, 0.0225),
    DistributionCoefficients(25.00, 29.99, 1.55, 0.0220),
    DistributionCoefficients(30.00, 34.99, 1.50, 0.0215),
    DistributionCoefficients(35.00, 39.99, 1.40, 0.0210),
    DistributionCoefficients(40.00, 44.99, 1.30, 0.0210),
    DistributionCoefficients(45.00, 49.99, 1.20, 0.0205),
    DistributionCoefficients(50.00, 54.99, 1.10, 0.0205),
    DistributionCoefficients(55.00, 59.99, 1.05, 0.0200),
    DistributionCoefficients(60.00, 64.99, 1.00, 0.0000),
    DistributionCoefficients(65.00, 69.99, 1.00, 0.0000),
    DistributionCoefficients(70.00, 74.99, 1.00, 0.0000),
    DistributionCoefficients(75.00, 79.99, 0.90, 0.0000),
    DistributionCoefficients(80.00, 84.99, 0.80, 0.0000),
    DistributionCoefficients(85.00, 89.99, 0.70, 0.0000),
    DistributionCoefficients(90.00, 94.99, 0.60, 0.0000),
    DistributionCoefficients(95.00, 100.00, 0.50, 0.0000),
]


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp_share(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def iter_coefficient_table() -> Iterable[DistributionCoefficients]:
    return tuple(COEFFICIENT_TABLE)


def lookup_distribution_coefficients(localization_share: float | None) -> DistributionCoefficients:
    if localization_share is None:
        return COEFFICIENT_TABLE[0]

    share = _clamp_share(localization_share)
    for row in COEFFICIENT_TABLE:
        if row.localization_range_min <= share <= row.localization_range_max:
            return row
    return COEFFICIENT_TABLE[-1]


def resolve_effective_date(value: Any) -> str:
    text = str(value or '').strip()
    if text:
        return text
    return WB_IRP_EFFECTIVE_DATE_DEFAULT


def resolve_threshold(value: Any, default: float) -> float:
    parsed = _as_float_or_none(value)
    if parsed is None:
        return float(default)
    return float(parsed)