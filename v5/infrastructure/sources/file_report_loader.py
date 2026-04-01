"""FileReportLoader - загрузка данных из Excel/CSV отчётов ВБ"""

import asyncio
import logging
from pathlib import Path
from datetime import date, datetime
from typing import Optional, List
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
    """Загружает данные из Excel/CSV отчётов ВБ"""

    def __init__(self):
        self.input_dir = Path("v5/audit/input")

    async def load_data(
        self, cabinet_ctx: CabinetContext, target_date: Optional[date] = None
    ) -> RawDataBundle:
        """
        Загружает данные из файлов отчётов.

        Args:
            cabinet_ctx: Контекст кабинета с путями
            target_date: Конкретная дата (опционально)

        Returns:
            RawDataBundle со всеми данными из файлов
        """
        logger.info(
            f"[FileReportLoader] Loading data from {self.input_dir} for {cabinet_ctx.cabinet.id}"
        )

        # Параллельная загрузка из всех папок
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
        )

        logger.info(
            f"[FileReportLoader] ✅ Loaded: "
            f"ads={len(ads)}, orders={len(orders)}, "
            f"margins={len(margins)}, returns={len(returns)}, "
            f"ratings={len(ratings)}"
        )

        return bundle

    def _load_ads_data(self, target_date: Optional[date] = None) -> List[RawAdsData]:
        """Загружает данные объявлений из папки ads/"""
        ads = []
        ads_dir = self.input_dir / "ads"

        if not ads_dir.exists():
            logger.warning(f"[FileReportLoader] ads/ directory not found")
            return ads

        # Ищем файлы ads_stats, full_stats
        for file in list(ads_dir.glob("*stats*.xlsx")) + list(ads_dir.glob("*stats*.csv")):
            try:
                logger.info(f"[FileReportLoader] Parsing ads from {file.name}")

                if file.suffix == ".xlsx":
                    df = pd.read_excel(file, sheet_name=0)
                else:
                    df = pd.read_csv(file)

                # Нормализуем названия колонок
                df.columns = [c.lower().strip() for c in df.columns]

                # Парсим объявления
                for _, row in df.iterrows():
                    try:
                        ad_id = self._get_val(row, ["id адреса", "campaign id", "id"])
                        if not ad_id:
                            continue
                        
                        sku = self._get_val(row, ["sku", "артикул", "nmid"])
                        sku_ids = [str(sku)] if sku else []

                        ads.append(
                            RawAdsData(
                                ad_id=str(ad_id),
                                name=self._get_val(
                                    row,
                                    [
                                        "название",
                                        "наименование",
                                        "adv name",
                                        "name",
                                    ],
                                )
                                or "Unknown",
                                sku_ids=sku_ids,
                                budget_daily=self._get_float(row, ["дневной бюджет", "daily budget"])
                                or 0.0,
                                status=self._get_val(
                                    row, ["статус", "status"]
                                )
                                or "active",
                                views=int(self._get_val(row, ["просмотры", "views", "impressions"]) or 0),
                                clicks=int(
                                    self._get_val(row, ["клики", "clicks"]) or 0
                                ),
                                spend=self._get_float(row, ["трата", "расход", "spend", "cost"])
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
        """Загружает данные заказов из папки finance/"""
        orders = []
        finance_dir = self.input_dir / "finance"

        if not finance_dir.exists():
            logger.warning(f"[FileReportLoader] finance/ directory not found")
            return orders

        # Ищем отчет по продажам (report_detail или просто все xlsx файлы)
        for file in list(finance_dir.glob("*.xlsx")) + list(finance_dir.glob("*.csv")):
            if "margin" in file.name.lower():
                continue  # Пропускаем margin отчеты
                
            try:
                logger.info(f"[FileReportLoader] Parsing orders from {file.name}")

                if file.suffix == ".xlsx":
                    df = pd.read_excel(file, sheet_name=0)
                else:
                    df = pd.read_csv(file)

                df.columns = [c.lower().strip() for c in df.columns]

                for idx, row in df.iterrows():
                    try:
                        sku_id = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                        if not sku_id:
                            continue

                        orders.append(
                            RawOrdersData(
                                order_id=str(self._get_val(row, ["id заказа", "order id", "номер заказа"]) or f"ord_{idx}"),
                                sku_id=str(sku_id),
                                ad_id=self._get_val(row, ["id рекламы", "ad id", "campaign id"]),
                                quantity=int(
                                    self._get_val(row, ["количество", "qty", "кол-во"]) or 0
                                ),
                                revenue=self._get_float(
                                    row,
                                    [
                                        "выручка",
                                        "доход",
                                        "revenue",
                                        "сумма продаж",
                                    ],
                                )
                                or 0.0,
                                commission=self._get_float(
                                    row, ["комиссия", "commission", "комиссионный сбор"]
                                )
                                or 0.0,
                                date=target_date or date.today(),
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"[FileReportLoader] Failed to parse orders row: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"[FileReportLoader] Error loading {file.name}: {e}")
                continue

        return orders

    def _load_margins_data(self, target_date: Optional[date] = None) -> List[RawMarginsData]:
        """Загружает данные маржи из папки finance/ (margin_report)"""
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
                        sku_id = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                        if not sku_id:
                            continue

                        cost_price = self._get_float(row, ["себестоимость", "cost", "cost price"])
                        if not cost_price or cost_price <= 0:
                            continue  # Пропускаем с нулевой себестоимостью

                        selling_price = self._get_float(
                            row,
                            [
                                "цена продажи",
                                "selling price",
                                "цена",
                                "retail price",
                                "price",
                            ],
                        )
                        margin_percent = self._get_float(
                            row, ["маржа %", "margin %", "margin", "маржа"]
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
        """Загружает данные возвратов"""
        returns = []
        # Returns можно найти в funnel или finance разделах
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
                            sku_id = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                            if not sku_id:
                                continue

                            returns.append(
                                RawReturnsData(
                                    return_id=str(self._get_val(row, ["id возврата", "return id"]) or f"ret_{idx}"),
                                    order_id=str(self._get_val(row, ["id заказа", "order id"]) or "unknown"),
                                    sku_id=str(sku_id),
                                    reason=self._get_val(
                                        row, ["причина", "reason", "description", "причина возврата"]
                                    )
                                    or "unknown",
                                    revenue_lost=self._get_float(
                                        row, ["потери", "lost revenue", "сумма", "доход потери"]
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
        """Загружает данные рейтингов"""
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
                            sku_id = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                            if not sku_id:
                                continue

                            rating = self._get_float(
                                row,
                                [
                                    "средний рейтинг",
                                    "average rating",
                                    "rating",
                                    "средняя оценка",
                                ],
                            )
                            
                            # Рассчитаем количество негативных отзывов
                            review_count = int(
                                self._get_val(row, ["отзывы", "reviews", "количество отзывов"])
                                or 0
                            )
                            
                            positive_percent = self._get_float(
                                row, ["% позитивных", "positive %", "процент позитива"]
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
    def _get_val(row, possible_names: List[str]) -> Optional[str]:
        """Получает значение из строки по одному из возможных названий колонок"""
        for name in possible_names:
            if name in row.index:
                val = row[name]
                if pd.notna(val):
                    return str(val).strip()
        return None

    @staticmethod
    def _get_float(row, possible_names: List[str]) -> Optional[float]:
        """Получает числовое значение из строки"""
        val = FileReportLoader._get_val(row, possible_names)
        if val:
            try:
                # Replace comma with dot for parsing
                val = str(val).replace(",", ".")
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

