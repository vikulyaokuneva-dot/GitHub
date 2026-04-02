"""FileReportLoader - Р·Р°РіСЂСѓР·РєР° РґР°РЅРЅС‹С… РёР· Excel/CSV РѕС‚С‡С‘С‚РѕРІ Р’Р‘"""

import asyncio
import logging
import re
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, Optional, List
import pandas as pd

from ...domain import (
    RawDataBundle,
    CabinetContext,
    RawAdsData,
    RawOrdersData,
    RawMarginsData,
    RawReturnsData,
    RawRatingsData,
)
from .base import DataSource

logger = logging.getLogger(__name__)


class FileReportLoader(DataSource):
    """Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ РёР· Excel/CSV РѕС‚С‡С‘С‚РѕРІ Р’Р‘"""

    def __init__(self, shared_input_dir: str = "v5/audit/input"):
        self.shared_input_dir = Path(shared_input_dir)
        self.input_dir = self.shared_input_dir
        self._finance_loader_debug: Dict[str, Any] = {}

    async def load_data(
        self, cabinet_ctx: CabinetContext, target_date: Optional[date] = None
    ) -> RawDataBundle:
        """
        Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ РёР· С„Р°Р№Р»РѕРІ РѕС‚С‡С‘С‚РѕРІ.

        Args:
            cabinet_ctx: РљРѕРЅС‚РµРєСЃС‚ РєР°Р±РёРЅРµС‚Р° СЃ РїСѓС‚СЏРјРё
            target_date: РљРѕРЅРєСЂРµС‚РЅР°СЏ РґР°С‚Р° (РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ)

        Returns:
            RawDataBundle СЃРѕ РІСЃРµРјРё РґР°РЅРЅС‹РјРё РёР· С„Р°Р№Р»РѕРІ
        """
        self.input_dir = self._resolve_input_dir(cabinet_ctx)
        logger.info(
            f"[FileReportLoader] Loading data from {self.input_dir} for {cabinet_ctx.cabinet.id}"
        )

        # РџР°СЂР°Р»Р»РµР»СЊРЅР°СЏ Р·Р°РіСЂСѓР·РєР° РёР· РІСЃРµС… РїР°РїРѕРє
        ads_task = asyncio.to_thread(self._load_ads_data, target_date)
        orders_task = asyncio.to_thread(self._load_orders_data, target_date)
        margins_task = asyncio.to_thread(self._load_margins_data, target_date)
        returns_task = asyncio.to_thread(self._load_returns_data, target_date)
        ratings_task = asyncio.to_thread(self._load_ratings_data, target_date)

        ads, orders, margins, returns, ratings = await asyncio.gather(
            ads_task, orders_task, margins_task, returns_task, ratings_task
        )

        bundle = RawDataBundle(
            source="report",
            cabinet_id=cabinet_ctx.cabinet.id,
            period_date=target_date or datetime.now().date(),
            ads=ads,
            orders=orders,
            margins=margins,
            returns=returns,
            ratings=ratings,
            debug={
                "input_dir": str(self.input_dir),
                "finance_loader": dict(self._finance_loader_debug or {}),
            },
        )

        logger.info(
            f"[FileReportLoader] вњ… Loaded: "
            f"ads={len(ads)}, orders={len(orders)}, "
            f"margins={len(margins)}, returns={len(returns)}, "
            f"ratings={len(ratings)}"
        )

        if self._finance_loader_debug:
            logger.info(
                "[FileReportLoader] finance debug: "
                f"rows_total={self._finance_loader_debug.get('rows_total', 0)}, "
                f"rows_loaded={self._finance_loader_debug.get('rows_loaded', 0)}, "
                f"rows_dropped={self._finance_loader_debug.get('rows_dropped', 0)}"
            )

        return bundle

    def _resolve_input_dir(self, cabinet_ctx: CabinetContext) -> Path:
        """
        Resolve audit input location with strict v5-first precedence:
          1) cabinet-scoped v5 input: cabinets/<seller>/v5/input
          2) shared v5 audit inbox: v5/audit/input
        """
        cabinet_input = cabinet_ctx.inputs_dir
        if cabinet_input.exists() and any(cabinet_input.rglob("*")):
            return cabinet_input
        return self.shared_input_dir

    def _load_ads_data(self, target_date: Optional[date] = None) -> List[RawAdsData]:
        """Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ РѕР±СЉСЏРІР»РµРЅРёР№ РёР· РїР°РїРєРё ads/"""
        ads = []
        ads_dir = self.input_dir / "ads"

        if not ads_dir.exists():
            logger.warning(f"[FileReportLoader] ads/ directory not found")
            return ads

        # РС‰РµРј С„Р°Р№Р»С‹ ads_stats, full_stats
        for file in list(ads_dir.glob("*stats*.xlsx")) + list(ads_dir.glob("*stats*.csv")):
            try:
                logger.info(f"[FileReportLoader] Parsing ads from {file.name}")

                if file.suffix == ".xlsx":
                    df = pd.read_excel(file, sheet_name=0)
                else:
                    df = pd.read_csv(file)

                # РќРѕСЂРјР°Р»РёР·СѓРµРј РЅР°Р·РІР°РЅРёСЏ РєРѕР»РѕРЅРѕРє
                df.columns = [c.lower().strip() for c in df.columns]

                # РџР°СЂСЃРёРј РѕР±СЉСЏРІР»РµРЅРёСЏ
                for _, row in df.iterrows():
                    try:
                        ad_id = self._get_val(row, ["id Р°РґСЂРµСЃР°", "campaign id", "id"])
                        if not ad_id:
                            continue
                        
                        sku = self._get_val(row, ["sku", "Р°СЂС‚РёРєСѓР»", "nmid"])
                        sku_ids = [str(sku)] if sku else []

                        ads.append(
                            RawAdsData(
                                ad_id=str(ad_id),
                                name=self._get_val(
                                    row,
                                    [
                                        "РЅР°Р·РІР°РЅРёРµ",
                                        "РЅР°РёРјРµРЅРѕРІР°РЅРёРµ",
                                        "adv name",
                                        "name",
                                    ],
                                )
                                or "Unknown",
                                sku_ids=sku_ids,
                                budget_daily=self._get_float(row, ["РґРЅРµРІРЅРѕР№ Р±СЋРґР¶РµС‚", "daily budget"])
                                or 0.0,
                                status=self._get_val(
                                    row, ["СЃС‚Р°С‚СѓСЃ", "status"]
                                )
                                or "active",
                                views=int(self._get_val(row, ["РїСЂРѕСЃРјРѕС‚СЂС‹", "views", "impressions"]) or 0),
                                clicks=int(
                                    self._get_val(row, ["РєР»РёРєРё", "clicks"]) or 0
                                ),
                                spend=self._get_float(row, ["С‚СЂР°С‚Р°", "СЂР°СЃС…РѕРґ", "spend", "cost"])
                                or 0.0,
                                date=target_date or date.today(),
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"[FileReportLoader] Failed to parse ads row: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"[FileReportLoader] Error loading {file.name}: {e}")
                continue

        return ads

    def _load_orders_data(self, target_date: Optional[date] = None) -> List[RawOrdersData]:
        """Load WB finance rows and map them to RawOrdersData without dropping valid rows."""
        orders: List[RawOrdersData] = []
        debug: Dict[str, Any] = {
            "rows_total": 0,
            "rows_loaded": 0,
            "rows_dropped": 0,
            "dropped_reasons": {},
            "files_parsed": [],
            "detected_columns": {},
            "operation_basis_detected": {},
            "component_nonzero_rows": {
                "gross_revenue": 0,
                "realized_revenue": 0,
                "seller_payout": 0,
                "commission": 0,
                "logistics": 0,
                "storage": 0,
                "penalties": 0,
                "deductions": 0,
                "loyalty_program": 0,
                "loyalty_points_withheld": 0,
                "acquiring": 0,
                "pvz_service": 0,
                "other_adjustments": 0,
            },
            "row_debug_sample": [],
        }
        self._finance_loader_debug = debug

        finance_dir = self.input_dir / "finance"
        if not finance_dir.exists():
            logger.warning(f"[FileReportLoader] finance/ directory not found")
            return orders

        for file in list(finance_dir.glob("*.xlsx")) + list(finance_dir.glob("*.csv")):
            if "margin" in file.name.lower():
                continue

            try:
                logger.info(f"[FileReportLoader] Parsing orders from {file.name}")
                debug["files_parsed"].append(file.name)

                if file.suffix == ".xlsx":
                    df = pd.read_excel(file, sheet_name=0)
                else:
                    df = pd.read_csv(file)

                df.columns = [self._canonicalize_name(c) for c in df.columns]
                debug["detected_columns"][file.name] = list(df.columns)

                for idx, row in df.iterrows():
                    debug["rows_total"] += 1
                    try:
                        parsed_row, drop_reason, row_diag = self._parse_finance_order_row(
                            row=row,
                            row_index=idx,
                            source_file=file.name,
                            row_date=target_date or date.today(),
                        )
                        if parsed_row is None:
                            reason = str(drop_reason or "unknown_drop")
                            debug["rows_dropped"] += 1
                            debug["dropped_reasons"][reason] = int(debug["dropped_reasons"].get(reason, 0) or 0) + 1
                            if len(debug["row_debug_sample"]) < 250:
                                debug["row_debug_sample"].append(row_diag)
                            continue

                        orders.append(parsed_row)
                        debug["rows_loaded"] += 1

                        op_basis = str(row_diag.get("operation_basis") or "").strip()
                        if op_basis:
                            debug["operation_basis_detected"][op_basis] = int(
                                debug["operation_basis_detected"].get(op_basis, 0) or 0
                            ) + 1

                        components = row_diag.get("components") or {}
                        if isinstance(components, dict):
                            for key in debug["component_nonzero_rows"].keys():
                                if abs(float(components.get(key, 0.0) or 0.0)) > 1e-9:
                                    debug["component_nonzero_rows"][key] = int(
                                        debug["component_nonzero_rows"].get(key, 0) or 0
                                    ) + 1

                        if len(debug["row_debug_sample"]) < 250:
                            debug["row_debug_sample"].append(row_diag)
                    except Exception as e:
                        debug["rows_dropped"] += 1
                        debug["dropped_reasons"]["row_parse_error"] = int(
                            debug["dropped_reasons"].get("row_parse_error", 0) or 0
                        ) + 1
                        if len(debug["row_debug_sample"]) < 250:
                            debug["row_debug_sample"].append(
                                {
                                    "raw_row_index": int(idx),
                                    "excluded": True,
                                    "excluded_reason": "row_parse_error",
                                    "error": str(e),
                                    "source_file": file.name,
                                }
                            )
                        logger.warning(
                            f"[FileReportLoader] Failed to parse orders row: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"[FileReportLoader] Error loading {file.name}: {e}")
                continue

        self._finance_loader_debug = debug
        return orders

    def _load_margins_data(self, target_date: Optional[date] = None) -> List[RawMarginsData]:
        """Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ РјР°СЂР¶Рё РёР· РїР°РїРєРё finance/ (margin_report)"""
        margins = []
        finance_dir = self.input_dir / "finance"

        if not finance_dir.exists():
            return margins

        for file in list(finance_dir.glob("*margin*.xlsx")) + list(finance_dir.glob("*margin*.csv")):
            try:
                logger.info(f"[FileReportLoader] Parsing margins from {file.name}")

                if file.suffix == ".xlsx":
                    df = pd.read_excel(file, sheet_name=0)
                else:
                    df = pd.read_csv(file)

                df.columns = [c.lower().strip() for c in df.columns]

                for _, row in df.iterrows():
                    try:
                        sku_id = self._get_val(row, ["sku", "Р°СЂС‚РёРєСѓР»", "nmid", "nm id"])
                        if not sku_id:
                            continue

                        cost_price = self._get_float(row, ["СЃРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊ", "cost", "cost price"])
                        if not cost_price or cost_price <= 0:
                            continue  # РџСЂРѕРїСѓСЃРєР°РµРј СЃ РЅСѓР»РµРІРѕР№ СЃРµР±РµСЃС‚РѕРёРјРѕСЃС‚СЊСЋ

                        selling_price = self._get_float(
                            row,
                            [
                                "С†РµРЅР° РїСЂРѕРґР°Р¶Рё",
                                "selling price",
                                "С†РµРЅР°",
                                "retail price",
                                "price",
                            ],
                        )
                        margin_percent = self._get_float(
                            row, ["РјР°СЂР¶Р° %", "margin %", "margin", "РјР°СЂР¶Р°"]
                        ) or 0.0

                        margins.append(
                            RawMarginsData(
                                sku_id=str(sku_id),
                                cost_price=cost_price,
                                selling_price=selling_price or 0.0,
                                margin_percent=margin_percent,
                                date=target_date or date.today(),
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"[FileReportLoader] Failed to parse margins row: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"[FileReportLoader] Error loading {file.name}: {e}")
                continue

        return margins

    def _load_returns_data(self, target_date: Optional[date] = None) -> List[RawReturnsData]:
        """Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ РІРѕР·РІСЂР°С‚РѕРІ"""
        returns = []
        # Returns РјРѕР¶РЅРѕ РЅР°Р№С‚Рё РІ funnel РёР»Рё finance СЂР°Р·РґРµР»Р°С…
        for data_dir in [
            self.input_dir / "funnel",
            self.input_dir / "finance",
        ]:
            if not data_dir.exists():
                continue

            for file in list(data_dir.glob("*.xlsx")) + list(data_dir.glob("*.csv")):
                if "return" not in file.name.lower():
                    continue

                try:
                    logger.info(f"[FileReportLoader] Parsing returns from {file.name}")

                    if file.suffix == ".xlsx":
                        df = pd.read_excel(file, sheet_name=0)
                    else:
                        df = pd.read_csv(file)

                    df.columns = [c.lower().strip() for c in df.columns]

                    for idx, row in df.iterrows():
                        try:
                            sku_id = self._get_val(row, ["sku", "Р°СЂС‚РёРєСѓР»", "nmid", "nm id"])
                            if not sku_id:
                                continue

                            returns.append(
                                RawReturnsData(
                                    return_id=str(self._get_val(row, ["id РІРѕР·РІСЂР°С‚Р°", "return id"]) or f"ret_{idx}"),
                                    order_id=str(self._get_val(row, ["id Р·Р°РєР°Р·Р°", "order id"]) or "unknown"),
                                    sku_id=str(sku_id),
                                    reason=self._get_val(
                                        row, ["РїСЂРёС‡РёРЅР°", "reason", "description", "РїСЂРёС‡РёРЅР° РІРѕР·РІСЂР°С‚Р°"]
                                    )
                                    or "unknown",
                                    revenue_lost=self._get_float(
                                        row, ["РїРѕС‚РµСЂРё", "lost revenue", "СЃСѓРјРјР°", "РґРѕС…РѕРґ РїРѕС‚РµСЂРё"]
                                    )
                                    or 0.0,
                                    date=target_date or date.today(),
                                )
                            )
                        except Exception as e:
                            logger.warning(
                                f"[FileReportLoader] Failed to parse returns row: {e}"
                            )
                            continue

                except Exception as e:
                    logger.error(
                        f"[FileReportLoader] Error loading {file.name}: {e}"
                    )
                    continue

        return returns

    def _load_ratings_data(self, target_date: Optional[date] = None) -> List[RawRatingsData]:
        """Р—Р°РіСЂСѓР¶Р°РµС‚ РґР°РЅРЅС‹Рµ СЂРµР№С‚РёРЅРіРѕРІ"""
        ratings = []

        for data_dir in [
            self.input_dir / "ads",
            self.input_dir / "funnel",
        ]:
            if not data_dir.exists():
                continue

            for file in list(data_dir.glob("*.xlsx")) + list(data_dir.glob("*.csv")):
                if "rating" not in file.name.lower() and "feedback" not in file.name.lower():
                    continue

                try:
                    logger.info(f"[FileReportLoader] Parsing ratings from {file.name}")

                    if file.suffix == ".xlsx":
                        df = pd.read_excel(file, sheet_name=0)
                    else:
                        df = pd.read_csv(file)

                    df.columns = [c.lower().strip() for c in df.columns]

                    for _, row in df.iterrows():
                        try:
                            sku_id = self._get_val(row, ["sku", "Р°СЂС‚РёРєСѓР»", "nmid", "nm id"])
                            if not sku_id:
                                continue

                            rating = self._get_float(
                                row,
                                [
                                    "СЃСЂРµРґРЅРёР№ СЂРµР№С‚РёРЅРі",
                                    "average rating",
                                    "rating",
                                    "СЃСЂРµРґРЅСЏСЏ РѕС†РµРЅРєР°",
                                ],
                            )
                            
                            # Р Р°СЃСЃС‡РёС‚Р°РµРј РєРѕР»РёС‡РµСЃС‚РІРѕ РЅРµРіР°С‚РёРІРЅС‹С… РѕС‚Р·С‹РІРѕРІ
                            review_count = int(
                                self._get_val(row, ["РѕС‚Р·С‹РІС‹", "reviews", "РєРѕР»РёС‡РµСЃС‚РІРѕ РѕС‚Р·С‹РІРѕРІ"])
                                or 0
                            )
                            
                            positive_percent = self._get_float(
                                row, ["% РїРѕР·РёС‚РёРІРЅС‹С…", "positive %", "РїСЂРѕС†РµРЅС‚ РїРѕР·РёС‚РёРІР°"]
                            ) or 0.0
                            
                            negative_reviews = int(review_count * (100 - positive_percent) / 100)

                            ratings.append(
                                RawRatingsData(
                                    sku_id=str(sku_id),
                                    rating=rating or 0.0,
                                    review_count=review_count,
                                    negative_reviews=negative_reviews,
                                    date=target_date or date.today(),
                                )
                            )
                        except Exception as e:
                            logger.warning(
                                f"[FileReportLoader] Failed to parse ratings row: {e}"
                            )
                            continue

                except Exception as e:
                    logger.error(
                        f"[FileReportLoader] Error loading {file.name}: {e}"
                    )
                    continue

        return ratings

    @staticmethod
    def _canonicalize_name(name: Any) -> str:
        text = str(name or "").strip().lower().replace("ё", "е")
        text = text.replace("№", " no ")
        text = re.sub(r"[\(\)\[\]\{\}/\\,;:%\-]+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _lookup_val(cls, row: pd.Series, aliases: List[str]) -> Optional[Any]:
        for alias in aliases:
            key = cls._canonicalize_name(alias)
            if key in row.index:
                val = row[key]
                if pd.notna(val):
                    return val
        return None

    @classmethod
    def _lookup_float(cls, row: pd.Series, aliases: List[str]) -> float:
        val = cls._lookup_val(row, aliases)
        if val is None:
            return 0.0
        try:
            return float(str(val).strip().replace(" ", "").replace(",", "."))
        except Exception:
            return 0.0

    @classmethod
    def _lookup_int(cls, row: pd.Series, aliases: List[str]) -> int:
        val = cls._lookup_val(row, aliases)
        if val is None:
            return 0
        try:
            return int(float(str(val).strip().replace(" ", "").replace(",", ".")))
        except Exception:
            return 0

    @staticmethod
    def _normalize_sku(raw: Any) -> str:
        if raw is None:
            return ""
        sku = str(raw).strip()
        if not sku:
            return ""
        if re.fullmatch(r"\d+\.0+", sku):
            sku = sku.split(".", 1)[0]
        return sku

    @staticmethod
    def _is_summary_row(row: pd.Series, operation_text: str) -> bool:
        markers = []
        for key in ("no", "тип документа", "обоснование для оплаты", "название"):
            canon = FileReportLoader._canonicalize_name(key)
            if canon in row.index and pd.notna(row[canon]):
                markers.append(str(row[canon]).strip().lower())
        joined = " ".join(markers + [str(operation_text or "").lower()])
        return ("итог" in joined) or ("всего" in joined)

    def _parse_finance_order_row(
        self,
        row: pd.Series,
        row_index: int,
        source_file: str,
        row_date: date,
    ) -> tuple[Optional[RawOrdersData], Optional[str], Dict[str, Any]]:
        sku_raw = self._lookup_val(
            row,
            [
                "Код номенклатуры",
                "Артикул WB",
                "nmId",
                "nm id",
                "nmid",
                "Артикул",
                "Артикул продавца",
                "Артикул поставщика",
                "sku",
            ],
        )
        sku_id = self._normalize_sku(sku_raw)

        document_type = str(
            self._lookup_val(
                row,
                ["Тип документа", "document type", "doc type", "doc_type_name"],
            )
            or ""
        ).strip()
        operation_basis = str(
            self._lookup_val(
                row,
                [
                    "Обоснование для оплаты",
                    "Основание оплаты",
                    "supplier_oper_name",
                    "operationTypeName",
                    "operation basis",
                ],
            )
            or ""
        ).strip()
        operation_text = " ".join(
            [x for x in [document_type, operation_basis] if str(x or "").strip()]
        ).strip()

        quantity = self._lookup_int(row, ["Кол-во", "Количество", "qty", "count"])
        gross_revenue = self._lookup_float(
            row,
            [
                "Цена розничная",
                "retail price",
                "gross revenue",
            ],
        )
        realized_revenue = self._lookup_float(
            row,
            [
                "Вайлдберриз реализовал Товар (Пр)",
                "retail_amount",
                "sale amount",
                "realized revenue",
            ],
        )
        seller_payout = self._lookup_float(
            row,
            [
                "К перечислению Продавцу за реализованный Товар",
                "К перечислению продавцу",
                "ppvz_for_pay",
                "to_pay",
                "seller payout",
            ],
        )
        commission = self._lookup_float(
            row,
            [
                "Вознаграждение Вайлдберриз (ВВ), без НДС",
                "Вознаграждение с продаж до вычета услуг поверенного, без НДС",
                "Комиссия",
                "commission",
                "комиссионный сбор",
            ],
        )
        logistics = self._lookup_float(
            row,
            [
                "Услуги по доставке товара покупателю",
                "Логистика",
                "delivery_rub",
                "logistics",
            ],
        )
        storage = self._lookup_float(row, ["Хранение", "storage", "storage_fee"])
        penalties = self._lookup_float(
            row, ["Общая сумма штрафов", "Штраф", "penalty", "fine"]
        )
        deductions = self._lookup_float(row, ["Удержания", "deductions"])
        loyalty_program = self._lookup_float(
            row,
            [
                "Стоимость участия в программе лояльности",
                "Скидка по программе софинансирования",
                "loyalty program",
            ],
        )
        loyalty_points_withheld = self._lookup_float(
            row,
            [
                "Сумма удержанная за начисленные баллы программы лояльности",
                "Компенсация скидки по программе лояльности",
                "loyalty points",
            ],
        )
        acquiring = self._lookup_float(
            row,
            [
                "Компенсация платёжных услуг/Комиссия за интеграцию платёжных сервисов",
                "Компенсация платежных услуг/Комиссия за интеграцию платежных сервисов",
                "acquiring",
                "эквайринг",
            ],
        )
        pvz_service = self._lookup_float(
            row,
            [
                "Возмещение за выдачу и возврат товаров на ПВЗ",
                "pvz service",
                "pvz",
            ],
        )
        rebill_logistic_cost = self._lookup_float(
            row,
            [
                "Возмещение издержек по перевозке/по складским операциям с товаром",
                "rebill logistic cost",
                "rebill_logistic_cost",
            ],
        )
        other_adjustments = self._lookup_float(
            row,
            [
                "Корректировка Вознаграждения Вайлдберриз (ВВ)",
                "Разовое изменение срока перечисления денежных средств",
                "other adjustments",
            ],
        )

        revenue_for_orders = (
            seller_payout
            if abs(seller_payout) > 1e-9
            else (realized_revenue if abs(realized_revenue) > 1e-9 else gross_revenue)
        )

        meaningful_components = [
            gross_revenue,
            realized_revenue,
            seller_payout,
            commission,
            logistics,
            storage,
            penalties,
            deductions,
            loyalty_program,
            loyalty_points_withheld,
            acquiring,
            pvz_service,
            rebill_logistic_cost,
            other_adjustments,
        ]
        has_meaningful_amount = any(abs(float(x or 0.0)) > 1e-9 for x in meaningful_components)
        has_operation_text = bool(str(operation_text or "").strip())
        has_sku = bool(sku_id)
        is_summary = self._is_summary_row(row, operation_text)

        diag = {
            "raw_row_index": int(row_index),
            "source_file": source_file,
            "sku_id": sku_id or None,
            "operation_type": document_type,
            "operation_basis": operation_basis,
            "excluded": False,
            "excluded_reason": None,
            "components": {
                "gross_revenue": round(gross_revenue, 2),
                "realized_revenue": round(realized_revenue, 2),
                "seller_payout": round(seller_payout, 2),
                "commission": round(commission, 2),
                "logistics": round(logistics + rebill_logistic_cost, 2),
                "storage": round(storage, 2),
                "penalties": round(penalties, 2),
                "deductions": round(deductions, 2),
                "loyalty_program": round(loyalty_program, 2),
                "loyalty_points_withheld": round(loyalty_points_withheld, 2),
                "acquiring": round(acquiring, 2),
                "pvz_service": round(pvz_service, 2),
                "other_adjustments": round(other_adjustments, 2),
            },
        }

        if is_summary:
            diag["excluded"] = True
            diag["excluded_reason"] = "summary_row"
            return None, "summary_row", diag

        if not has_meaningful_amount and not has_operation_text and not has_sku and quantity == 0:
            diag["excluded"] = True
            diag["excluded_reason"] = "empty_financial_row"
            return None, "empty_financial_row", diag

        order_id = str(
            self._lookup_val(
                row,
                ["id заказа", "Номер заказа", "order id", "rrd_id", "rrdid"],
            )
            or f"ord_{source_file}_{row_index}"
        )
        ad_id = self._lookup_val(row, ["id рекламы", "ad id", "campaign id"])
        if ad_id is not None:
            ad_id = str(ad_id).strip() or None

        parsed = RawOrdersData(
            order_id=order_id,
            sku_id=str(sku_id or ""),
            ad_id=ad_id,
            quantity=int(quantity or 0),
            revenue=float(revenue_for_orders or 0.0),
            commission=float(commission or 0.0),
            date=row_date,
            operation_type=document_type,
            operation_basis=operation_basis,
            document_type=document_type,
            gross_revenue=float(gross_revenue or 0.0),
            realized_revenue=float(realized_revenue or 0.0),
            seller_payout=float(seller_payout or 0.0),
            logistics=float(logistics or 0.0),
            storage=float(storage or 0.0),
            penalties=float(penalties or 0.0),
            deductions=float(deductions or 0.0),
            loyalty_program=float(loyalty_program or 0.0),
            loyalty_points_withheld=float(loyalty_points_withheld or 0.0),
            acquiring=float(acquiring or 0.0),
            pvz_service=float(pvz_service or 0.0),
            other_adjustments=float(other_adjustments or 0.0),
            rebill_logistic_cost=float(rebill_logistic_cost or 0.0),
            source_file=source_file,
            raw_row_index=int(row_index),
            is_valid_sku=bool(sku_id) and str(sku_id).strip().lower() not in {"0", "0.0", "nan", "none"},
            excluded_reason="",
        )
        return parsed, None, diag

    @staticmethod
    def _get_val(row, possible_names: List[str]) -> Optional[str]:
        """РџРѕР»СѓС‡Р°РµС‚ Р·РЅР°С‡РµРЅРёРµ РёР· СЃС‚СЂРѕРєРё РїРѕ РѕРґРЅРѕРјСѓ РёР· РІРѕР·РјРѕР¶РЅС‹С… РЅР°Р·РІР°РЅРёР№ РєРѕР»РѕРЅРѕРє"""
        for name in possible_names:
            if name in row.index:
                val = row[name]
                if pd.notna(val):
                    return str(val).strip()
        return None

    @staticmethod
    def _get_float(row, possible_names: List[str]) -> Optional[float]:
        """РџРѕР»СѓС‡Р°РµС‚ С‡РёСЃР»РѕРІРѕРµ Р·РЅР°С‡РµРЅРёРµ РёР· СЃС‚СЂРѕРєРё"""
        val = FileReportLoader._get_val(row, possible_names)
        if val:
            try:
                # Replace comma with dot for parsing
                val = str(val).replace(",", ".")
                return float(val)
            except (ValueError, TypeError):
                return None
        return None


