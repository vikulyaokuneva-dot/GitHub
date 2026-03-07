from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd


def _guess_manual_file(manual_dir: str | os.PathLike) -> Optional[Path]:
    d = Path(manual_dir)
    if not d.exists():
        return None
    # Prefer newest file by mtime among supported extensions
    candidates: List[Path] = []
    for ext in (".xlsx", ".xls", ".csv", ".json"):
        candidates.extend(d.glob(f"*{ext}"))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _normalize_manual_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Normalize column names
    cols = {c: str(c).strip().lower() for c in df.columns}
    df = df.rename(columns=cols)

    def pick(*names: str) -> Optional[str]:
        for n in names:
            if n in df.columns:
                return n
        return None

    c_keyword = pick("keyword", "ключ", "ключевое слово", "запрос", "поисковый запрос", "фраза", "phrase")
    c_views = pick("views", "impressions", "shows", "показы", "показы (шт)", "просмотры")
    c_clicks = pick("clicks", "click", "клики", "клики (шт)")
    c_spend = pick("spend", "cost", "sum", "расход", "затраты", "стоимость", "сумма расхода")
    c_orders = pick("orders", "заказы", "кол-во заказов", "количество заказов")
    c_revenue = pick("revenue", "orderSum", "выручка", "сумма заказов", "сумма выкупов", "сумма продаж")

    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        it: Dict[str, Any] = {}
        if c_keyword:
            it["keyword"] = r.get(c_keyword)
        if c_views:
            it["views"] = r.get(c_views)
        if c_clicks:
            it["clicks"] = r.get(c_clicks)
        if c_spend:
            it["spend"] = r.get(c_spend)
        if c_orders:
            it["orders"] = r.get(c_orders)
        if c_revenue:
            it["orderSum"] = r.get(c_revenue)
        # Keep any other columns as-is for debugging
        rows.append(it)
    return rows


def load_ads_stats(
    client: Any,
    date_from: str,
    date_to: str,
    manual_dir: str = "data/manual_ads",
) -> Tuple[Any, str, Optional[str]]:
    """Load ads stats with fallback.

    Returns: (ads_raw, source, manual_file_name)
      source in {"api", "manual", "empty"}
    """
    ads_raw: Any = []
    try:
        ads_raw = client.fetch_ads_stats(date_from, date_to)
    except Exception:
        ads_raw = []

    if ads_raw:
        return ads_raw, "api", None

    manual_file = _guess_manual_file(manual_dir)
    if not manual_file:
        return [], "empty", None

    try:
        if manual_file.suffix.lower() == ".json":
            import json
            ads_raw = json.loads(manual_file.read_text(encoding="utf-8"))
            # Could be dict with rows
            if isinstance(ads_raw, dict) and "rows" in ads_raw:
                ads_raw = ads_raw["rows"]
        elif manual_file.suffix.lower() in (".csv",):
            df = pd.read_csv(manual_file)
            ads_raw = _normalize_manual_rows(df)
        else:
            # Excel: take first sheet
            df = pd.read_excel(manual_file)
            ads_raw = _normalize_manual_rows(df)
    except Exception:
        ads_raw = []

    if not ads_raw:
        return [], "empty", str(manual_file.name)

    return ads_raw, "manual", str(manual_file.name)
