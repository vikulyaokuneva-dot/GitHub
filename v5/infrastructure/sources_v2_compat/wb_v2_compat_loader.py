"""v2-compatible API ingestion path for v5.

This loader keeps the proven v2 sequence and request semantics:
1) sales funnel
2) ads stats (+ manual fallback)
3) stocks
4) realization with lag fallback
"""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.ads_loader import load_ads_stats as v2_load_ads_stats
from src.metrics import calc_financial_metrics, calc_funnel_metrics
from src.wb_client import WBClient as V2WBClient

from ...domain import CabinetContext, RawDataBundle, RawRatingsData
from ..sources.base import DataSource
from ..sources.parsers import AdsParser, MarginsParser, OrdersParser, ReturnsParser


def _safe_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except Exception:
        return 0


def _safe_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _iter_dict_rows(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return

    if isinstance(payload, dict):
        preferred = ("data", "products", "items", "rows", "result", "stocks", "list", "adverts")
        for key in preferred:
            if key in payload:
                yield from _iter_dict_rows(payload.get(key))
        for val in payload.values():
            if isinstance(val, (list, dict)):
                yield from _iter_dict_rows(val)


def _count_rows(payload: Any) -> int:
    return sum(1 for _ in _iter_dict_rows(payload))


def _extract_products_from_funnel(funnel_raw: Any) -> list[dict[str, Any]]:
    if isinstance(funnel_raw, dict):
        data = funnel_raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("products"), list):
            return [x for x in data.get("products", []) if isinstance(x, dict)]
    return []


class V2CompatibleWBAPILoader(DataSource):
    """Loader that reuses v2 ingestion path but returns v5 domain contracts."""

    def __init__(
        self,
        *,
        max_finance_lag_days: int | None = None,
        manual_ads_dir: str = "data/manual_ads",
        tax_rate: float | None = None,
    ) -> None:
        self.max_finance_lag_days = (
            int(max_finance_lag_days)
            if max_finance_lag_days is not None
            else int(os.getenv("WB_MAX_FINANCE_LAG_DAYS", "3"))
        )
        self.manual_ads_dir = manual_ads_dir
        self.tax_rate = float(tax_rate) if tax_rate is not None else float(os.getenv("WB_TAX_RATE", "0.06"))

    async def load_data(self, cabinet_ctx: CabinetContext, target_date: date) -> RawDataBundle:
        return await asyncio.to_thread(self._load_data_sync, cabinet_ctx, target_date)

    def _load_data_sync(self, cabinet_ctx: CabinetContext, target_date: date) -> RawDataBundle:
        api_key = str(cabinet_ctx.cabinet.api_key or "").strip()
        if not api_key:
            raise ValueError(f"Cabinet {cabinet_ctx.cabinet.id} has no API key configured")

        raw_dir = cabinet_ctx.raw_data_dir / "v2_compat_raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        client = V2WBClient(token=api_key, raw_dir=str(raw_dir))
        manual_ads_dir = self._resolve_manual_ads_dir(cabinet_ctx)

        date_from = target_date.isoformat()
        date_to = target_date.isoformat()

        # v2 truth sequence (do not reorder)
        funnel_raw = client.fetch_sales_funnel(date_from, date_to)
        ads_raw, ads_source, manual_ads_file = v2_load_ads_stats(
            client,
            date_from,
            date_to,
            manual_dir=manual_ads_dir,
        )
        stocks_raw = client.fetch_stocks()
        realization_raw, finance_date_used, finance_lag_days = self._pick_realization_with_lag(
            client=client,
            target_date=target_date,
        )

        # Convert raw payloads to v5 domain contracts.
        ads_data = AdsParser.parse_ads_stats(
            ads_stats=ads_raw if isinstance(ads_raw, list) else [],
            target_date=target_date,
        )
        orders_from_realization = OrdersParser.parse_orders_from_realization(
            realization=realization_raw,
            target_date=finance_date_used,
            enforce_date_match=False,
        )
        orders_from_funnel = OrdersParser.parse_orders_from_funnel(
            funnel=funnel_raw if isinstance(funnel_raw, dict) else {},
            target_date=target_date,
        )
        orders_data = orders_from_realization if orders_from_realization else orders_from_funnel
        margins_data = MarginsParser.parse_margins_from_realization(
            realization=realization_raw,
            target_date=finance_date_used,
            enforce_date_match=False,
        )
        returns_data = ReturnsParser.parse_returns(
            realization=realization_raw,
            target_date=finance_date_used,
            enforce_date_match=False,
        )
        ratings_data = self._parse_ratings_from_funnel(funnel_raw, target_date)

        v2_counts = self._build_v2_truth_counts(
            ads_raw=ads_raw,
            funnel_raw=funnel_raw,
            realization_raw=realization_raw,
            stocks_raw=stocks_raw,
        )
        v5_funnel_metrics = calc_funnel_metrics(funnel_raw)
        v5_counts = {
            "ads_count": len(ads_data),
            "orders_count": _safe_int(v5_funnel_metrics.get("orders")),
            "realization_rows_count": _count_rows(realization_raw),
            "stocks_count": _count_rows(stocks_raw),
            "returns_count": len(returns_data),
            "ratings_count": len(ratings_data),
        }
        comparison = {
            "v2_truth_counts": v2_counts,
            "v5_compat_counts": v5_counts,
            "not_less_than_v2": {
                key: int(v5_counts.get(key, 0) or 0) >= int(v2_counts.get(key, 0) or 0)
                for key in ("ads_count", "orders_count", "returns_count", "ratings_count")
            },
            "notes": {
                "realization_rows_count": "same raw source for v2 and v5-compat in this run",
                "stocks_count": "same raw source for v2 and v5-compat in this run",
            },
        }

        debug = {
            "ingestion_path": "v2_compat",
            "finance_date_used": finance_date_used.isoformat(),
            "finance_lag_days": finance_lag_days,
            "ads_source": ads_source,
            "manual_ads_dir": manual_ads_dir,
            "manual_ads_file": manual_ads_file,
            "source_counts_comparison": comparison,
            "v2_raw_counts": v2_counts,
            "v5_compat_counts": v5_counts,
            "orders_records_count": len(orders_data),
        }
        return RawDataBundle(
            cabinet_id=cabinet_ctx.cabinet.id,
            period_date=target_date,
            source="api",
            ads=ads_data,
            orders=orders_data,
            margins=margins_data,
            returns=returns_data,
            ratings=ratings_data,
            debug=debug,
        )

    def _pick_realization_with_lag(
        self,
        *,
        client: V2WBClient,
        target_date: date,
    ) -> tuple[list[dict[str, Any]], date, int]:
        last_rows: list[dict[str, Any]] = []
        last_date = target_date
        for lag in range(0, self.max_finance_lag_days + 1):
            dt_used = target_date - timedelta(days=lag)
            rows = client.fetch_realization_report(dt_used.isoformat(), dt_used.isoformat())
            parsed = [x for x in _iter_dict_rows(rows)]
            if parsed:
                return parsed, dt_used, lag
            last_rows = parsed
            last_date = dt_used
        return last_rows, last_date, self.max_finance_lag_days

    def _parse_ratings_from_funnel(self, funnel_raw: Any, target_date: date) -> list[RawRatingsData]:
        products = _extract_products_from_funnel(funnel_raw)
        out: list[RawRatingsData] = []
        for p in products:
            sku_id = str(p.get("nmId") or p.get("id") or "").strip()
            if not sku_id:
                continue
            st = p.get("statistic") if isinstance(p.get("statistic"), dict) else {}
            selected = st.get("selected") if isinstance(st, dict) and isinstance(st.get("selected"), dict) else {}
            rating = _safe_float(p.get("rating") if p.get("rating") is not None else selected.get("rating"))
            review_count = _safe_int(
                p.get("feedbackCount")
                if p.get("feedbackCount") is not None
                else selected.get("feedbackCount")
            )
            out.append(
                RawRatingsData(
                    sku_id=sku_id,
                    rating=rating,
                    review_count=review_count,
                    negative_reviews=0,
                    date=target_date,
                )
            )
        return out

    def _build_v2_truth_counts(
        self,
        *,
        ads_raw: Any,
        funnel_raw: Any,
        realization_raw: Any,
        stocks_raw: Any,
    ) -> dict[str, int]:
        funnel_metrics = calc_funnel_metrics(funnel_raw)
        financial_metrics = calc_financial_metrics(realization_raw, tax_rate=self.tax_rate)
        products = _extract_products_from_funnel(funnel_raw)
        ratings_count = 0
        for p in products:
            if p.get("rating") is not None or p.get("feedbackCount") is not None:
                ratings_count += 1
        return {
            "ads_count": _count_rows(ads_raw),
            "orders_count": _safe_int(funnel_metrics.get("orders")),
            "realization_rows_count": _count_rows(realization_raw),
            "stocks_count": _count_rows(stocks_raw),
            "returns_count": _safe_int(financial_metrics.get("returns_qty")),
            "ratings_count": ratings_count,
        }

    def _resolve_manual_ads_dir(self, cabinet_ctx: CabinetContext) -> str:
        configured = Path(self.manual_ads_dir)
        if configured.is_absolute():
            return str(configured)

        candidates = [
            # v5-local preferred path (isolated runtime namespace)
            cabinet_ctx.cabinet_root / configured,
            # seller-level legacy manual ads folder (read-only fallback)
            cabinet_ctx.seller_root / configured,
            # repository-relative fallback (same as v2 behavior)
            configured,
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return str(candidates[0])
