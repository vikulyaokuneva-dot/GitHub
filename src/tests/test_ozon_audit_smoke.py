from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from audit.run_audit import run_audit_mode

pytestmark = pytest.mark.ozon_audit


def _write_ozon_products_xlsx(path: Path) -> None:
    rows = [
        ["Отчет Ozon", "", "", "", "", "", "", ""],
        ["Период: 2026-04-01 - 2026-04-03", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", ""],
        ["Артикул продавца", "SKU", "Наименование товара", "Заказы", "Выручка, руб", "Просмотры", "Конверсия, %", "Цена"],
        ["OFFER-1", "SKU-1", "Товар 1", 10, 15000, 1200, 0.08, 1500],
        ["OFFER-2", "SKU-2", "Товар 2", 3, 2100, 600, 0.03, 700],
        ["Итого", "", "", 13, 17100, 1800, "", ""],
    ]
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, header=False)


def _write_cogs_csv(path: Path) -> None:
    df = pd.DataFrame(
        [
            {"seller_code": "OFFER-1", "cogs": 900},
            {"seller_code": "OFFER-2", "cogs": 950},
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def test_ozon_audit_smoke(tmp_path: Path):
    input_root = tmp_path / "input" / "ozon"
    out_dir = tmp_path / "out"

    _write_ozon_products_xlsx(input_root / "products" / "ozon_products_report.xlsx")
    _write_cogs_csv(input_root / "cogs" / "cogs.csv")

    def _fake_pdf(markdown: str, out_path: str, title: str = ""):
        Path(out_path).write_bytes(f"{title}\n{markdown}".encode("utf-8"))

    with patch("audit.run_audit.markdown_to_simple_pdf", side_effect=_fake_pdf):
        result = run_audit_mode(
            source="ozon",
            input_dir=str(input_root),
            out_dir=str(out_dir),
            period="2026-04-01_2026-04-03",
            send_email=False,
        )

    facts_path = Path(result["facts_path"])
    md_path = Path(result["md_path"])
    pdf_path = Path(result["pdf_path"])
    actions_path = Path(result["actions_path"])

    assert facts_path.exists()
    assert md_path.exists()
    assert pdf_path.exists()
    assert actions_path.exists()

    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert facts["report_type"] == "audit"
    assert facts["source"] == "ozon"
    assert "sku_profit" in facts
    assert "decision_layer" in facts
    assert "abc_analysis" in facts
    assert len((facts.get("sku_profit") or {}).get("items") or []) > 0
