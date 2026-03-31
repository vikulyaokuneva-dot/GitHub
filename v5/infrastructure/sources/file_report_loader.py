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
        ads_task = asyncio.to_thread(self._load_ads_data)
        orders_task = asyncio.to_thread(self._load_orders_data)
        margins_task = asyncio.to_thread(self._load_margins_data)
        returns_task = asyncio.to_thread(self._load_returns_data)
        ratings_task = asyncio.to_thread(self._load_ratings_data)

        ads, orders, margins, returns, ratings = await asyncio.gather(
            ads_task, orders_task, margins_task, returns_task, ratings_task
        )

        bundle = RawDataBundle(
            source="file_report",
            cabinet_id=cabinet_ctx.cabinet.id,
            loaded_date=datetime.now().date(),
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

    def _load_ads_data(self) -> List[RawAdsData]:
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
                        sku = self._get_val(row, ["sku", "артикул", "nmid"])
                        if not sku:
                            continue

                        ads.append(
                            RawAdsData(
                                sku=int(sku),
                                adv_name=self._get_val(
                                    row,
                                    [
                                        "название",
                                        "наименование",
                                        "adv name",
                                    ],
                                )
                                or "Unknown",
                                adv_type=self._get_val(
                                    row, ["тип объявления", "campaign type"]
                                )
                                or "unknown",
                                daily_budget=self._get_float(row, ["дневной бюджет"])
                                or 0,
                                views=int(self._get_val(row, ["просмотры", "views"]) or 0),
                                clicks=int(
                                    self._get_val(row, ["клики", "clicks"]) or 0
                                ),
                                ctr=self._get_float(row, ["ctr", "ctr %"]) or 0,
                                spend=self._get_float(row, ["трата", "расход", "spend"])
                                or 0,
                                cpc=self._get_float(row, ["cpc"]) or 0,
                                conversions=int(
                                    self._get_val(row, ["конверсии", "conversions"])
                                    or 0
                                ),
                                orders=int(self._get_val(row, ["заказы", "orders"]) or 0),
                                revenue=self._get_float(
                                    row, ["доход", "выручка", "revenue"]
                                )
                                or 0,
                                roas=self._get_float(
                                    row, ["roas", "roi", "рентабельность"]
                                )
                                or 0,
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

    def _load_orders_data(self) -> List[RawOrdersData]:
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

                for _, row in df.iterrows():
                    try:
                        sku = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                        if not sku:
                            continue

                        orders.append(
                            RawOrdersData(
                                sku=int(sku),
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
                                or 0,
                                commission=self._get_float(
                                    row, ["комиссия", "commission", "комиссионный сбор"]
                                )
                                or 0,
                                commission_percent=self._get_float(
                                    row, ["процент комиссии", "commission %"]
                                )
                                or 0,
                                fbo_count=int(self._get_val(row, ["fbo"]) or 0),
                                fbs_count=int(self._get_val(row, ["fbs"]) or 0),
                                return_count=int(
                                    self._get_val(
                                        row,
                                        ["возвраты", "returns", "количество возвратов"]
                                    )
                                    or 0
                                ),
                                average_price=self._get_float(
                                    row, ["средняя цена", "average price"]
                                )
                                or 0,
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

    def _load_margins_data(self) -> List[RawMarginsData]:
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
                        sku = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                        if not sku:
                            continue

                        cost_price = self._get_float(row, ["себестоимость", "cost"])
                        if not cost_price or cost_price <= 0:
                            continue  # Пропускаем с нулевой себестоимостью

                        selling_price = self._get_float(
                            row,
                            [
                                "цена продажи",
                                "selling price",
                                "цена",
                                "retail price",
                            ],
                        )
                        margin_percent = self._get_float(
                            row, ["маржа", "margin %", "margin"]
                        )

                        margins.append(
                            RawMarginsData(
                                sku=int(sku),
                                cost_price=cost_price,
                                selling_price=selling_price or 0,
                                margin_percent=margin_percent or 0,
                                margin_rub=self._get_float(
                                    row, ["маржа руб", "margin rub"]
                                )
                                or 0,
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

    def _load_returns_data(self) -> List[RawReturnsData]:
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

                    for _, row in df.iterrows():
                        try:
                            sku = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                            if not sku:
                                continue

                            returns.append(
                                RawReturnsData(
                                    sku=int(sku),
                                    return_count=int(
                                        self._get_val(row, ["количество", "count"])
                                        or 0
                                    ),
                                    return_reason=self._get_val(
                                        row, ["причина", "reason", "description"]
                                    )
                                    or "unknown",
                                    lost_revenue=self._get_float(
                                        row, ["потери", "lost revenue", "сумма"]
                                    )
                                    or 0,
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

    def _load_ratings_data(self) -> List[RawRatingsData]:
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
                            sku = self._get_val(row, ["sku", "артикул", "nmid", "nm id"])
                            if not sku:
                                continue

                            ratings.append(
                                RawRatingsData(
                                    sku=int(sku),
                                    average_rating=self._get_float(
                                        row,
                                        [
                                            "средний рейтинг",
                                            "average rating",
                                            "rating",
                                        ],
                                    )
                                    or 0,
                                    review_count=int(
                                        self._get_val(row, ["отзывы", "reviews"])
                                        or 0
                                    ),
                                    positive_percent=self._get_float(
                                        row, ["% позитивных", "positive %"]
                                    )
                                    or 0,
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

