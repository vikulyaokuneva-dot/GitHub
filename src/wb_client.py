# src/wb_client.py
import os
import time
import json
import datetime as dt
from typing import Any, Dict, Optional

import requests

from wb_api_core.token_resolver import resolve_wb_api_token


class WBClient:
    SALES_FUNNEL_ENDPOINT = "/api/analytics/v3/sales-funnel/products"
    REALIZATION_ENDPOINT = "/api/v5/supplier/reportDetailByPeriod"

    def __init__(self, token: Optional[str] = None, raw_dir: str = "out/raw"):
        self.token, self.token_env_name_used = resolve_wb_api_token(token)
        if not self.token:
            raise ValueError("WB_API_TOKEN не задан. Добавь токен в Secrets/ENV.")

        self.analytics_url = (os.getenv("WB_ANALYTICS_BASE_URL", "https://seller-analytics-api.wildberries.ru")).rstrip("/")
        self.advert_url = (os.getenv("WB_ADVERT_BASE_URL", "https://advert-api.wildberries.ru")).rstrip("/")
        self.statistics_url = (os.getenv("WB_STATISTICS_BASE_URL", "https://statistics-api.wildberries.ru")).rstrip("/")

        self.raw_dir = raw_dir
        os.makedirs(self.raw_dir, exist_ok=True)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }

    def _save_raw(self, name: str, payload: Any):
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.raw_dir, f"{ts}_{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def get_json(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        name: str = "wb",
        base_url: Optional[str] = None,
        allow_204: bool = False,
        empty_on_204: Any = None,
        allow_403: bool = False,
        empty_on_403: Any = None,
    ) -> Any:
        """GET JSON from WB.
        allow_204: HTTP 204 => вернуть empty_on_204 (обычно [])
        allow_403: HTTP 403 => вернуть empty_on_403 (обычно []) и продолжить пайплайн
        """
        base = (base_url or self.analytics_url).rstrip("/")
        url = f"{base}{path}"
        params = params or {}

        last_err = None
        for attempt in range(1, 6):
            try:
                r = requests.get(url, headers=self._headers(), params=params, timeout=60)

                if r.status_code == 204 and allow_204:
                    payload = {"url": url, "params": params, "status": 204, "data": empty_on_204}
                    self._save_raw(name, payload)
                    return empty_on_204

                if r.status_code == 403 and allow_403:
                    payload = {"url": url, "params": params, "status": 403, "data": empty_on_403, "error": r.text}
                    self._save_raw(name, payload)
                    return empty_on_403

                if r.status_code == 200:
                    data = r.json()
                    self._save_raw(name, {"url": url, "params": params, "status": 200, "data": data})
                    return data

                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 * attempt)
                    last_err = f"{r.status_code}: {r.text[:200]}"
                    continue

                raise RuntimeError(f"WB API error {r.status_code}: {r.text}")

            except Exception as e:
                last_err = str(e)
                time.sleep(2 * attempt)

        raise RuntimeError(f"WB API failed after retries: {last_err}")

    def post_json(self, path: str, body: Dict[str, Any], name: str = "wb", base_url: Optional[str] = None) -> Any:
        base = (base_url or self.analytics_url).rstrip("/")
        url = f"{base}{path}"

        last_err = None
        for attempt in range(1, 6):
            try:
                r = requests.post(url, headers=self._headers(), json=body, timeout=60)
                if r.status_code == 200:
                    data = r.json()
                    self._save_raw(name, {"url": url, "body": body, "status": 200, "data": data})
                    return data

                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 * attempt)
                    last_err = f"{r.status_code}: {r.text[:200]}"
                    continue

                raise RuntimeError(f"WB API error {r.status_code}: {r.text}")

            except Exception as e:
                last_err = str(e)
                time.sleep(2 * attempt)

        raise RuntimeError(f"WB API failed after retries: {last_err}")

    # ======================
    # 1) ВОРОНКА (Analytics)
    # ======================
    def fetch_sales_funnel(self, date_from: str, date_to: str) -> Any:
        body = {
            "selectedPeriod": {"start": date_from, "end": date_to},
            "nmIds": [],
            "brandNames": [],
            "subjectIds": [],
            "tagIds": [],
            "skipDeletedNm": True,
            "limit": 1000,
            "offset": 0,
        }
        return self.post_json(
            path=self.SALES_FUNNEL_ENDPOINT,
            body=body,
            name="funnel",
            base_url=self.analytics_url,
        )

    # ======================
    # 2) РЕКЛАМА (Promotion)
    # ======================
    def fetch_ads_stats(self, date_from: str, date_to: str) -> Any:
        # В некоторых кабинетах WB может ограничить доступ к camp-api (403).
        # В этом случае НЕ валим весь отчёт — просто вернём пустые данные по рекламе.
        adverts = self.get_json(
            path="/api/advert/v2/adverts",
            params={},
            name="adverts",
            base_url=self.advert_url,
            allow_403=True,
            empty_on_403={},
        )

        # WB может возвращать разные формы:
        # 1) {"adverts": [ {"id": 33009836, ...}, ... ]}
        # 2) {"someKey": [ {"advertId": 123, ... }, ... ], ...}
        # Поэтому вытаскиваем id максимально безопасно.
        advert_ids: list[int] = []

        items = None
        if isinstance(adverts, dict):
            if isinstance(adverts.get("adverts"), list):
                items = adverts.get("adverts")
            else:
                # попробуем собрать все списки из значений
                items = []
                for v in adverts.values():
                    if isinstance(v, list):
                        items.extend(v)
        elif isinstance(adverts, list):
            items = adverts

        if items:
            for it in items:
                if not isinstance(it, dict):
                    continue
                raw_id = it.get("advertId")
                if raw_id is None:
                    raw_id = it.get("id")
                if raw_id is None:
                    continue
                try:
                    advert_ids.append(int(raw_id))
                except Exception:
                    continue

        advert_ids = sorted(set(advert_ids))
        if not advert_ids:
            return []

        all_stats: list[Any] = []
        chunk_size = 50

        for i in range(0, len(advert_ids), chunk_size):
            chunk = advert_ids[i:i + chunk_size]
            stats = self.get_json(
                path="/adv/v3/fullstats",
                params={
                    "ids": ",".join(map(str, chunk)),
                    "beginDate": date_from,
                    "endDate": date_to,
                },
                name=f"ads_fullstats_{i//chunk_size}",
                base_url=self.advert_url,
                allow_204=True,
                empty_on_204=[],
                allow_403=True,
                empty_on_403=[],
            )

            if isinstance(stats, list):
                all_stats.extend(stats)
            elif stats:
                all_stats.append(stats)

        return all_stats

    # ======================
    # 3) ОСТАТКИ (Analytics, текущий срез)
    # ======================
    def fetch_stocks(self, date_from: str | None = None) -> Any:
        _ = date_from
        return self.post_json(
            path="/api/analytics/v1/stocks-report/wb-warehouses",
            body={
                "nmIds": [],
                "chrtIds": [],
                "limit": 250000,
                "offset": 0,
            },
            name="stocks",
            base_url=self.analytics_url,
        )

    # ======================
    # 4) ФИНАНСЫ / РЕАЛИЗАЦИЯ (Statistics)
    # ======================
    def fetch_realization_report(self, date_from: str, date_to: str) -> Any:
        return self.get_json(
            path=self.REALIZATION_ENDPOINT,
            params={
                "dateFrom": date_from,
                "dateTo": date_to,
                "limit": 100000,
                "rrdid": 0,
            },
            name="realization",
            base_url=self.statistics_url,
            allow_204=True,
            empty_on_204=[],
        )
