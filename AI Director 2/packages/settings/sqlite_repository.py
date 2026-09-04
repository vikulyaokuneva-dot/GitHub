"""SQLite storage for seller-provided financial parameters.

The repository persists declarations and rebuilds the existing domain contracts
(:class:`ProductCostProfile`, :class:`TaxRateSetting`,
:class:`PeriodFinalityConfirmation`).  It performs no financial calculation and
never invents a value for an absent setting.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Final

from packages.finance.contracts import FinancialInputState
from packages.persistence.sqlite import apply_migrations, connect
from packages.products.contracts import ProductCostProfile
from packages.tax.contracts import TaxRateBasis, TaxRateSetting
from packages.wb_core.contracts import TenantAccountScope

from .contracts import FinancialSettings, PeriodFinalityConfirmation

COST_SOURCE: Final = "seller_financial_setting"
TAX_SOURCE: Final = "seller_financial_setting"

#: A seller who states a unit cost without a date means "this item costs this".
#: The window therefore opens before any auditable period instead of silently
#: excluding the days the seller already reported.
DEFAULT_EFFECTIVE_FROM: Final = date(2000, 1, 1)


class SQLiteFinancialSettingsRepository:
    """Durable, tenant-scoped storage for COGS, tax rate, and finality claims."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        apply_migrations(database_path)

    # ------------------------------------------------------------------
    # product cost
    # ------------------------------------------------------------------

    @staticmethod
    def _cost_source_record_id(scope: TenantAccountScope, nm_id: str) -> str:
        return f"cogs:{scope.account_id}:{nm_id}"

    def _cost_from_row(self, scope: TenantAccountScope, row: tuple[object, ...]) -> ProductCostProfile:
        return ProductCostProfile(
            scope=scope,
            nm_id=str(row[0]),
            state=FinancialInputState.PROVIDED,
            unit_cogs=Decimal(str(row[1])),
            effective_from=date.fromisoformat(str(row[2])),
            source=COST_SOURCE,
            source_record_id=self._cost_source_record_id(scope, str(row[0])),
        )

    def list_product_costs(self, scope: TenantAccountScope) -> tuple[tuple[str, Decimal, str | None], ...]:
        """Return stored ``(nm_id, cogs_per_unit, seller_sku)`` declarations."""

        with connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT nm_id, cogs_per_unit, seller_sku
                FROM product_cost_settings
                WHERE tenant_id = ? AND account_id = ?
                ORDER BY nm_id
                """,
                (str(scope.tenant_id), str(scope.account_id)),
            ).fetchall()
        return tuple((str(row[0]), Decimal(str(row[1])), None if row[2] is None else str(row[2])) for row in rows)

    def get_product_cost_profiles(self, scope: TenantAccountScope) -> tuple[ProductCostProfile, ...]:
        with connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT nm_id, cogs_per_unit, effective_from
                FROM product_cost_settings
                WHERE tenant_id = ? AND account_id = ?
                ORDER BY nm_id
                """,
                (str(scope.tenant_id), str(scope.account_id)),
            ).fetchall()
        return tuple(self._cost_from_row(scope, tuple(row)) for row in rows)

    def save_product_cost(
        self,
        scope: TenantAccountScope,
        nm_id: str,
        cogs_per_unit: Decimal,
        *,
        seller_sku: str | None = None,
        effective_from: date = DEFAULT_EFFECTIVE_FROM,
        now: datetime | None = None,
    ) -> ProductCostProfile:
        """Insert or replace one unit cost; the latest declaration wins."""

        moment = now or datetime.now(timezone.utc)
        profile = ProductCostProfile(
            scope=scope,
            nm_id=nm_id,
            state=FinancialInputState.PROVIDED,
            unit_cogs=cogs_per_unit,
            effective_from=effective_from,
            source=COST_SOURCE,
            source_record_id=self._cost_source_record_id(scope, nm_id),
        )
        with connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO product_cost_settings (
                    tenant_id, account_id, nm_id, seller_sku, cogs_per_unit, effective_from, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, account_id, nm_id) DO UPDATE SET
                    seller_sku = excluded.seller_sku,
                    cogs_per_unit = excluded.cogs_per_unit,
                    effective_from = excluded.effective_from,
                    updated_at = excluded.updated_at
                """,
                (
                    str(scope.tenant_id),
                    str(scope.account_id),
                    nm_id,
                    seller_sku,
                    str(cogs_per_unit),
                    effective_from.isoformat(),
                    moment.isoformat(),
                ),
            )
        return profile

    # ------------------------------------------------------------------
    # tax rate
    # ------------------------------------------------------------------

    def get_tax_rate(self, scope: TenantAccountScope) -> TaxRateSetting | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT tax_rate_percent, tax_basis, updated_at
                FROM tax_rate_settings
                WHERE tenant_id = ? AND account_id = ?
                """,
                (str(scope.tenant_id), str(scope.account_id)),
            ).fetchone()
        if row is None:
            return None
        return TaxRateSetting(
            scope=scope,
            rate_percent=Decimal(str(row[0])),
            basis=TaxRateBasis(str(row[1])),
            source=TAX_SOURCE,
            updated_at=datetime.fromisoformat(str(row[2])),
        )

    def save_tax_rate(
        self,
        scope: TenantAccountScope,
        rate_percent: Decimal,
        *,
        basis: TaxRateBasis = TaxRateBasis.REALIZED_REVENUE,
        now: datetime | None = None,
    ) -> TaxRateSetting:
        moment = now or datetime.now(timezone.utc)
        setting = TaxRateSetting(scope=scope, rate_percent=rate_percent, basis=basis, source=TAX_SOURCE, updated_at=moment)
        with connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO tax_rate_settings (tenant_id, account_id, tax_rate_percent, tax_basis, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, account_id) DO UPDATE SET
                    tax_rate_percent = excluded.tax_rate_percent,
                    tax_basis = excluded.tax_basis,
                    updated_at = excluded.updated_at
                """,
                (str(scope.tenant_id), str(scope.account_id), str(rate_percent), basis.value, moment.isoformat()),
            )
        return setting

    # ------------------------------------------------------------------
    # period finality confirmation
    # ------------------------------------------------------------------

    def get_confirmation(self, scope: TenantAccountScope, operational_date: date) -> PeriodFinalityConfirmation | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT confirmed_at, evidence_code
                FROM period_finality_confirmations
                WHERE tenant_id = ? AND account_id = ? AND operational_date = ?
                """,
                (str(scope.tenant_id), str(scope.account_id), operational_date.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return PeriodFinalityConfirmation(
            scope=scope,
            operational_date=operational_date,
            confirmed_at=datetime.fromisoformat(str(row[0])),
            evidence_code=str(row[1]),
        )

    def save_confirmation(
        self,
        scope: TenantAccountScope,
        operational_date: date,
        *,
        now: datetime | None = None,
    ) -> PeriodFinalityConfirmation:
        moment = now or datetime.now(timezone.utc)
        with connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO period_finality_confirmations (tenant_id, account_id, operational_date, confirmed_at, evidence_code)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (tenant_id, account_id, operational_date) DO UPDATE SET
                    confirmed_at = excluded.confirmed_at,
                    evidence_code = excluded.evidence_code
                """,
                (str(scope.tenant_id), str(scope.account_id), operational_date.isoformat(), moment.isoformat(), "seller_confirmed_period"),
            )
        return PeriodFinalityConfirmation(scope=scope, operational_date=operational_date, confirmed_at=moment)

    def delete_confirmation(self, scope: TenantAccountScope, operational_date: date) -> None:
        with connect(self._database_path) as connection:
            connection.execute(
                """
                DELETE FROM period_finality_confirmations
                WHERE tenant_id = ? AND account_id = ? AND operational_date = ?
                """,
                (str(scope.tenant_id), str(scope.account_id), operational_date.isoformat()),
            )

    # ------------------------------------------------------------------
    # bundle for one audit run
    # ------------------------------------------------------------------

    def get_settings(self, scope: TenantAccountScope, operational_date: date) -> FinancialSettings:
        return FinancialSettings(
            product_costs=self.get_product_cost_profiles(scope),
            tax_rate=self.get_tax_rate(scope),
            finality_confirmation=self.get_confirmation(scope, operational_date),
        )
