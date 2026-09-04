"""HTTP-layer validation and JSON shaping for seller financial parameters.

Validation lives here so that a seller always sees a human sentence instead of
a traceback or a pydantic structure dump.  Nothing in this module calculates a
financial value: it only accepts, normalises, and reports declarations.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from packages.settings.contracts import PeriodFinalityConfirmation
from packages.tax.contracts import TaxRateSetting


class FinancialSettingsInputError(ValueError):
    """A validation problem that is safe to show to a seller verbatim."""


def parse_decimal(raw: Any, *, label: str) -> Decimal:
    """Read a money or rate value without ever routing it through float."""

    if isinstance(raw, bool) or raw is None:
        raise FinancialSettingsInputError(f"«{label}» должно быть числом")
    if isinstance(raw, float):
        raise FinancialSettingsInputError(f"«{label}» нужно передать текстом, а не числом с плавающей точкой")
    text = str(raw).strip().replace(",", ".")
    if not text:
        raise FinancialSettingsInputError(f"«{label}» должно быть числом")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise FinancialSettingsInputError(f"«{label}» должно быть числом") from None
    if not value.is_finite():
        raise FinancialSettingsInputError(f"«{label}» должно быть конечным числом")
    return value


def parse_tax_rate(raw: Any) -> Decimal:
    value = parse_decimal(raw, label="Налоговая ставка")
    if value < 0:
        raise FinancialSettingsInputError("Налоговая ставка не может быть отрицательной")
    if value > Decimal("100"):
        raise FinancialSettingsInputError("Налоговая ставка не может превышать 100 процентов")
    return value


def parse_cogs(raw: Any) -> Decimal:
    value = parse_decimal(raw, label="Себестоимость")
    if value < 0:
        raise FinancialSettingsInputError("Себестоимость не может быть отрицательной")
    return value


def parse_nm_id(raw: Any) -> str:
    if raw is None:
        raise FinancialSettingsInputError("Артикул товара не указан")
    text = str(raw).strip()
    if not text.isdigit():
        raise FinancialSettingsInputError("Артикул товара должен содержать только цифры")
    if not 1 <= len(text) <= 30:
        raise FinancialSettingsInputError("Артикул товара должен быть от 1 до 30 знаков")
    return text


def parse_optional_sku(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if len(text) > 150:
        raise FinancialSettingsInputError("Артикул продавца слишком длинный")
    return text


def settings_payload(
    *,
    operational_date: date,
    tax_rate: TaxRateSetting | None,
    product_costs: tuple[tuple[str, Decimal, str | None], ...],
    confirmation: PeriodFinalityConfirmation | None,
) -> dict[str, Any]:
    """One shape for the screen and for the API contract."""

    return {
        "operational_date": operational_date.isoformat(),
        "tax_rate": None if tax_rate is None else str(tax_rate.rate_percent),
        "tax_rate_unit": "percent",
        "tax_basis": None if tax_rate is None else tax_rate.basis.value,
        "tax_updated_at": None if tax_rate is None else tax_rate.updated_at.isoformat(),
        "finality_confirmed": confirmation is not None,
        "finality_confirmed_at": None if confirmation is None else confirmation.confirmed_at.isoformat(),
        "cogs": [
            {"sku": nm_id, "cogs_per_unit": str(value), "seller_sku": seller_sku}
            for nm_id, value, seller_sku in product_costs
        ],
    }
