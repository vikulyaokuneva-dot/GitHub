from __future__ import annotations

import os
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List

import requests


class WBClient:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("WB_API_TOKEN")
        if not self.token:
            raise ValueError("WB_API_TOKEN not provided")
        self.token = self.token.strip()
        if not self.token:
            raise ValueError("WB_API_TOKEN not provided")

        self.advert_url = os.getenv("WB_ADVERT_BASE_URL", "https://advert-api.wildberries.ru").rstrip("/")
        self.statistics_url = os.getenv("WB_STATISTICS_BASE_URL", "https://statistics-api.wildberries.ru").rstrip("/")

    @staticmethod
    def _as_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        text = text.replace(" ", "").replace(",", ".").replace("%", "")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _as_sku(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if re.fullmatch(r"\d+(\.0+)?", text):
            return text.split(".", 1)[0]
        return text

    @staticmethod
    def _pick_first_text(row: Dict[str, Any], keys: Iterable[str]) -> str:
        for key in keys:
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return ""

    @classmethod
    def _pick_first_float(cls, row: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
        for key in keys:
            value = cls._as_float(row.get(key))
            if value is not None:
                return value
        return default

    @classmethod
    def _pick_optional_float(cls, row: Dict[str, Any], keys: Iterable[str]) -> float | None:
        for key in keys:
            value = cls._as_float(row.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _extract_rows(payload: Any, keys: Iterable[str]) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        for value in payload.values():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return [row for row in value if isinstance(row, dict)]
        return []

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _get_json(
        self,
        base_url: str,
        path: str,
        params: Dict[str, Any] | None = None,
        *,
        allow_204: bool = False,
        empty_on_204: Any = None,
        allow_403: bool = False,
        empty_on_403: Any = None,
    ) -> Any:
        url = f"{base_url.rstrip('/')}{path}"
        last_error: str = "unknown_error"
        for attempt in range(1, 6):
            try:
                response = requests.get(url, headers=self._headers(), params=params or {}, timeout=60)
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 204 and allow_204:
                    return empty_on_204
                if response.status_code == 403 and allow_403:
                    return empty_on_403
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = f"{response.status_code}: {response.text[:200]}"
                    time.sleep(attempt * 1.5)
                    continue
                raise RuntimeError(f"WB API error {response.status_code}: {response.text}")
            except Exception as exc:
                last_error = str(exc)
                time.sleep(attempt * 1.5)
        raise RuntimeError(f"WB API failed after retries: {last_error}")

    def fetch_sales(self, run_date: str) -> List[Dict[str, Any]]:
        payload = self._get_json(
            base_url=self.statistics_url,
            path="/api/v5/supplier/reportDetailByPeriod",
            params={
                "dateFrom": run_date,
                "dateTo": run_date,
                "limit": 100000,
                "rrdid": 0,
            },
            allow_204=True,
            empty_on_204=[],
        )
        rows = self._extract_rows(payload, ("data", "items", "rows"))
        out: List[Dict[str, Any]] = []
        for row in rows:
            sku = self._as_sku(
                row.get("nmId")
                or row.get("nm_id")
                or row.get("nmid")
                or row.get("nmID")
                or row.get("barcode")
                or row.get("supplierArticle")
                or row.get("vendorCode")
            )
            seller_sku = self._as_sku(
                row.get("supplierArticle")
                or row.get("vendorCode")
                or row.get("techSize")
            )
            warehouse = self._pick_first_text(
                row,
                (
                    "warehouseName",
                    "warehouse",
                    "officeName",
                    "giOfficeName",
                    "oblastOkrugName",
                ),
            )
            quantity = self._pick_first_float(
                row,
                (
                    "quantity",
                    "sa_quantity",
                    "sales_qty",
                    "saleQty",
                    "ordersCount",
                    "order_count",
                    "orders",
                ),
                default=0.0,
            )
            revenue = self._pick_first_float(
                row,
                (
                    "revenue",
                    "ppvz_for_pay",
                    "forPay",
                    "retail_amount",
                    "retailPriceWithDiscRub",
                ),
                default=0.0,
            )
            logistics = self._pick_first_float(
                row,
                (
                    "logistics",
                    "delivery_rub",
                    "deliveryAmount",
                    "deliveryCost",
                ),
                default=0.0,
            )
            penalties = self._pick_first_float(
                row,
                (
                    "penalties",
                    "penalty",
                    "penaltyAmount",
                ),
                default=0.0,
            )
            storage = self._pick_first_float(
                row,
                (
                    "storage",
                    "storage_fee",
                    "storageFee",
                ),
                default=0.0,
            )
            deductions = self._pick_first_float(
                row,
                (
                    "deductions",
                    "deduction",
                    "acquiringFee",
                ),
                default=0.0,
            )
            explicit_profit = self._pick_optional_float(
                row,
                (
                    "profit",
                    "netProfit",
                    "income",
                ),
            )
            profit = explicit_profit if explicit_profit is not None else revenue - logistics - penalties - storage - deductions

            item: Dict[str, Any] = {
                "sku": sku,
                "revenue": round(revenue, 2),
                "profit": round(profit, 2),
                "orders": quantity,
                "buys": quantity,
                "sales_count": quantity,
                "logistics": round(logistics, 2),
                "penalties": round(penalties, 2),
                "storage": round(storage, 2),
                "deductions": round(deductions, 2),
            }
            if seller_sku:
                item["seller_sku"] = seller_sku
            if warehouse:
                item["warehouse"] = warehouse
            out.append(item)
        return out

    def fetch_ads(self, run_date: str) -> List[Dict[str, Any]]:
        adverts_payload = self._get_json(
            base_url=self.advert_url,
            path="/api/advert/v2/adverts",
            params={},
            allow_403=True,
            empty_on_403={},
        )
        advert_rows = self._extract_rows(adverts_payload, ("adverts", "items", "rows"))
        advert_ids: List[int] = []
        for row in advert_rows:
            raw_id = row.get("advertId")
            if raw_id is None:
                raw_id = row.get("id")
            value = self._as_float(raw_id)
            if value is None:
                continue
            advert_ids.append(int(value))
        if not advert_ids:
            return []

        bucket: Dict[str, Dict[str, float]] = {}
        chunk_size = 50
        for idx in range(0, len(advert_ids), chunk_size):
            chunk = advert_ids[idx:idx + chunk_size]
            stats_payload = self._get_json(
                base_url=self.advert_url,
                path="/adv/v3/fullstats",
                params={
                    "ids": ",".join(str(advert_id) for advert_id in chunk),
                    "beginDate": run_date,
                    "endDate": run_date,
                },
                allow_204=True,
                empty_on_204=[],
                allow_403=True,
                empty_on_403=[],
            )
            stats_rows = self._extract_rows(stats_payload, ("items", "rows"))
            for stat in stats_rows:
                day_rows = self._extract_rows(stat, ("days", "items", "rows"))
                for day in day_rows:
                    nm_rows = self._extract_rows(day, ("nm", "nms", "items", "rows"))
                    if not nm_rows:
                        app_rows = self._extract_rows(day, ("apps", "items", "rows"))
                        for app in app_rows:
                            nm_rows.extend(self._extract_rows(app, ("nm", "nms", "items", "rows")))
                    for nm in nm_rows:
                        sku = self._as_sku(
                            nm.get("nmId")
                            or nm.get("nm_id")
                            or nm.get("nmid")
                            or nm.get("nm")
                        )
                        if not sku:
                            continue
                        spend = self._pick_first_float(
                            nm,
                            ("sum", "spend", "cost", "expenses", "price"),
                            default=0.0,
                        )
                        clicks = self._pick_first_float(
                            nm,
                            ("clicks", "click"),
                            default=0.0,
                        )
                        orders = self._pick_first_float(
                            nm,
                            ("orders", "order_count", "ordersCount"),
                            default=0.0,
                        )
                        if sku not in bucket:
                            bucket[sku] = {"ads_spend": 0.0, "clicks": 0.0, "orders": 0.0}
                        bucket[sku]["ads_spend"] += spend
                        bucket[sku]["clicks"] += clicks
                        bucket[sku]["orders"] += orders

        out: List[Dict[str, Any]] = []
        for sku, agg in bucket.items():
            orders = float(agg.get("orders", 0.0))
            ads_spend = float(agg.get("ads_spend", 0.0))
            cpo = (ads_spend / orders) if orders > 0 else None
            out.append(
                {
                    "sku": sku,
                    "ads_spend": round(ads_spend, 2),
                    "cpo": round(cpo, 2) if cpo is not None else None,
                }
            )
        out.sort(key=lambda row: float(row.get("ads_spend", 0.0) or 0.0), reverse=True)
        return out

    def fetch_stocks(self) -> List[Dict[str, Any]]:
        date_from = (date.today() - timedelta(days=30)).isoformat()
        payload = self._get_json(
            base_url=self.statistics_url,
            path="/api/v1/supplier/stocks",
            params={"dateFrom": date_from},
            allow_204=True,
            empty_on_204=[],
        )
        rows = self._extract_rows(payload, ("data", "items", "rows"))
        out: List[Dict[str, Any]] = []
        for row in rows:
            sku = self._as_sku(
                row.get("nmId")
                or row.get("nm_id")
                or row.get("nmid")
                or row.get("barcode")
            )
            seller_sku = self._as_sku(
                row.get("supplierArticle")
                or row.get("vendorCode")
            )
            warehouse = self._pick_first_text(
                row,
                (
                    "warehouseName",
                    "warehouse",
                    "officeName",
                ),
            )
            quantity_full = self._pick_first_float(row, ("quantityFull", "quantity_full"), default=0.0)
            quantity = self._pick_first_float(row, ("quantity", "qty"), default=0.0)
            in_way_to_client = self._pick_first_float(row, ("inWayToClient",), default=0.0)
            in_way_from_client = self._pick_first_float(row, ("inWayFromClient",), default=0.0)
            stock = max(quantity_full, quantity, quantity + in_way_to_client + in_way_from_client)

            item: Dict[str, Any] = {
                "sku": sku,
                "stock": round(max(stock, 0.0), 2),
            }
            if seller_sku:
                item["seller_sku"] = seller_sku
            if warehouse:
                item["warehouse"] = warehouse
            out.append(item)
        return out
