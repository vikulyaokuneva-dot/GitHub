from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

from .client import (
    ADVERTS_PATH,
    ADVERT_STATS_PATH,
    FINANCE_DETAILED_PATH,
    ORDERS_PATH,
    SALES_FUNNEL_PRODUCTS_PATH,
    SALES_PATH,
    SEARCH_REPORT_DETAILS_PATH,
    SEARCH_REPORT_GROUPS_PATH,
    STOCKS_WB_WAREHOUSES_PATH,
    WBApiClient,
)

FINANCE_LEGACY_PATH = "/api/v5/supplier/reportDetailByPeriod"

SALES_FUNNEL_PAGE_LIMIT = 1000
FINANCE_PAGE_LIMIT = 100000
ADS_CHUNK_SIZE = 50
STOCKS_WB_WAREHOUSES_PAGE_LIMIT = 250000
CABINET_COMMERCE_SOURCE_FAMILY = "cabinet_commerce_daily"
ADS_SOURCE_FAMILY = "ads_api"


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(str(os.getenv(name, str(default)) or str(default)).strip()))
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(str(os.getenv(name, str(default)) or str(default)).strip()))
    except Exception:
        return float(default)


def _cabinet_commerce_retry_policy() -> Dict[str, Any]:
    return {
        "retryable_statuses": (429, 500, 502, 503, 504),
        "max_attempts": max(1, _env_int("WB_CABINET_COMMERCE_MAX_ATTEMPTS", 5)),
        "base_delay_seconds": _env_float("WB_CABINET_COMMERCE_BASE_DELAY_SECONDS", 3.0),
        "cap_delay_seconds": _env_float("WB_CABINET_COMMERCE_CAP_DELAY_SECONDS", 45.0),
        "jitter_ratio": min(_env_float("WB_CABINET_COMMERCE_JITTER_RATIO", 0.25), 1.0),
        "max_retry_window_seconds": _env_float("WB_CABINET_COMMERCE_MAX_RETRY_WINDOW_SECONDS", 90.0),
    }


def _cabinet_commerce_cache_ttl_seconds() -> int:
    return max(60, _env_int("WB_CABINET_COMMERCE_CACHE_TTL_SECONDS", 21600))


def _cabinet_commerce_cache_fallback_ttl_seconds() -> int:
    return max(_cabinet_commerce_cache_ttl_seconds(), _env_int("WB_CABINET_COMMERCE_CACHE_FALLBACK_TTL_SECONDS", 259200))


def _cabinet_commerce_cache_path(repo_root: str, seller_id: str, target_date: str) -> str:
    return os.path.join(
        repo_root,
        "cabinets",
        seller_id,
        "artifacts",
        "wb_api_core",
        "cache",
        CABINET_COMMERCE_SOURCE_FAMILY,
        f"{target_date}.json",
    )


def _read_json(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def _read_cabinet_commerce_cache(
    *,
    repo_root: str | None,
    seller_id: str | None,
    target_date: str,
    max_age_seconds: int | None,
) -> Dict[str, Any] | None:
    resolved_repo_root = str(repo_root or "").strip()
    resolved_seller_id = str(seller_id or "").strip()
    if not resolved_repo_root or not resolved_seller_id:
        return None
    path = _cabinet_commerce_cache_path(resolved_repo_root, resolved_seller_id, target_date)
    if not os.path.exists(path):
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return None
    if str(payload.get("seller_id") or "") != resolved_seller_id:
        return None
    if str(payload.get("target_date") or "") != target_date:
        return None
    if str(payload.get("source_family") or "") != CABINET_COMMERCE_SOURCE_FAMILY:
        return None
    rows_raw = payload.get("rows_raw")
    debug = payload.get("debug")
    if not isinstance(rows_raw, list) or not isinstance(debug, dict):
        return None
    if not bool(debug.get("success", False)):
        return None
    cached_at_epoch = payload.get("cached_at_epoch")
    try:
        cache_age_seconds = max(0.0, time.time() - float(cached_at_epoch))
    except Exception:
        try:
            cache_age_seconds = max(0.0, time.time() - float(os.path.getmtime(path)))
        except Exception:
            cache_age_seconds = 0.0
    if max_age_seconds is not None and cache_age_seconds > float(max_age_seconds):
        return None
    return {
        "path": path,
        "age_seconds": round(cache_age_seconds, 2),
        "rows_raw": [row for row in rows_raw if isinstance(row, dict)],
        "debug": dict(debug),
    }


def _write_cabinet_commerce_cache(
    *,
    repo_root: str | None,
    seller_id: str | None,
    target_date: str,
    rows_raw: List[Dict[str, Any]],
    debug: Dict[str, Any],
) -> str:
    resolved_repo_root = str(repo_root or "").strip()
    resolved_seller_id = str(seller_id or "").strip()
    if not resolved_repo_root or not resolved_seller_id:
        return ""
    path = _cabinet_commerce_cache_path(resolved_repo_root, resolved_seller_id, target_date)
    payload = {
        "seller_id": resolved_seller_id,
        "target_date": target_date,
        "source_family": CABINET_COMMERCE_SOURCE_FAMILY,
        "cached_at_epoch": round(time.time(), 3),
        "rows_raw": [row for row in rows_raw if isinstance(row, dict)],
        "debug": dict(debug),
    }
    _write_json(path, payload)
    return path


def _build_cabinet_cache_debug(
    *,
    client: WBApiClient,
    target_date: str,
    rows_raw: List[Dict[str, Any]],
    cache_path: str,
    cache_age_seconds: float,
    cache_mode: str,
    retry_count: int = 0,
    retry_delays: List[float] | None = None,
    final_failure_reason: str = "",
    last_status_code: Any = 200,
    last_attempts: int = 0,
) -> Dict[str, Any]:
    response = {
        "endpoint": "cabinet_commerce",
        "path": SALES_FUNNEL_PRODUCTS_PATH,
        "method": "POST",
        "base_url": client.analytics_base_url,
        "success": True,
        "status_code": last_status_code,
        "attempts": last_attempts,
        "error_text": "",
    }
    return _build_debug(
        response,
        rows_loaded=len(rows_raw),
        date_from=target_date,
        date_to=target_date,
        extra={
            "source_family": CABINET_COMMERCE_SOURCE_FAMILY,
            "page_limit": SALES_FUNNEL_PAGE_LIMIT,
            "pages_loaded": 0,
            "last_offset": 0,
            "pagination_complete": True,
            "cache_hit": True,
            "cache_mode": cache_mode,
            "cache_fallback_used": cache_mode == "failure_fallback",
            "cache_path": cache_path,
            "cache_age_seconds": round(float(cache_age_seconds or 0.0), 2),
            "retry_count": int(retry_count or 0),
            "retry_delays": list(retry_delays or []),
            "final_failure_reason": str(final_failure_reason or ""),
        },
    )


def _build_debug(
    response: Dict[str, Any],
    *,
    rows_loaded: int,
    date_from: str,
    date_to: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "endpoint": str(response.get("endpoint") or ""),
        "path": str(response.get("path") or ""),
        "method": str(response.get("method") or "GET"),
        "base_url": str(response.get("base_url") or ""),
        "success": bool(response.get("success", False)),
        "status_code": response.get("status_code"),
        "attempts": int(response.get("attempts", 0) or 0),
        "rows_loaded": int(rows_loaded),
        "error_text": str(response.get("error_text") or ""),
        "date_from": date_from,
        "date_to": date_to,
        "cache_hit": bool(response.get("cache_hit", False)),
        "cache_mode": str(response.get("cache_mode") or ""),
        "cache_fallback_used": bool(response.get("cache_fallback_used", False)),
        "cache_path": str(response.get("cache_path") or ""),
        "cache_age_seconds": response.get("cache_age_seconds"),
        "retry_count": int(response.get("retry_count", 0) or 0),
        "retry_delays": list(response.get("retry_delays", []) or []),
        "final_failure_reason": str(response.get("final_failure_reason") or ""),
        "retry_after": str(response.get("retry_after") or ""),
        "x_ratelimit_retry": str(response.get("x_ratelimit_retry") or ""),
        "x_ratelimit_reset": str(response.get("x_ratelimit_reset") or ""),
        "x_ratelimit_remaining": str(response.get("x_ratelimit_remaining") or ""),
        "rate_limit_delay_seconds": response.get("rate_limit_delay_seconds"),
        "token_present": bool(response.get("token_present", False)),
        "token_env_name_used": str(response.get("token_env_name_used") or ""),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    return payload


def _extract_realization_rows(payload: Any, client: WBApiClient) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def _append(items: Any) -> None:
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    rows.append(item)

    if isinstance(payload, list):
        _append(payload)
    elif isinstance(payload, dict):
        _append(payload.get("rows"))
        _append(payload.get("details"))
        for key in ("data", "items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                _append(value)
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    _append(item.get("rows"))
                    _append(item.get("details"))
                    _append(item.get("data"))

    if rows:
        return rows
    return client.extract_rows(payload, ("data", "items", "rows", "details"))


def _extract_sales_funnel_rows(payload: Any, client: WBApiClient) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            products = data.get("products")
            if isinstance(products, list):
                return [row for row in products if isinstance(row, dict)]
        products = payload.get("products")
        if isinstance(products, list):
            return [row for row in products if isinstance(row, dict)]
    return client.extract_rows(payload, ("products", "items", "rows"))


def load_cabinet_commerce(
    client: WBApiClient,
    target_date: str,
    *,
    seller_id: str | None = None,
    repo_root: str | None = None,
) -> Dict[str, Any]:
    fresh_cache = _read_cabinet_commerce_cache(
        repo_root=repo_root,
        seller_id=seller_id,
        target_date=target_date,
        max_age_seconds=_cabinet_commerce_cache_ttl_seconds(),
    )
    if isinstance(fresh_cache, dict):
        cached_rows = list(fresh_cache.get("rows_raw", []))
        return {
            "rows_raw": cached_rows,
            "debug": _build_cabinet_cache_debug(
                client=client,
                target_date=target_date,
                rows_raw=cached_rows,
                cache_path=str(fresh_cache.get("path") or ""),
                cache_age_seconds=float(fresh_cache.get("age_seconds") or 0.0),
                cache_mode="fresh_local_cache",
            ),
        }

    rows_raw: List[Dict[str, Any]] = []
    pages_loaded = 0
    offset = 0
    last_page_rows_loaded = 0
    total_retry_count = 0
    total_retry_delays: List[float] = []
    last_response: Dict[str, Any] = {
        "endpoint": "cabinet_commerce",
        "path": SALES_FUNNEL_PRODUCTS_PATH,
        "method": "POST",
        "base_url": client.analytics_base_url,
        "success": False,
        "status_code": None,
        "attempts": 0,
        "error_text": "",
    }

    while True:
        response = client.request_json(
            endpoint_name="cabinet_commerce",
            path=SALES_FUNNEL_PRODUCTS_PATH,
            method="POST",
            json_body={
                "selectedPeriod": {"start": target_date, "end": target_date},
                "nmIds": [],
                "brandNames": [],
                "subjectIds": [],
                "tagIds": [],
                "skipDeletedNm": True,
                "limit": SALES_FUNNEL_PAGE_LIMIT,
                "offset": offset,
            },
            allow_204=True,
            empty_on_204={"data": {"products": []}},
            base_url=client.analytics_base_url,
            retry_policy=_cabinet_commerce_retry_policy(),
        )
        last_response = response
        total_retry_count += int(response.get("retry_count", 0) or 0)
        total_retry_delays.extend([float(item) for item in list(response.get("retry_delays", []) or [])])
        if not bool(response.get("success", False)):
            break
        page_rows = _extract_sales_funnel_rows(response.get("payload", {}), client)
        last_page_rows_loaded = len(page_rows)
        rows_raw.extend(page_rows)
        pages_loaded += 1
        if last_page_rows_loaded < SALES_FUNNEL_PAGE_LIMIT:
            break
        offset += SALES_FUNNEL_PAGE_LIMIT

    if bool(last_response.get("success", False)):
        success_debug = _build_debug(
            last_response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": CABINET_COMMERCE_SOURCE_FAMILY,
                "page_limit": SALES_FUNNEL_PAGE_LIMIT,
                "pages_loaded": pages_loaded,
                "last_offset": offset,
                "pagination_complete": bool(bool(last_response.get("success", False)) and last_page_rows_loaded < SALES_FUNNEL_PAGE_LIMIT),
                "cache_hit": False,
                "cache_mode": "miss",
                "cache_fallback_used": False,
                "retry_count": total_retry_count,
                "retry_delays": [round(float(item), 2) for item in total_retry_delays],
                "final_failure_reason": "",
            },
        )
        cache_path = _write_cabinet_commerce_cache(
            repo_root=repo_root,
            seller_id=seller_id,
            target_date=target_date,
            rows_raw=rows_raw,
            debug=success_debug,
        )
        if cache_path:
            success_debug["cache_path"] = cache_path
        return {
            "rows_raw": rows_raw,
            "debug": success_debug,
        }

    fallback_cache = _read_cabinet_commerce_cache(
        repo_root=repo_root,
        seller_id=seller_id,
        target_date=target_date,
        max_age_seconds=_cabinet_commerce_cache_fallback_ttl_seconds(),
    )
    if isinstance(fallback_cache, dict):
        cached_rows = list(fallback_cache.get("rows_raw", []))
        return {
            "rows_raw": cached_rows,
            "debug": _build_cabinet_cache_debug(
                client=client,
                target_date=target_date,
                rows_raw=cached_rows,
                cache_path=str(fallback_cache.get("path") or ""),
                cache_age_seconds=float(fallback_cache.get("age_seconds") or 0.0),
                cache_mode="failure_fallback",
                retry_count=total_retry_count,
                retry_delays=[round(float(item), 2) for item in total_retry_delays],
                final_failure_reason=str(last_response.get("final_failure_reason") or last_response.get("error_text") or ""),
                last_status_code=last_response.get("status_code"),
                last_attempts=int(last_response.get("attempts", 0) or 0),
            ),
        }

    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            last_response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": CABINET_COMMERCE_SOURCE_FAMILY,
                "page_limit": SALES_FUNNEL_PAGE_LIMIT,
                "pages_loaded": pages_loaded,
                "last_offset": offset,
                "pagination_complete": bool(bool(last_response.get("success", False)) and last_page_rows_loaded < SALES_FUNNEL_PAGE_LIMIT),
                "cache_hit": False,
                "cache_mode": "miss",
                "cache_fallback_used": False,
                "retry_count": total_retry_count,
                "retry_delays": [round(float(item), 2) for item in total_retry_delays],
                "final_failure_reason": str(last_response.get("final_failure_reason") or last_response.get("error_text") or ""),
            },
        ),
    }


def load_orders(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="orders",
        path=ORDERS_PATH,
        params={"dateFrom": target_date, "flag": 0},
        allow_204=True,
        empty_on_204=[],
        retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "flag_used": 0,
                "date_semantics": "lastChangeDate_gte_dateFrom",
            },
        ),
    }


def load_sales(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="sales",
        path=SALES_PATH,
        params={"dateFrom": target_date, "flag": 1},
        allow_204=True,
        empty_on_204=[],
        retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
    )
    payload = response.get("payload", [])
    rows_raw = client.extract_rows(payload, ("data", "items", "rows"))
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(response, rows_loaded=len(rows_raw), date_from=target_date, date_to=target_date),
    }


def _extract_stocks_wb_warehouse_rows(payload: Any, client: WBApiClient) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return client.extract_rows(data, ("items", "rows", "stocks"))
    return client.extract_rows(payload, ("data", "items", "rows", "stocks"))


def load_stocks(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    rows_raw: List[Dict[str, Any]] = []
    offset = 0
    pages_loaded = 0
    last_page_rows_loaded = 0
    response: Dict[str, Any] = {
        "endpoint": "stocks",
        "path": STOCKS_WB_WAREHOUSES_PATH,
        "method": "POST",
        "base_url": client.analytics_base_url,
        "success": False,
        "status_code": None,
        "attempts": 0,
        "error_text": "",
    }

    while True:
        response = client.request_json(
            endpoint_name="stocks",
            path=STOCKS_WB_WAREHOUSES_PATH,
            method="POST",
            json_body={
                "nmIds": [],
                "chrtIds": [],
                "limit": STOCKS_WB_WAREHOUSES_PAGE_LIMIT,
                "offset": offset,
            },
            allow_204=True,
            empty_on_204=[],
            base_url=client.analytics_base_url,
            retry_policy={
                "retryable_statuses": (429, 500, 502, 503, 504),
                "max_attempts": 3,
                "base_delay_seconds": 3.0,
                "cap_delay_seconds": 20.0,
                "jitter_ratio": 0.1,
                "max_retry_window_seconds": 60.0,
            },
        )
        if not bool(response.get("success", False)):
            break
        page_rows = _extract_stocks_wb_warehouse_rows(response.get("payload", []), client)
        rows_raw.extend(page_rows)
        pages_loaded += 1
        last_page_rows_loaded = len(page_rows)
        if last_page_rows_loaded < STOCKS_WB_WAREHOUSES_PAGE_LIMIT:
            break
        offset += STOCKS_WB_WAREHOUSES_PAGE_LIMIT

    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": "stocks_wb_warehouses",
                "snapshot_kind": "current",
                "page_limit": STOCKS_WB_WAREHOUSES_PAGE_LIMIT,
                "pages_loaded": pages_loaded,
                "last_offset": offset,
                "pagination_complete": bool(
                    response.get("success", False)
                    and last_page_rows_loaded < STOCKS_WB_WAREHOUSES_PAGE_LIMIT
                ),
            },
        ),
    }


def load_finance_final(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="finance_final",
        path=FINANCE_DETAILED_PATH,
        method="POST",
        json_body={
            "dateFrom": target_date,
            "dateTo": target_date,
            "period": "daily",
            "limit": FINANCE_PAGE_LIMIT,
            "rrdId": 0,
        },
        allow_204=True,
        empty_on_204=[],
        base_url=client.finance_base_url,
        retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
    )
    payload = response.get("payload", [])
    rows_raw = _extract_realization_rows(payload, client)
    payload_incompatible = bool(bool(response.get("success", False)) and payload not in ({}, [], None) and not rows_raw)
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": "finance_final_daily",
                "finance_endpoint_used": FINANCE_DETAILED_PATH,
                "finance_requested_fields_count": 0,
                "finance_requested_fields": [],
                "finance_request_uses_all_fields": True,
                "finance_period": "daily",
                "finance_limit": FINANCE_PAGE_LIMIT,
                "finance_rrd_id": 0,
                "finance_pagination_truncated": len(rows_raw) >= FINANCE_PAGE_LIMIT,
                "finance_payload_incompatible": payload_incompatible,
            },
        ),
    }


def _safe_float(row: Dict[str, Any], keys: tuple) -> float:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def load_finance_legacy(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="finance_legacy",
        path=FINANCE_LEGACY_PATH,
        method="GET",
        params={
            "dateFrom": target_date,
            "dateTo": target_date,
            "limit": 100000,
            "rrdid": 0,
        },
        allow_204=True,
        empty_on_204=[],
        base_url=client.statistics_base_url,
        retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
    )
    payload = response.get("payload", [])
    rows_raw = _extract_realization_rows(payload, client)
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": "finance_legacy",
                "finance_endpoint_used": FINANCE_LEGACY_PATH,
                "finance_api_mode": "legacy_direct",
            },
        ),
    }


def load_ads(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    adverts_response = client.request_json(
        endpoint_name="ads_adverts",
        path=ADVERTS_PATH,
        method="GET",
        json_body=None,
        allow_204=True,
        empty_on_204={"data": {"adverts": []}},
        base_url=client.advert_base_url,
        retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
    )
    adverts_payload = adverts_response.get("payload", {})
    advert_rows = []
    if isinstance(adverts_payload, dict):
        advert_rows = adverts_payload.get("adverts", adverts_payload.get("items", []))
    if not isinstance(advert_rows, list):
        advert_rows = []

    advert_ids: List[int] = []
    for row in advert_rows:
        if not isinstance(row, dict):
            continue
        raw_id = row.get("advertId") or row.get("id")
        try:
            advert_ids.append(int(float(str(raw_id or "0"))))
        except (TypeError, ValueError):
            continue
    advert_ids = [aid for aid in advert_ids if aid > 0]

    if not advert_ids:
        return {
            "rows_raw": [],
            "debug": _build_debug(
                adverts_response,
                rows_loaded=0,
                date_from=target_date,
                date_to=target_date,
                extra={
                    "source_family": ADS_SOURCE_FAMILY,
                    "adverts_listed": len(advert_rows),
                    "advert_ids_found": 0,
                },
            ),
        }

    bucket: Dict[str, Dict[str, float]] = {}
    stats_debug = adverts_response
    for idx in range(0, len(advert_ids), ADS_CHUNK_SIZE):
        chunk = advert_ids[idx:idx + ADS_CHUNK_SIZE]
        stats_response = client.request_json(
            endpoint_name="ads_stats",
            path=ADVERT_STATS_PATH,
            method="GET",
            json_body=None,
            params={
                "ids": ",".join(str(aid) for aid in chunk),
                "beginDate": target_date,
                "endDate": target_date,
            },
            allow_204=True,
            empty_on_204=[],
            base_url=client.advert_base_url,
            retry_policy={"retryable_statuses": (500, 502, 503, 504), "max_attempts": 2},
        )
        stats_debug = stats_response
        stats_payload = stats_response.get("payload", [])
        if not isinstance(stats_payload, list):
            stats_payload = []

        for stat in stats_payload:
            if not isinstance(stat, dict):
                continue
            day_rows = stat.get("days", [])
            if not isinstance(day_rows, list):
                day_rows = []
            for day in day_rows:
                if not isinstance(day, dict):
                    continue
                nm_rows = day.get("nm", day.get("nms", []))
                if not isinstance(nm_rows, list):
                    nm_rows = []
                if not nm_rows:
                    app_rows = day.get("apps", [])
                    if not isinstance(app_rows, list):
                        app_rows = []
                    for app in app_rows:
                        if isinstance(app, dict):
                            app_nm = app.get("nm", app.get("nms", []))
                            if isinstance(app_nm, list):
                                nm_rows.extend(app_nm)
                for nm in nm_rows:
                    if not isinstance(nm, dict):
                        continue
                    sku = str(nm.get("nmId") or nm.get("nm_id") or nm.get("nmid") or nm.get("nm") or "").strip()
                    if not sku:
                        continue
                    spend = _safe_float(nm, ("sum", "spend", "cost", "expenses", "price"))
                    impressions = _safe_float(nm, ("impressions", "views", "shows", "imps"))
                    clicks = _safe_float(nm, ("clicks", "click"))
                    add_to_cart = _safe_float(nm, ("addToCart", "add_to_cart", "atbs", "cart_count"))
                    orders = _safe_float(nm, ("orders", "order_count", "ordersCount"))
                    if sku not in bucket:
                        bucket[sku] = {"ads_spend": 0.0, "impressions": 0.0, "clicks": 0.0, "add_to_cart": 0.0, "orders": 0.0}
                    bucket[sku]["ads_spend"] += spend
                    bucket[sku]["impressions"] += impressions
                    bucket[sku]["clicks"] += clicks
                    bucket[sku]["add_to_cart"] += add_to_cart
                    bucket[sku]["orders"] += orders

    rows_raw: List[Dict[str, Any]] = []
    for sku, agg in bucket.items():
        impressions = agg.get("impressions", 0.0)
        clicks = agg.get("clicks", 0.0)
        orders_val = agg.get("orders", 0.0)
        spend = agg.get("ads_spend", 0.0)
        ctr = (clicks / impressions * 100.0) if impressions > 0 else None
        cpo = (spend / orders_val) if orders_val > 0 else None
        rows_raw.append({
            "date": target_date,
            "sku": sku,
            "nm_id": sku,
            "ads_spend": round(spend, 2),
            "impressions": round(impressions, 0),
            "clicks": round(clicks, 0),
            "add_to_cart": round(agg.get("add_to_cart", 0.0), 0),
            "orders": round(orders_val, 0),
            "ctr": round(ctr, 2) if ctr is not None else None,
            "cpo": round(cpo, 2) if cpo is not None else None,
            "source": "ads_api",
        })

    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            stats_debug,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": ADS_SOURCE_FAMILY,
                "adverts_listed": len(advert_rows),
                "advert_ids_found": len(advert_ids),
                "ads_spend_total": round(sum(r.get("ads_spend", 0.0) for r in rows_raw), 2),
            },
        ),
    }


def load_finance_final_single_attempt(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    response = client.request_json(
        endpoint_name="finance_final",
        path=FINANCE_DETAILED_PATH,
        method="POST",
        json_body={
            "dateFrom": target_date,
            "dateTo": target_date,
            "period": "daily",
            "limit": FINANCE_PAGE_LIMIT,
            "rrdId": 0,
        },
        allow_204=True,
        empty_on_204=[],
        base_url=client.finance_base_url,
        retry_policy={"retryable_statuses": (), "max_attempts": 1},
    )
    payload = response.get("payload", [])
    rows_raw = _extract_realization_rows(payload, client)
    payload_incompatible = bool(bool(response.get("success", False)) and payload not in ({}, [], None) and not rows_raw)
    return {
        "rows_raw": rows_raw,
        "debug": _build_debug(
            response,
            rows_loaded=len(rows_raw),
            date_from=target_date,
            date_to=target_date,
            extra={
                "source_family": "finance_final_daily",
                "finance_endpoint_used": FINANCE_DETAILED_PATH,
                "finance_requested_fields_count": 0,
                "finance_requested_fields": [],
                "finance_request_uses_all_fields": True,
                "finance_period": "daily",
                "finance_limit": FINANCE_PAGE_LIMIT,
                "finance_rrd_id": 0,
                "finance_pagination_truncated": len(rows_raw) >= FINANCE_PAGE_LIMIT,
                "finance_payload_incompatible": payload_incompatible,
                "finance_single_attempt": True,
            },
        ),
    }


def load_finance_final_with_lag(client: WBApiClient, target_date: str, max_lag_days: int = 3) -> Dict[str, Any]:
    from datetime import datetime, timedelta
    primary = load_finance_final(client, target_date)
    if primary.get("rows_raw"):
        return primary
    finance_debug = primary.get("debug", {})
    if finance_debug.get("status_code") == 429:
        legacy = load_finance_legacy(client, target_date)
        legacy_debug = legacy.get("debug", {})
        if legacy.get("rows_raw"):
            debug = dict(legacy_debug)
            debug["finance_fallback_used"] = True
            debug["finance_fallback_reason"] = "primary_429_to_legacy"
            debug["finance_primary_status_code"] = 429
            legacy["debug"] = debug
            return legacy
        debug = dict(primary.get("debug", {}))
        debug["finance_legacy_attempted"] = True
        debug["finance_legacy_status_code"] = legacy_debug.get("status_code")
        debug["finance_legacy_error_text"] = str(legacy_debug.get("error_text") or "")
        primary["debug"] = debug
        return primary
    for lag in range(1, max_lag_days + 1):
        try:
            lag_date = (datetime.strptime(target_date, "%Y-%m-%d").date() - timedelta(days=lag)).isoformat()
        except Exception:
            continue
        lag_result = load_finance_final_single_attempt(client, lag_date)
        if lag_result.get("rows_raw"):
            debug = dict(lag_result.get("debug", {}))
            debug["finance_lag_used"] = True
            debug["finance_lag_days"] = lag
            debug["finance_original_date"] = target_date
            debug["finance_actual_date"] = lag_date
            lag_result["debug"] = debug
            return lag_result
        if lag_result.get("debug", {}).get("status_code") == 429:
            break
    return primary


def load_search_report(client: WBApiClient, target_date: str) -> Dict[str, Any]:
    if not client.has_token():
        return {"available": False, "rows_raw": [], "source": "search_report_api", "debug": {"success": False, "reason": "no_token"}}

    date_from = target_date
    date_to = target_date

    body = {
        "selectedPeriod": {"start": date_from, "end": date_to},
        "currentPeriod": {"start": date_from, "end": date_to},
        "nmIds": [],
        "brandNames": [],
        "subjectIds": [],
        "tagIds": [],
        "skipDeletedNm": True,
        "limit": 1000,
        "offset": 0,
        "orderBy": "orderSum",
        "positionCluster": "searchQueriesCount",
    }

    try:
        url = f"{client.analytics_base_url}{SEARCH_REPORT_GROUPS_PATH}"
        result = client.request_json(
            endpoint_name="search_report_groups",
            path=SEARCH_REPORT_GROUPS_PATH,
            method="POST",
            json_body=body,
            base_url=client.analytics_base_url,
            retry_policy={
                "retryable_statuses": (500, 502, 503, 504),
                "max_attempts": 2,
            },
        )
        if not result.get("success"):
            return {"available": False, "rows_raw": [], "source": "search_report_api", "debug": {"success": False, "status_code": result.get("status_code"), "error": result.get("error_text", "")[:500]}}

        payload = result.get("payload") or {}
        groups = payload.get("data", {}).get("groups", []) if isinstance(payload.get("data"), dict) else []

        all_rows = []
        for group in groups:
            nm_ids = [p.get("nmId") for p in group.get("products", []) if p.get("nmId")]
            if not nm_ids:
                continue

            detail_body = {
                "selectedPeriod": {"start": date_from, "end": date_to},
                "currentPeriod": {"start": date_from, "end": date_to},
                "nmIds": nm_ids,
                "limit": 1000,
                "offset": 0,
                "orderBy": "orderSum",
                "positionCluster": "searchQueriesCount",
            }
            try:
                detail_result = client.request_json(
                    endpoint_name="search_report_details",
                    path=SEARCH_REPORT_DETAILS_PATH,
                    method="POST",
                    json_body=detail_body,
                    base_url=client.analytics_base_url,
                    retry_policy={
                        "retryable_statuses": (500, 502, 503, 504),
                        "max_attempts": 2,
                    },
                )
                if detail_result.get("success"):
                    detail_payload = detail_result.get("payload") or {}
                    details = detail_payload.get("data", {}).get("details", []) if isinstance(detail_payload.get("data"), dict) else []
                    for d in details:
                        all_rows.append({
                            "nmId": d.get("nmId"),
                            "vendorCode": d.get("vendorCode", ""),
                            "title": d.get("title", ""),
                            "searchQueriesCount": d.get("searchQueriesCount", 0),
                            "viewedWithSearchCount": d.get("viewedWithSearchCount", 0),
                            "clickedWithSearchCount": d.get("clickedWithSearchCount", 0),
                            "addToCartWithSearchCount": d.get("addToCartWithSearchCount", 0),
                            "ordersWithSearchCount": d.get("ordersWithSearchCount", 0),
                            "sumWithSearch": d.get("sumWithSearch", 0),
                            "buyoutWithSearchCount": d.get("buyoutWithSearchCount", 0),
                            "buyoutSumWithSearch": d.get("buyoutSumWithSearch", 0),
                        })
            except Exception:
                pass

        return {
            "available": True,
            "rows_raw": all_rows,
            "source": "search_report_api",
            "target_date": target_date,
            "debug": {"success": True, "status_code": 200, "rows_loaded": len(all_rows), "groups_count": len(groups)},
        }
    except Exception as exc:
        return {"available": False, "rows_raw": [], "source": "search_report_api", "debug": {"success": False, "error": str(exc)[:500]}}


def load_bundle(
    client: WBApiClient,
    target_date: str,
    *,
    seller_id: str | None = None,
    repo_root: str | None = None,
    max_finance_lag_days: int = 3,
) -> Dict[str, Any]:
    return {
        "cabinet_commerce": load_cabinet_commerce(client, target_date, seller_id=seller_id, repo_root=repo_root),
        "finance_final": load_finance_final_with_lag(client, target_date, max_lag_days=max_finance_lag_days),
        "orders": load_orders(client, target_date),
        "sales": load_sales(client, target_date),
        "stocks": load_stocks(client, target_date),
        "ads": load_ads(client, target_date),
        "search_report": load_search_report(client, target_date),
    }
