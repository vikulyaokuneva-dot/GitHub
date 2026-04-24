from __future__ import annotations

import os
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List

import requests

from wb_api_core.token_resolver import resolve_wb_api_token


class WBClient:
    def __init__(self, token: str | None = None):
        self.token, self.token_env_name_used = resolve_wb_api_token(token)
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

    @staticmethod
    def _row_date_iso(row: Dict[str, Any]) -> str:
        for key in (
            "date",
            "dateFrom",
            "dateTo",
            "lastChangeDate",
            "sale_dt",
            "order_dt",
        ):
            raw = str(row.get(key) or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", raw):
                return raw[:10]
        return ""

    @staticmethod
    def _first_present_key(row: Dict[str, Any], keys: Iterable[str]) -> str:
        for key in keys:
            if key in row and str(row.get(key) or "").strip():
                return key
        return ""

    @classmethod
    def _extract_operation_meta(cls, row: Dict[str, Any]) -> Dict[str, str]:
        operation = cls._pick_first_text(
            row,
            (
                "supplierOperName",
                "supplier_oper_name",
                "supplier_oper_name_ru",
                "operation",
                "operationName",
                "docTypeName",
                "doc_type_name",
            ),
        )
        operation_type = cls._pick_first_text(
            row,
            (
                "supplierOperTypeName",
                "supplier_oper_type_name",
                "supplierOperType",
                "supplier_oper_type",
                "operationType",
                "operation_type",
            ),
        )
        operation_name = cls._pick_first_text(
            row,
            (
                "nmSubjectName",
                "subjectName",
                "subject",
                "brandName",
                "name",
                "nmName",
            ),
        )
        return {
            "_operation": operation,
            "_operation_type": operation_type,
            "_operation_name": operation_name,
        }

    @classmethod
    def _map_realization_row(cls, row: Dict[str, Any], raw_row_index: int) -> Dict[str, Any]:
        sku_keys = ("nmId", "nm_id", "nmid", "nmID", "barcode", "supplierArticle", "vendorCode")
        sku_key = cls._first_present_key(row, sku_keys)
        sku = cls._as_sku(row.get(sku_key)) if sku_key else ""
        seller_sku = cls._as_sku(
            row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("techSize")
        )
        warehouse = cls._pick_first_text(
            row,
            (
                "warehouseName",
                "warehouse",
                "officeName",
                "giOfficeName",
                "oblastOkrugName",
            ),
        )
        quantity = cls._pick_first_float(
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
        revenue = cls._pick_first_float(
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
        cost_price = cls._pick_first_float(
            row,
            (
                "cost_price",
                "costPrice",
                "purchasePrice",
                "supplierPrice",
            ),
            default=0.0,
        )
        wb_commission = cls._pick_first_float(
            row,
            (
                "wb_commission",
                "commission",
                "retailCommission",
                "ppvz_sales_commission",
                "ppvz_sales_commission_value",
            ),
            default=0.0,
        )
        logistics = cls._pick_first_float(
            row,
            (
                "logistics",
                "delivery_rub",
                "deliveryAmount",
                "deliveryCost",
            ),
            default=0.0,
        )
        penalties = cls._pick_first_float(
            row,
            (
                "penalties",
                "penalty",
                "penaltyAmount",
            ),
            default=0.0,
        )
        storage = cls._pick_first_float(
            row,
            (
                "storage",
                "storage_fee",
                "storageFee",
            ),
            default=0.0,
        )
        deductions = cls._pick_first_float(
            row,
            (
                "deductions",
                "deduction",
                "acquiringFee",
            ),
            default=0.0,
        )
        explicit_profit = cls._pick_optional_float(
            row,
            (
                "profit",
                "netProfit",
                "income",
            ),
        )
        profit = (
            explicit_profit
            if explicit_profit is not None
            else revenue - cost_price - wb_commission - logistics - penalties - storage - deductions
        )

        item: Dict[str, Any] = {
            "sku": sku,
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "orders": quantity,
            "buys": quantity,
            "sales_count": quantity,
            "cost_price": round(cost_price, 2),
            "wb_commission": round(wb_commission, 2),
            "logistics": round(logistics, 2),
            "penalties": round(penalties, 2),
            "storage": round(storage, 2),
            "deductions": round(deductions, 2),
            "_raw_row_index": raw_row_index,
            "_source_dataset": "realization",
            "_raw_sku_value": str(row.get(sku_key) or "").strip() if sku_key else "",
            "_sku_source_field": sku_key,
        }
        if seller_sku:
            item["seller_sku"] = seller_sku
        if warehouse:
            item["warehouse"] = warehouse
        item.update(cls._extract_operation_meta(row))
        return item

    @classmethod
    def _map_sales_row(cls, row: Dict[str, Any], raw_row_index: int) -> Dict[str, Any]:
        sku_keys = ("nmId", "nm_id", "nmid", "barcode", "supplierArticle", "vendorCode")
        sku_key = cls._first_present_key(row, sku_keys)
        sku = cls._as_sku(row.get(sku_key)) if sku_key else ""
        seller_sku = cls._as_sku(
            row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("techSize")
        )
        warehouse = cls._pick_first_text(
            row,
            (
                "warehouseName",
                "warehouse",
                "officeName",
                "oblastOkrugName",
            ),
        )
        quantity = cls._pick_first_float(
            row,
            ("quantity", "sa_quantity", "saleQty", "sales_qty"),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if cls._pick_first_text(row, ("saleID", "saleId", "srid", "gNumber")) else 0.0
        revenue = cls._pick_first_float(
            row,
            (
                "revenue",
                "forPay",
                "totalPrice",
                "finishedPrice",
                "priceWithDisc",
                "salePriceWithDisc",
            ),
            default=0.0,
        )
        cost_price = cls._pick_first_float(
            row,
            (
                "cost_price",
                "costPrice",
                "purchasePrice",
                "supplierPrice",
            ),
            default=0.0,
        )
        wb_commission = cls._pick_first_float(
            row,
            (
                "wb_commission",
                "commission",
                "retailCommission",
                "ppvz_sales_commission",
                "ppvz_sales_commission_value",
            ),
            default=0.0,
        )
        logistics = cls._pick_first_float(
            row,
            (
                "logistics",
                "delivery_rub",
                "deliveryAmount",
                "deliveryCost",
            ),
            default=0.0,
        )
        penalties = cls._pick_first_float(
            row,
            (
                "penalties",
                "penalty",
                "penaltyAmount",
            ),
            default=0.0,
        )
        storage = cls._pick_first_float(
            row,
            (
                "storage",
                "storage_fee",
                "storageFee",
            ),
            default=0.0,
        )
        deductions = cls._pick_first_float(
            row,
            (
                "deductions",
                "deduction",
                "acquiringFee",
            ),
            default=0.0,
        )
        explicit_profit = cls._pick_optional_float(
            row,
            (
                "profit",
                "netProfit",
                "income",
            ),
        )
        profit = (
            explicit_profit
            if explicit_profit is not None
            else revenue - cost_price - wb_commission - logistics - penalties - storage - deductions
        )

        item: Dict[str, Any] = {
            "sku": sku,
            "revenue": round(revenue, 2),
            "profit": round(profit, 2),
            "orders": quantity,
            "buys": quantity,
            "sales_count": quantity,
            "cost_price": round(cost_price, 2),
            "wb_commission": round(wb_commission, 2),
            "logistics": round(logistics, 2),
            "penalties": round(penalties, 2),
            "storage": round(storage, 2),
            "deductions": round(deductions, 2),
            "_raw_row_index": raw_row_index,
            "_source_dataset": "sales",
            "_raw_sku_value": str(row.get(sku_key) or "").strip() if sku_key else "",
            "_sku_source_field": sku_key,
        }
        if seller_sku:
            item["seller_sku"] = seller_sku
        if warehouse:
            item["warehouse"] = warehouse
        item.update(cls._extract_operation_meta(row))
        return item

    @classmethod
    def _map_orders_row(cls, row: Dict[str, Any], raw_row_index: int) -> Dict[str, Any]:
        sku_keys = ("nmId", "nm_id", "nmid", "barcode", "supplierArticle", "vendorCode")
        sku_key = cls._first_present_key(row, sku_keys)
        sku = cls._as_sku(row.get(sku_key)) if sku_key else ""
        seller_sku = cls._as_sku(
            row.get("supplierArticle")
            or row.get("vendorCode")
            or row.get("techSize")
        )
        warehouse = cls._pick_first_text(
            row,
            (
                "warehouseName",
                "warehouse",
                "officeName",
                "oblastOkrugName",
            ),
        )
        quantity = cls._pick_first_float(
            row,
            (
                "quantity",
                "orderQty",
                "orderCount",
                "ordersCount",
                "orders",
            ),
            default=0.0,
        )
        if quantity <= 0:
            quantity = 1.0 if cls._pick_first_text(row, ("odid", "srid", "gNumber")) else 0.0
        revenue = cls._pick_first_float(
            row,
            (
                "totalPrice",
                "priceWithDisc",
                "finishedPrice",
                "convertedPrice",
            ),
            default=0.0,
        )
        item: Dict[str, Any] = {
            "sku": sku,
            "revenue": round(revenue, 2),
            "profit": 0.0,
            "orders": quantity,
            "buys": 0.0,
            "sales_count": 0.0,
            "cost_price": 0.0,
            "wb_commission": 0.0,
            "logistics": 0.0,
            "penalties": 0.0,
            "storage": 0.0,
            "deductions": 0.0,
            "_raw_row_index": raw_row_index,
            "_source_dataset": "orders",
            "_raw_sku_value": str(row.get(sku_key) or "").strip() if sku_key else "",
            "_sku_source_field": sku_key,
        }
        if seller_sku:
            item["seller_sku"] = seller_sku
        if warehouse:
            item["warehouse"] = warehouse
        item.update(cls._extract_operation_meta(row))
        return item

    def fetch_realization(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        print(f"[wb] fetch_realization started date_from={date_from} date_to={date_to}")
        payload = self._get_json(
            base_url=self.statistics_url,
            path="/api/v5/supplier/reportDetailByPeriod",
            params={
                "dateFrom": date_from,
                "dateTo": date_to,
                "limit": 100000,
                "rrdid": 0,
            },
            allow_204=True,
            empty_on_204=[],
        )
        rows = self._extract_rows(payload, ("data", "items", "rows"))
        out = [self._map_realization_row(row, raw_row_index=index) for index, row in enumerate(rows)]
        print(f"[wb] fetch_realization rows={len(out)}")
        return out

    def fetch_sales(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        print(f"[wb] fetch_sales started date_from={date_from} date_to={date_to}")
        payload = self._get_json(
            base_url=self.statistics_url,
            path="/api/v1/supplier/sales",
            params={"dateFrom": date_from},
            allow_204=True,
            empty_on_204=[],
        )
        rows = self._extract_rows(payload, ("data", "items", "rows"))
        out: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            row_date = self._row_date_iso(row)
            if row_date and row_date > date_to:
                continue
            out.append(self._map_sales_row(row, raw_row_index=index))
        print(f"[wb] fetch_sales rows={len(out)}")
        return out

    def fetch_orders(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        print(f"[wb] fetch_orders started date_from={date_from} date_to={date_to}")
        payload = self._get_json(
            base_url=self.statistics_url,
            path="/api/v1/supplier/orders",
            params={"dateFrom": date_from},
            allow_204=True,
            empty_on_204=[],
        )
        rows = self._extract_rows(payload, ("data", "items", "rows"))
        out: List[Dict[str, Any]] = []
        for index, row in enumerate(rows):
            row_date = self._row_date_iso(row)
            if row_date and row_date > date_to:
                continue
            out.append(self._map_orders_row(row, raw_row_index=index))
        print(f"[wb] fetch_orders rows={len(out)}")
        return out

    def fetch_ads(self, date_from: str, date_to: str) -> List[Dict[str, Any]]:
        print(f"[wb] fetch_ads started date_from={date_from} date_to={date_to}")
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
            print("[wb] fetch_ads rows=0")
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
                    "beginDate": date_from,
                    "endDate": date_to,
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
                        impressions = self._pick_first_float(
                            nm,
                            ("impressions", "views", "shows", "imps"),
                            default=0.0,
                        )
                        clicks = self._pick_first_float(
                            nm,
                            ("clicks", "click"),
                            default=0.0,
                        )
                        add_to_cart = self._pick_first_float(
                            nm,
                            ("addToCart", "add_to_cart", "atbs", "cart_count"),
                            default=0.0,
                        )
                        orders = self._pick_first_float(
                            nm,
                            ("orders", "order_count", "ordersCount"),
                            default=0.0,
                        )
                        if sku not in bucket:
                            bucket[sku] = {"ads_spend": 0.0, "impressions": 0.0, "clicks": 0.0, "add_to_cart": 0.0, "orders": 0.0}
                        bucket[sku]["ads_spend"] += spend
                        bucket[sku]["impressions"] += impressions
                        bucket[sku]["clicks"] += clicks
                        bucket[sku]["add_to_cart"] += add_to_cart
                        bucket[sku]["orders"] += orders

        out: List[Dict[str, Any]] = []
        for sku, agg in bucket.items():
            orders = float(agg.get("orders", 0.0))
            ads_spend = float(agg.get("ads_spend", 0.0))
            impressions = float(agg.get("impressions", 0.0))
            clicks = float(agg.get("clicks", 0.0))
            add_to_cart = float(agg.get("add_to_cart", 0.0))
            ctr = (clicks / impressions * 100.0) if impressions > 0 else None
            cpo = (ads_spend / orders) if orders > 0 else None
            out.append(
                {
                    "sku": sku,
                    "ads_spend": round(ads_spend, 2),
                    "impressions": int(round(impressions)),
                    "clicks": int(round(clicks)),
                    "add_to_cart": int(round(add_to_cart)),
                    "orders": int(round(orders)),
                    "ctr": round(ctr, 2) if ctr is not None else None,
                    "cpo": round(cpo, 2) if cpo is not None else None,
                }
            )
        out.sort(key=lambda row: float(row.get("ads_spend", 0.0) or 0.0), reverse=True)
        print(f"[wb] fetch_ads rows={len(out)}")
        return out

    def fetch_stocks(self) -> List[Dict[str, Any]]:
        date_from = (date.today() - timedelta(days=30)).isoformat()
        print(f"[wb] fetch_stocks started date_from={date_from}")
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
        print(f"[wb] fetch_stocks rows={len(out)}")
        return out
