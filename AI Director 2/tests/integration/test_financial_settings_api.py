"""HTTP contract and human validation for seller financial parameters."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.accounts import AccountRegistrationService, CredentialRef, SQLiteAccountRegistrationRepository
from packages.common.settings import Settings
from packages.settings.sqlite_repository import SQLiteFinancialSettingsRepository

DAY = date(2026, 9, 2)


@pytest.fixture()
def harness(tmp_path: Path):
    database_path = tmp_path / "api.sqlite3"
    accounts = SQLiteAccountRegistrationRepository(database_path)
    service = AccountRegistrationService(accounts)
    owner = service.register_wildberries_seller(
        seller_id="settings_owner", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    other = service.register_wildberries_seller(
        seller_id="settings_other", credential_ref=CredentialRef(reference="TEST_FIXTURE_CREDENTIAL")
    )
    store = SQLiteFinancialSettingsRepository(database_path)
    client = TestClient(
        create_app(
            settings=Settings(service_name="test-api", environment="test", version="0.1.0-test"),
            account_repository=accounts,
            financial_settings_repository=store,
        )
    )
    return client, owner, other, store


def _url(account_id) -> str:
    return f"/api/accounts/{account_id}/financial-settings"


def test_settings_start_empty_and_do_not_invent_values(harness) -> None:
    client, owner, _, _ = harness

    body = client.get(_url(owner.account_id), params={"date": DAY.isoformat()}).json()

    assert body["tax_rate"] is None
    assert body["cogs"] == []
    assert body["finality_confirmed"] is False


def test_tax_rate_is_saved_and_read_back(harness) -> None:
    client, owner, _, store = harness

    response = client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "6"})

    assert response.status_code == 200
    assert response.json()["tax_rate"] == "6"
    assert response.json()["tax_rate_unit"] == "percent"
    assert response.json()["tax_basis"] == "realized_revenue"
    assert store.get_tax_rate(owner.scope).rate_percent == Decimal("6")


def test_comma_decimal_separator_is_accepted(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "6,5"})

    assert response.status_code == 200
    assert response.json()["tax_rate"] == "6.5"


def test_product_cost_is_saved_read_back_and_replaced(harness) -> None:
    client, owner, _, store = harness

    first = client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "739384273", "cogs_per_unit": "500", "seller_sku": "ART-739"})
    assert first.status_code == 200
    assert first.json()["cogs"] == [{"sku": "739384273", "cogs_per_unit": "500", "seller_sku": "ART-739"}]

    client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "739384273", "cogs_per_unit": "480.50"})
    body = client.get(_url(owner.account_id)).json()
    assert body["cogs"] == [{"sku": "739384273", "cogs_per_unit": "480.50", "seller_sku": None}]
    assert store.list_product_costs(owner.scope) == (("739384273", Decimal("480.50"), None),)


def test_negative_cogs_is_rejected_with_a_human_message(harness) -> None:
    client, owner, _, store = harness

    response = client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "1001", "cogs_per_unit": "-5"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Себестоимость не может быть отрицательной"
    assert store.list_product_costs(owner.scope) == ()


def test_non_numeric_cogs_is_rejected(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "1001", "cogs_per_unit": "пятьсот"})

    assert response.status_code == 400
    assert "Себестоимость" in response.json()["detail"]


def test_money_arriving_as_float_is_rejected(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "1001", "cogs_per_unit": 500.5})

    assert response.status_code == 400
    assert "текстом" in response.json()["detail"]


def test_negative_tax_rate_is_rejected_with_a_human_message(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "-6"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Налоговая ставка не может быть отрицательной"


def test_non_numeric_tax_rate_is_rejected(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "шесть процентов"})

    assert response.status_code == 400
    assert "Налоговая ставка" in response.json()["detail"]


def test_tax_rate_above_one_hundred_is_rejected(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "150"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Налоговая ставка не может превышать 100 процентов"


def test_a_non_numeric_sku_is_not_accepted(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "ART-1001", "cogs_per_unit": "500"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Артикул товара должен содержать только цифры"


def test_an_empty_sku_is_not_accepted(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/cogs", json={"cogs_per_unit": "500"})

    assert response.status_code == 400
    assert "Артикул" in response.json()["detail"]


def test_settings_never_leak_to_another_account(harness) -> None:
    client, owner, other, _ = harness

    client.put(f"{_url(owner.account_id)}/tax", json={"tax_rate": "6"})
    client.put(f"{_url(owner.account_id)}/cogs", json={"sku": "1001", "cogs_per_unit": "500"})

    body = client.get(_url(other.account_id)).json()
    assert body["tax_rate"] is None
    assert body["cogs"] == []


def test_unknown_account_is_reported_honestly(harness) -> None:
    client, _, _, _ = harness
    from uuid import uuid4

    assert client.get(_url(uuid4())).status_code == 404
    assert client.put(f"{_url(uuid4())}/tax", json={"tax_rate": "6"}).status_code == 404


def test_finality_confirmation_can_be_recorded_and_withdrawn(harness) -> None:
    client, owner, _, store = harness

    saved = client.put(f"{_url(owner.account_id)}/finality", json={"operational_date": DAY.isoformat(), "confirmed": True})
    assert saved.status_code == 200
    assert saved.json()["finality_confirmed"] is True
    assert store.get_confirmation(owner.scope, DAY) is not None

    withdrawn = client.put(f"{_url(owner.account_id)}/finality", json={"operational_date": DAY.isoformat(), "confirmed": False})
    assert withdrawn.json()["finality_confirmed"] is False
    assert store.get_confirmation(owner.scope, DAY) is None


def test_finality_confirmation_requires_a_date(harness) -> None:
    client, owner, _, _ = harness

    response = client.put(f"{_url(owner.account_id)}/finality", json={"confirmed": True})

    assert response.status_code == 400
    assert response.json()["detail"] == "Укажите дату аудита"
