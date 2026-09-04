"""Read-only report payload contracts; domain modules own all metric calculation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from packages.advertising.contracts import AdvertisingReadModel
from packages.finance.contracts import FinancialResult
from packages.operational.contracts import OperationalDailyReadModel


class ReportMetric(BaseModel):
    """Already-calculated metric, rendered without recomputation."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    owner: str = Field(min_length=1, max_length=100)
    value: Decimal | None = None
    status: str = Field(min_length=1, max_length=100)

    @field_validator("value", mode="before")
    @classmethod
    def reject_float_money(cls, value: object) -> object:
        if isinstance(value, float):
            raise ValueError("report metric values must not be float")
        return value


class ReportPayload(BaseModel):
    """Single immutable input to report renderers, with no filesystem dependencies."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = Field(default="report-payload-v1", frozen=True)
    operational_date: date
    operational: OperationalDailyReadModel
    financial: FinancialResult | None = None
    advertising: AdvertisingReadModel | None = None
    metrics: tuple[ReportMetric, ...]
    diagnostics: tuple[str, ...] = ()
