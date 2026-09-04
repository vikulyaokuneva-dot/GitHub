"""Persistence contract for seller-provided financial parameters."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.finance.contracts import FinancialInputState
from packages.settings.contracts import FinancialSettings
from packages.settings.sqlite_repository import DEFAULT_EFFECTIVE_FROM, SQLiteFinancialSettingsRepository
from packages.tax.contracts import TaxRateBasis

NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
DAY = date(2026, 9, 2)


def _registration(database_path: Path, seller_id: str = "settings_seller"):
    accounts = SQLiteAccountRegistrationRepository(database_path)
    return AccountRegistrationService(accounts).register_wildberries_seller(
        seller_id=seller_id, credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )


def test_absent_settings_stay_missing_and_are_never_read_as_zero(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)

    assert repository.list_product_costs(registration.scope) == ()
    assert repository.get_tax_rate(registration.scope) is None
    assert repository.get_confirmation(registration.scope, DAY) is None

    settings = repository.get_settings(registration.scope, DAY)
    assert settings == FinancialSettings.empty()
    assert settings.tax_rate is None
    assert settings.finality_confirmation is None


def test_product_cost_is_saved_read_back_and_replaced(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)

    profile = repository.save_product_cost(registration.scope, "739384273", Decimal("500.00"), seller_sku="ART-739", now=NOW)
    assert profile.state is FinancialInputState.PROVIDED
    assert profile.unit_cogs == Decimal("500.00")
    assert profile.source == "seller_financial_setting"
    assert profile.effective_from == DEFAULT_EFFECTIVE_FROM

    assert repository.list_product_costs(registration.scope) == (("739384273", Decimal("500.00"), "ART-739"),)

    repository.save_product_cost(registration.scope, "739384273", Decimal("480.50"), seller_sku="ART-739", now=NOW)
    stored = repository.list_product_costs(registration.scope)
    assert len(stored) == 1
    assert stored[0][1] == Decimal("480.50")


def test_money_survives_the_round_trip_as_decimal_text(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)
    repository.save_product_cost(registration.scope, "1001", Decimal("0.10"), now=NOW)

    with sqlite3.connect(database_path) as connection:
        stored = connection.execute("SELECT cogs_per_unit FROM product_cost_settings").fetchone()[0]
    assert isinstance(stored, str)
    assert Decimal(stored) == Decimal("0.10")


def test_product_cost_is_scoped_to_the_declaring_account(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    owner = _registration(database_path, seller_id="owner")
    other = _registration(database_path, seller_id="other")
    repository = SQLiteFinancialSettingsRepository(database_path)

    repository.save_product_cost(owner.scope, "1001", Decimal("100.00"), now=NOW)
    repository.save_tax_rate(owner.scope, Decimal("6"), now=NOW)
    repository.save_confirmation(owner.scope, DAY, now=NOW)

    assert repository.list_product_costs(other.scope) == ()
    assert repository.get_tax_rate(other.scope) is None
    assert repository.get_confirmation(other.scope, DAY) is None


def test_tax_rate_is_saved_read_back_and_replaced(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)

    setting = repository.save_tax_rate(registration.scope, Decimal("6.00"), now=NOW)
    assert setting.rate_percent == Decimal("6.00")
    assert setting.basis is TaxRateBasis.REALIZED_REVENUE

    assert repository.get_tax_rate(registration.scope) is not None
    assert repository.get_tax_rate(registration.scope).rate_percent == Decimal("6.00")

    repository.save_tax_rate(registration.scope, Decimal("7"), now=NOW)
    assert repository.get_tax_rate(registration.scope).rate_percent == Decimal("7")


def test_tax_rate_rejects_negative_and_over_100_values(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)

    with pytest.raises(ValueError, match="positive or zero"):
        repository.save_tax_rate(registration.scope, Decimal("-1"), now=NOW)
    with pytest.raises(ValueError, match="100 percent"):
        repository.save_tax_rate(registration.scope, Decimal("100.5"), now=NOW)


def test_finality_confirmation_can_be_recorded_and_withdrawn(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)

    confirmation = repository.save_confirmation(registration.scope, DAY, now=NOW)
    assert repository.get_confirmation(registration.scope, DAY) is not None

    finality = confirmation.to_financial_finality_input()
    assert finality.source == "seller_confirmation"
    assert finality.evidence_code == "seller_confirmed_period"
    assert finality.operational_date == DAY

    repository.delete_confirmation(registration.scope, DAY)
    assert repository.get_confirmation(registration.scope, DAY) is None


def test_settings_cannot_be_stored_for_an_unknown_account(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registered = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)
    from packages.wb_core.contracts import TenantAccountScope

    stranger = TenantAccountScope(tenant_id=registered.scope.tenant_id, account_id=uuid4())
    with pytest.raises(sqlite3.IntegrityError):
        repository.save_tax_rate(stranger, Decimal("6"), now=NOW)


def test_product_cost_effective_window_decides_participation(tmp_path: Path) -> None:
    database_path = tmp_path / "settings.sqlite3"
    registration = _registration(database_path)
    repository = SQLiteFinancialSettingsRepository(database_path)
    repository.save_product_cost(registration.scope, "1001", Decimal("100.00"), effective_from=date(2026, 9, 1), now=NOW)

    settings = repository.get_settings(registration.scope, DAY)
    assert [profile.nm_id for profile in settings.applicable_product_costs(DAY)] == ["1001"]
    assert settings.applicable_product_costs(date(2026, 8, 31)) == ()
