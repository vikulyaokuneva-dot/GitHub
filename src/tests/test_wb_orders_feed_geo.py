from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from audit.audit_facts_builder import _build_local_orders_insights
from audit.audit_loader import parse_orders_file_with_diagnostics


def _build_orders_feed_file(path: Path) -> None:
    rows = [
        ["Все заказы", "", "", "", "", ""],
        ["Артикул продавца", "Артикул WB", "Дата оформления заказа", "Регион прибытия", "Город прибытия", "Количество заказов"],
        ["SKU-A", 405933491, "2026-04-04 15:27:07", "Центральный", "Москва", 2],
        ["SKU-B", 810239842, "2026-04-05 12:00:00", "Приволжский", "Казань", 1],
    ]
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Все заказы", index=False, header=False)
        pd.DataFrame([["Общая информация", "RUB"]]).to_excel(
            writer,
            sheet_name="Общая информация",
            index=False,
            header=False,
        )


def test_parse_orders_feed_extracts_sku_geo_orders_and_date(tmp_path: Path) -> None:
    orders_path = tmp_path / "лента заказов.xlsx"
    _build_orders_feed_file(orders_path)

    rows, diag = parse_orders_file_with_diagnostics(str(orders_path))

    assert diag.get("status") == "ok"
    assert int(diag.get("rows_scanned") or 0) >= 2
    assert int(diag.get("rows_with_geo") or 0) == 2
    assert len(rows) == 2

    first = rows[0]
    assert int(first.get("nmId") or 0) == 405933491
    assert str(first.get("region") or "") == "Центральный"
    assert int(first.get("orders") or 0) == 2
    assert str(first.get("date") or "").startswith("2026-04-04")


def test_local_orders_insights_uses_orders_feed_geo_when_available() -> None:
    orders_rows = [
        {"nmId": 405933491, "region": "Центральный", "city": "Москва", "orders": 3},
        {"nmId": 405933491, "region": "Центральный", "city": "Москва", "orders": 2},
        {"nmId": 810239842, "region": "Приволжский", "city": "Казань", "orders": 1},
    ]
    funnel_rows = [
        {"nmId": 405933491, "orderCount": 99, "region": "Уральский"},
    ]
    stocks_rows = [
        {"nmId": 405933491, "region": "Центральный", "quantityFull": 10},
        {"nmId": 810239842, "region": "Приволжский", "quantityFull": 5},
    ]

    payload = _build_local_orders_insights(
        orders_rows=orders_rows,
        funnel_rows=funnel_rows,
        stocks_rows=stocks_rows,
    )

    assert payload.get("available") is True
    diagnostics = payload.get("diagnostics") or {}
    assert diagnostics.get("orders_geo_source") == "orders_feed"
    assert int(diagnostics.get("orders_rows_scanned") or 0) == 3
    assert int(diagnostics.get("orders_rows_with_geo") or 0) == 3
    assert any((item or {}).get("region") == "Центральный" for item in (payload.get("by_region") or []))
    assert any((item or {}).get("sku") == 405933491 for item in (payload.get("orders_with_geo") or []))


def test_local_orders_insights_returns_honest_message_when_geo_missing() -> None:
    payload = _build_local_orders_insights(
        orders_rows=[],
        funnel_rows=[{"nmId": 405933491, "orderCount": 3}],
        stocks_rows=[],
    )
    assert payload.get("available") is False
    assert payload.get("message") == "нет данных по географии заказов"


def test_local_orders_insights_builds_non_local_sku_actions() -> None:
    orders_rows = [
        {
            "nmId": 111111,
            "orders": 12,
            "region": "Центральный",
            "customer_region": "Сибирский",
            "warehouse_region": "Центральный",
        },
        {
            "nmId": 111111,
            "orders": 10,
            "region": "Сибирский",
            "customer_region": "Сибирский",
            "warehouse_region": "Центральный",
        },
        {
            "nmId": 222222,
            "orders": 8,
            "region": "Центральный",
            "customer_region": "Центральный",
            "warehouse_region": "Центральный",
        },
    ]

    payload = _build_local_orders_insights(
        orders_rows=orders_rows,
        funnel_rows=[],
        stocks_rows=[],
    )

    assert payload.get("available") is True
    assert payload.get("sku_non_local_available") is True
    actions = payload.get("sku_non_local_actions") or []
    assert len(actions) == 1

    first = actions[0]
    assert int(first.get("sku") or 0) == 111111
    assert int(first.get("non_local_orders_count") or 0) == 22
    assert str(first.get("top_region") or "") == "Сибирский"
    assert "Добавить склад в Сибирский" in str(first.get("recommendation") or "")


def test_local_orders_insights_non_local_actions_require_origin_and_destination() -> None:
    orders_rows = [
        {"nmId": 111111, "orders": 3, "region": "Центральный"},
        {"nmId": 111111, "orders": 2, "region": "Сибирский"},
    ]

    payload = _build_local_orders_insights(
        orders_rows=orders_rows,
        funnel_rows=[],
        stocks_rows=[],
    )

    assert payload.get("available") is True
    assert payload.get("sku_non_local_available") is False
    assert payload.get("sku_non_local_actions") == []
