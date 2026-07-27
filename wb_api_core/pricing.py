from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


MONEY_QUANTUM = Decimal("0.01")
PERCENT_QUANTUM = Decimal("0.01")
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
PRICE_SOURCE = "goods_filter_v2"
FBS_ORDER_SOURCE = "fbs_orders_v3"
FINANCE_SOURCE = "finance_detailed_api"


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def money(value: Any) -> Decimal | None:
    parsed = decimal_or_none(value)
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) if parsed is not None else None


def percent(value: Any) -> Decimal | None:
    parsed = decimal_or_none(value)
    return parsed.quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP) if parsed is not None else None


def cents_to_money(value: Any) -> Decimal | None:
    parsed = decimal_or_none(value)
    if parsed is None:
        return None
    return (parsed / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def discount_percent(reference_price: Any, discounted_price: Any) -> Decimal | None:
    reference = money(reference_price)
    discounted = money(discounted_price)
    if reference is None or discounted is None or reference <= 0:
        return None
    return ((reference - discounted) / reference * Decimal("100")).quantize(
        PERCENT_QUANTUM,
        rounding=ROUND_HALF_UP,
    )


def _iso_utc(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def normalize_goods_prices(rows_raw: Iterable[dict[str, Any]], *, captured_at: str) -> list[dict[str, Any]]:
    """Collapse the size-level price response into one deterministic nm_id snapshot."""
    normalized: list[dict[str, Any]] = []
    raw_rows = list(rows_raw)
    if not raw_rows:
        return normalized
    captured_at_utc = _iso_utc(captured_at)
    if not captured_at_utc:
        raise ValueError("captured_at must be an ISO timestamp")

    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        nm_id = raw.get("nmID", raw.get("nmId", raw.get("nm_id")))
        if nm_id in (None, ""):
            continue
        raw_sizes = raw.get("sizes")
        sizes: list[Any] = raw_sizes if isinstance(raw_sizes, list) else []
        candidates: list[tuple[Decimal, str, dict[str, Any]]] = []
        for size in sizes:
            if not isinstance(size, dict):
                continue
            discounted = money(size.get("discountedPrice"))
            base = money(size.get("price"))
            sort_price = discounted if discounted is not None else base
            if sort_price is None:
                continue
            candidates.append((sort_price, str(size.get("sizeID", "")), size))
        candidates.sort(key=lambda item: (item[0], item[1]))
        selected = candidates[0][2] if candidates else {}

        base_price = money(selected.get("price"))
        seller_discount = percent(raw.get("discount"))
        seller_discounted = money(selected.get("discountedPrice"))
        club_discounted = money(selected.get("clubDiscountedPrice"))
        distinct_prices = {
            (
                _decimal_text(money(item[2].get("price"))),
                _decimal_text(money(item[2].get("discountedPrice"))),
                _decimal_text(money(item[2].get("clubDiscountedPrice"))),
            )
            for item in candidates
        }
        if not candidates:
            quality = "missing_price"
        elif len(distinct_prices) > 1:
            quality = "partial_multiple_size_prices"
        else:
            quality = "complete"
        normalized.append(
            {
                "nm_id": str(nm_id),
                "captured_at": captured_at_utc,
                "seller_base_price": _decimal_text(base_price),
                "seller_discount_percent": _decimal_text(seller_discount),
                "seller_discounted_price": _decimal_text(seller_discounted),
                "club_discounted_price": _decimal_text(club_discounted),
                "buyer_price_before_wallet": None,
                "buyer_final_price": None,
                "platform_discount_percent": None,
                "wallet_discount_percent": None,
                "source": PRICE_SOURCE,
                "data_quality_status": quality,
                "api_version": "v2",
            }
        )
    return normalized


def normalize_fbs_order_prices(rows_raw: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in rows_raw:
        if not isinstance(raw, dict):
            continue
        nm_id = raw.get("nmId", raw.get("nmID", raw.get("nm_id")))
        order_id = raw.get("id", raw.get("orderId", raw.get("orderID")))
        created_at = _iso_utc(raw.get("createdAt", raw.get("created_at")))
        if nm_id in (None, "") or order_id in (None, "") or not created_at:
            continue
        before_wallet = cents_to_money(raw.get("convertedPrice"))
        final_price = cents_to_money(raw.get("convertedFinalPrice"))
        wallet_discount = discount_percent(before_wallet, final_price)
        quality = "complete" if before_wallet is not None and final_price is not None else "missing_buyer_price"
        normalized.append(
            {
                "nm_id": str(nm_id),
                "order_id": str(order_id),
                "order_created_at": created_at,
                "captured_at": created_at,
                "buyer_price_before_wallet": _decimal_text(before_wallet),
                "buyer_final_price": _decimal_text(final_price),
                "wallet_discount_percent": _decimal_text(wallet_discount),
                "source": FBS_ORDER_SOURCE,
                "data_quality_status": quality,
                "api_version": "v3",
            }
        )
    return normalized


@dataclass(frozen=True)
class PriceSnapshotStore:
    path: Path

    @classmethod
    def for_seller(cls, *, repo_root: str, seller_id: str) -> "PriceSnapshotStore":
        return cls(Path(repo_root) / "cabinets" / seller_id / "data" / "product_prices.sqlite3")

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path))
        connection.row_factory = sqlite3.Row
        return connection

    def migrate(self) -> None:
        migration = Path(__file__).with_name("migrations") / "001_product_price_snapshot_up.sql"
        with self._connect() as connection:
            connection.executescript(migration.read_text(encoding="utf-8"))

    def rollback(self) -> None:
        migration = Path(__file__).with_name("migrations") / "001_product_price_snapshot_down.sql"
        with self._connect() as connection:
            connection.executescript(migration.read_text(encoding="utf-8"))

    def upsert_current_prices(self, *, seller_id: str, rows: Iterable[dict[str, Any]]) -> None:
        self.migrate()
        with self._connect() as connection:
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO product_price_snapshot (
                        seller_id, nm_id, captured_at, seller_base_price,
                        seller_discount_percent, seller_discounted_price,
                        club_discounted_price, buyer_price_before_wallet,
                        buyer_final_price, platform_discount_percent,
                        wallet_discount_percent, source, data_quality_status
                        , order_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(seller_id, nm_id, captured_at, source, order_id) DO UPDATE SET
                        seller_base_price=excluded.seller_base_price,
                        seller_discount_percent=excluded.seller_discount_percent,
                        seller_discounted_price=excluded.seller_discounted_price,
                        club_discounted_price=excluded.club_discounted_price,
                        data_quality_status=excluded.data_quality_status
                    """,
                    (
                        seller_id,
                        str(row.get("nm_id") or ""),
                        str(row.get("captured_at") or ""),
                        row.get("seller_base_price"),
                        row.get("seller_discount_percent"),
                        row.get("seller_discounted_price"),
                        row.get("club_discounted_price"),
                        None,
                        None,
                        None,
                        None,
                        PRICE_SOURCE,
                        str(row.get("data_quality_status") or "missing_price"),
                        "",
                    ),
                )

    def _latest_product_before(
        self,
        connection: sqlite3.Connection,
        *,
        seller_id: str,
        nm_id: str,
        order_created_at: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT * FROM product_price_snapshot
            WHERE seller_id = ? AND nm_id = ? AND source = ? AND captured_at <= ?
            ORDER BY captured_at DESC LIMIT 1
            """,
            (seller_id, nm_id, PRICE_SOURCE, order_created_at),
        ).fetchone()

    def upsert_fbs_orders(self, *, seller_id: str, rows: Iterable[dict[str, Any]]) -> None:
        self.migrate()
        with self._connect() as connection:
            for row in rows:
                nm_id = str(row.get("nm_id") or "")
                order_created_at = str(row.get("order_created_at") or "")
                if not nm_id or not order_created_at:
                    continue
                product = self._latest_product_before(
                    connection,
                    seller_id=seller_id,
                    nm_id=nm_id,
                    order_created_at=order_created_at,
                )
                seller_discounted = product["seller_discounted_price"] if product is not None else None
                platform_discount = discount_percent(seller_discounted, row.get("buyer_price_before_wallet"))
                quality = str(row.get("data_quality_status") or "missing_buyer_price")
                if product is None:
                    quality = "missing_historical_seller_snapshot"
                connection.execute(
                    """
                    INSERT INTO product_price_snapshot (
                        seller_id, nm_id, captured_at, seller_base_price,
                        seller_discount_percent, seller_discounted_price,
                        club_discounted_price, buyer_price_before_wallet,
                        buyer_final_price, platform_discount_percent,
                        wallet_discount_percent, source, data_quality_status
                        , order_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(seller_id, nm_id, captured_at, source, order_id) DO UPDATE SET
                        buyer_price_before_wallet=excluded.buyer_price_before_wallet,
                        buyer_final_price=excluded.buyer_final_price,
                        platform_discount_percent=excluded.platform_discount_percent,
                        wallet_discount_percent=excluded.wallet_discount_percent,
                        data_quality_status=excluded.data_quality_status
                    """,
                    (
                        seller_id,
                        nm_id,
                        order_created_at,
                        product["seller_base_price"] if product is not None else None,
                        product["seller_discount_percent"] if product is not None else None,
                        seller_discounted,
                        product["club_discounted_price"] if product is not None else None,
                        row.get("buyer_price_before_wallet"),
                        row.get("buyer_final_price"),
                        _decimal_text(platform_discount),
                        row.get("wallet_discount_percent"),
                        FBS_ORDER_SOURCE,
                        quality,
                        str(row.get("order_id") or ""),
                    ),
                )

    def rows(self, *, seller_id: str) -> list[dict[str, Any]]:
        self.migrate()
        with self._connect() as connection:
            result = connection.execute(
                """
                SELECT * FROM product_price_snapshot
                WHERE seller_id = ?
                ORDER BY captured_at, nm_id, source
                """,
                (seller_id,),
            ).fetchall()
        return [dict(row) for row in result]


def _average(values: Iterable[Any], *, quantum: Decimal) -> Decimal | None:
    parsed = [decimal_or_none(value) for value in values]
    present = [value for value in parsed if value is not None]
    if not present:
        return None
    return (sum(present, Decimal("0")) / Decimal(len(present))).quantize(quantum, rounding=ROUND_HALF_UP)


def _local_date(iso_timestamp: str) -> str | None:
    normalized = _iso_utc(iso_timestamp)
    if not normalized:
        return None
    return datetime.fromisoformat(normalized).astimezone(MOSCOW_TZ).date().isoformat()


def build_price_analytics(
    *,
    seller_id: str,
    operational_date: str,
    store_rows: Iterable[dict[str, Any]],
    finance_rows: Iterable[dict[str, Any]],
    funnel_rows: Iterable[dict[str, Any]] = (),
    sales_rows: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    all_rows = [dict(row) for row in store_rows if isinstance(row, dict)]
    current_product: dict[str, dict[str, Any]] = {}
    operational_product: dict[str, dict[str, Any]] = {}
    previous_product: dict[str, dict[str, Any]] = {}
    product_history: dict[str, list[dict[str, Any]]] = {}
    day_orders: dict[str, list[dict[str, Any]]] = {}

    for row in all_rows:
        nm_id = str(row.get("nm_id") or "")
        local_day = _local_date(str(row.get("captured_at") or ""))
        if not nm_id or not local_day:
            continue
        if row.get("source") == PRICE_SOURCE:
            product_history.setdefault(nm_id, []).append(row)
        elif row.get("source") == FBS_ORDER_SOURCE and local_day == operational_date:
            day_orders.setdefault(nm_id, []).append(row)

    for nm_id, history in product_history.items():
        ordered = sorted(history, key=lambda row: str(row.get("captured_at") or ""))
        current_product[nm_id] = ordered[-1]
        operational_rows = [
            row
            for row in ordered
            if (_local_date(str(row.get("captured_at") or "")) or "") == operational_date
        ]
        if operational_rows:
            operational_product[nm_id] = operational_rows[-1]
        current_day = _local_date(str(ordered[-1].get("captured_at") or ""))
        previous_day = None
        if current_day:
            previous_day = (
                datetime.strptime(current_day, "%Y-%m-%d").date() - timedelta(days=1)
            ).isoformat()
        prior_days = [
            row
            for row in ordered[:-1]
            if (_local_date(str(row.get("captured_at") or "")) or "") == str(previous_day or "")
        ]
        if prior_days:
            previous_product[nm_id] = prior_days[-1]

    funnel_fallback_by_nm: dict[str, dict[str, Decimal]] = {}
    for row in funnel_rows:
        if not isinstance(row, dict):
            continue
        nm_id = str(row.get("nm_id") or row.get("nmId") or "")
        row_date = str(row.get("date") or operational_date)
        if not nm_id or row_date != operational_date:
            continue
        if not bool(row.get("buyout_count_confirmed", False)):
            continue
        if not bool(row.get("buyout_sum_confirmed", False)):
            continue
        buyouts = decimal_or_none(row.get("buyouts", row.get("buyout_count")))
        buyout_sum = money(row.get("buyout_sum"))
        if buyouts is None or buyouts <= 0 or buyout_sum is None or buyout_sum <= 0:
            continue
        bucket = funnel_fallback_by_nm.setdefault(
            nm_id,
            {"buyouts": Decimal("0"), "buyout_sum": Decimal("0")},
        )
        bucket["buyouts"] += buyouts
        bucket["buyout_sum"] += buyout_sum

    sales_fallback_by_nm: dict[str, dict[str, Decimal]] = {}
    for row in sales_rows:
        if not isinstance(row, dict):
            continue
        nm_id = str(row.get("nm_id") or row.get("nmId") or "")
        row_date = str(row.get("date") or "")
        if not nm_id or row_date != operational_date:
            continue
        if not bool(row.get("quantity_confirmed", False)):
            continue
        if not bool(row.get("amount_confirmed", False)):
            continue
        quantity = decimal_or_none(row.get("quantity"))
        amount = money(row.get("amount"))
        if quantity is None or quantity <= 0 or amount is None or amount <= 0:
            continue
        bucket = sales_fallback_by_nm.setdefault(
            nm_id,
            {"buyouts": Decimal("0"), "buyout_sum": Decimal("0")},
        )
        bucket["buyouts"] += quantity
        bucket["buyout_sum"] += amount

    # The sales endpoint is the preferred fallback because each row represents
    # a factual sale. Funnel totals remain usable only when their count and sum
    # semantics were both explicitly confirmed.
    fallback_by_nm = dict(funnel_fallback_by_nm)
    fallback_by_nm.update(sales_fallback_by_nm)

    finance_platform_by_nm: dict[str, list[Decimal]] = {}
    finance_spp_by_nm: dict[str, list[Decimal]] = {}
    for row in finance_rows:
        if not isinstance(row, dict) or str(row.get("row_group") or "") != "sale":
            continue
        nm_id = str(row.get("nm_id") or "")
        finance_platform = percent(row.get("platform_discount_percent_finance"))
        finance_spp = percent(row.get("spp_component_percent_finance"))
        if nm_id and finance_platform is not None:
            finance_platform_by_nm.setdefault(nm_id, []).append(finance_platform)
        if nm_id and finance_spp is not None:
            finance_spp_by_nm.setdefault(nm_id, []).append(finance_spp)

    sku_ids = sorted(
        set(current_product)
        | set(day_orders)
        | set(fallback_by_nm)
        | set(finance_platform_by_nm)
        | set(finance_spp_by_nm),
        key=lambda item: (len(item), item),
    )
    sku_rows: list[dict[str, Any]] = []
    for nm_id in sku_ids:
        current = current_product.get(nm_id, {})
        previous = previous_product.get(nm_id, {})
        orders = day_orders.get(nm_id, [])
        complete_orders = [
            row
            for row in orders
            if money(row.get("buyer_price_before_wallet")) is not None
            and money(row.get("buyer_final_price")) is not None
        ]
        platform = _average(
            (row.get("platform_discount_percent") for row in complete_orders),
            quantum=PERCENT_QUANTUM,
        )
        wallet = _average(
            (row.get("wallet_discount_percent") for row in complete_orders),
            quantum=PERCENT_QUANTUM,
        )
        before_wallet = _average(
            (row.get("buyer_price_before_wallet") for row in complete_orders),
            quantum=MONEY_QUANTUM,
        )
        final_price = _average(
            (row.get("buyer_final_price") for row in complete_orders),
            quantum=MONEY_QUANTUM,
        )
        buyer_price_source = "fbs_converted_price" if complete_orders else "unavailable"
        buyer_units = Decimal(len(complete_orders))
        buyer_final_total = Decimal("0")
        for order_row in complete_orders:
            order_final_price = money(order_row.get("buyer_final_price"))
            if order_final_price is not None:
                buyer_final_total += order_final_price
        buyer_final_total = buyer_final_total.quantize(MONEY_QUANTUM)
        fallback = fallback_by_nm.get(nm_id)
        if before_wallet is None and final_price is None and fallback:
            fallback_count = fallback["buyouts"]
            fallback_sum = fallback["buyout_sum"]
            fallback_price = (fallback_sum / fallback_count).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            before_wallet = fallback_price
            final_price = fallback_price
            buyer_final_total = fallback_sum.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            buyer_units = fallback_count
            buyer_price_source = "sales_funnel_fallback"
        finance_exact_platform = _average(
            finance_platform_by_nm.get(nm_id, []),
            quantum=PERCENT_QUANTUM,
        )
        finance_spp_component = _average(
            finance_spp_by_nm.get(nm_id, []),
            quantum=PERCENT_QUANTUM,
        )
        finance_reference = (
            finance_exact_platform
            if finance_exact_platform is not None
            else finance_spp_component
        )
        finance_reference_type = (
            "platform_discount_percent"
            if finance_exact_platform is not None
            else ("spp_component_ppvz_spp_prc" if finance_spp_component is not None else "unavailable")
        )
        previous_orders = [
            row
            for row in all_rows
            if str(row.get("nm_id") or "") == nm_id
            and row.get("source") == FBS_ORDER_SOURCE
            and (_local_date(str(row.get("captured_at") or "")) or "") < operational_date
        ]
        previous_platform = _average(
            (row.get("platform_discount_percent") for row in previous_orders),
            quantum=PERCENT_QUANTUM,
        )
        seller_base = money(current.get("seller_base_price"))
        seller_discounted = money(current.get("seller_discounted_price"))
        operational_seller_discounted = money(
            operational_product.get(nm_id, {}).get("seller_discounted_price")
        )
        if (
            not complete_orders
            and fallback
            and operational_seller_discounted is not None
            and before_wallet is not None
        ):
            platform = discount_percent(operational_seller_discounted, before_wallet)
        delta = (
            (platform - previous_platform).quantize(PERCENT_QUANTUM, rounding=ROUND_HALF_UP)
            if platform is not None and previous_platform is not None
            else None
        )
        previous_seller = money(previous.get("seller_discounted_price"))
        seller_delta = (
            seller_discounted - previous_seller
            if seller_discounted is not None and previous_seller is not None
            else None
        )
        previous_buyer = _average((row.get("buyer_final_price") for row in previous_orders), quantum=MONEY_QUANTUM)
        buyer_delta = final_price - previous_buyer if final_price is not None and previous_buyer is not None else None
        reserve = None
        if delta is not None and delta > 0 and seller_discounted is not None:
            reserve = (seller_discounted * min(delta, Decimal("5")) / Decimal("100")).quantize(
                MONEY_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
        if finance_reference is None:
            reconciliation = "unavailable"
        elif platform is None:
            reconciliation = "no_order_discount_data"
        elif abs(platform - finance_reference) <= Decimal("0.50"):
            reconciliation = "matched"
        else:
            reconciliation = "mismatch"
        quality_values = {str(row.get("data_quality_status") or "") for row in orders}
        quality = str(current.get("data_quality_status") or "")
        if quality_values and any(value != "complete" for value in quality_values):
            quality = "partial"
        if not quality:
            quality = "missing_price"
        sku_rows.append(
            {
                "nm_id": nm_id,
                "seller_base_price": _decimal_text(seller_base),
                "seller_price": _decimal_text(seller_discounted),
                "seller_discount_percent": current.get("seller_discount_percent"),
                "seller_discounted_price": _decimal_text(seller_discounted),
                "seller_snapshot_date": (
                    _local_date(str(operational_product.get(nm_id, {}).get("captured_at") or ""))
                    if operational_product.get(nm_id)
                    else None
                ),
                "club_discounted_price": current.get("club_discounted_price"),
                "buyer_price_before_wallet": _decimal_text(before_wallet),
                "buyer_final_price": _decimal_text(final_price),
                "buyer_final_total": (
                    _decimal_text(buyer_final_total)
                    if complete_orders or fallback
                    else None
                ),
                "buyer_price_source": buyer_price_source,
                "buyer_price_units": _decimal_text(buyer_units) if buyer_units > 0 else None,
                "platform_discount_percent": _decimal_text(platform),
                "wallet_discount_percent": _decimal_text(wallet),
                "platform_discount_change_day": _decimal_text(delta),
                "seller_price_change_day": _decimal_text(money(seller_delta)),
                "buyer_price_change_day": _decimal_text(money(buyer_delta)),
                "potential_price_increase_reserve": _decimal_text(reserve),
                "finance_discount_reference_percent": _decimal_text(finance_reference),
                "finance_discount_reference_type": finance_reference_type,
                "finance_discount_reconciliation": reconciliation,
                "fbs_orders_count": len(orders),
                "source": f"{PRICE_SOURCE}+{buyer_price_source}",
                "data_quality_status": quality,
            }
        )

    fbs_orders_count = sum(len(rows) for rows in day_orders.values())
    fbs_orders_with_price_count = sum(
        1
        for rows in day_orders.values()
        for row in rows
        if money(row.get("buyer_price_before_wallet")) is not None
        and money(row.get("buyer_final_price")) is not None
    )
    order_total = Decimal("0")
    for nm_id in set(day_orders) | set(fallback_by_nm):
        priced_fbs_rows = [
            money(row.get("buyer_final_price"))
            for row in day_orders.get(nm_id, [])
            if money(row.get("buyer_price_before_wallet")) is not None
            and money(row.get("buyer_final_price")) is not None
        ]
        if priced_fbs_rows:
            order_total += sum(
                (value for value in priced_fbs_rows if value is not None),
                Decimal("0"),
            )
        elif nm_id in fallback_by_nm:
            order_total += fallback_by_nm[nm_id]["buyout_sum"]
    order_total = order_total.quantize(MONEY_QUANTUM)
    fallback_total = sum(
        (row["buyout_sum"] for row in fallback_by_nm.values()),
        Decimal("0"),
    ).quantize(MONEY_QUANTUM)
    sku_total = sum(
        (
            (money(row.get("buyer_final_total")) or Decimal("0"))
            for row in sku_rows
            if money(row.get("buyer_final_total")) is not None
        ),
        Decimal("0"),
    ).quantize(MONEY_QUANTUM)
    fallback_buyouts_count = sum(
        (row["buyouts"] for row in fallback_by_nm.values()),
        Decimal("0"),
    )
    has_fallback_amount = fallback_total > 0 and fallback_buyouts_count > 0
    if fbs_orders_with_price_count == 0 and not has_fallback_amount:
        totals_status = "unavailable"
    elif sku_total != order_total:
        totals_status = "mismatch"
    elif fbs_orders_with_price_count < fbs_orders_count:
        totals_status = "partial"
    else:
        totals_status = "matched"
    has_reconciliation_amount = fbs_orders_with_price_count > 0 or has_fallback_amount
    weighted_discount_numerator = Decimal("0")
    weighted_discount_units = Decimal("0")
    for row in sku_rows:
        row_discount = percent(row.get("platform_discount_percent"))
        row_units = decimal_or_none(row.get("buyer_price_units"))
        if row_discount is None or row_units is None or row_units <= 0:
            continue
        weighted_discount_numerator += row_discount * row_units
        weighted_discount_units += row_units
    weighted_platform_discount = (
        (weighted_discount_numerator / weighted_discount_units).quantize(
            PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        if weighted_discount_units > 0
        else None
    )
    seller_price_available = any(money(row.get("seller_price")) is not None for row in sku_rows)
    fbs_price_available = fbs_orders_with_price_count > 0
    buyer_fallback_available = any(
        row.get("buyer_price_source") == "sales_funnel_fallback"
        and money(row.get("buyer_final_price")) is not None
        for row in sku_rows
    )
    return {
        "available": bool(sku_rows),
        "title": "Цены и платформенные скидки по SKU",
        "operational_date": operational_date,
        "sku_rows": sku_rows,
        "weighted_platform_discount_percent": _decimal_text(weighted_platform_discount),
        "status": {
            "seller_price": "available" if seller_price_available else "unavailable",
            "fbs_price_data": "available" if fbs_price_available else "unavailable",
            "buyer_price": (
                "available"
                if fbs_price_available
                else ("fallback/available" if buyer_fallback_available else "unavailable")
            ),
        },
        "changes": {
            "title": "Изменение цен и скидок",
            "rows": sku_rows,
            "recommendation_mode": "analytics_only",
            "automatic_price_changes": False,
        },
        "reconciliation": {
            "sku_buyer_final_total": _decimal_text(sku_total) if has_reconciliation_amount else None,
            "fbs_orders_buyer_final_total": _decimal_text(order_total) if has_reconciliation_amount else None,
            "difference": (
                _decimal_text((sku_total - order_total).quantize(MONEY_QUANTUM))
                if has_reconciliation_amount
                else None
            ),
            "fbs_orders_count": fbs_orders_count,
            "fbs_orders_with_price_count": fbs_orders_with_price_count,
            "fallback_buyouts_count": _decimal_text(fallback_buyouts_count),
            "buyer_total_source": (
                "fbs_converted_final_price"
                if fbs_orders_with_price_count > 0
                else ("sales_funnel_fallback" if has_fallback_amount else "unavailable")
            ),
            "status": totals_status,
        },
        "source": f"{PRICE_SOURCE}+{FBS_ORDER_SOURCE}+{FINANCE_SOURCE}",
    }


def write_raw_price_payloads(
    *,
    repo_root: str,
    seller_id: str,
    captured_at: str,
    goods_payload: Any,
    fbs_payload: Any,
) -> dict[str, str]:
    safe_stamp = str(captured_at).replace(":", "-").replace("+", "_")
    directory = Path(repo_root) / "cabinets" / seller_id / "history" / "prices" / "raw"
    directory.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, payload, version in (
        ("goods_filter", goods_payload, "v2"),
        ("fbs_orders", fbs_payload, "v3"),
    ):
        path = directory / f"{safe_stamp}_{name}.json"
        body = {
            "seller_id": seller_id,
            "captured_at": captured_at,
            "api_version": version,
            "source": name,
            "payload": payload,
        }
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        paths[name] = os.path.relpath(path, repo_root).replace("\\", "/")
    return paths
