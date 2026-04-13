"""LEGACY v3 skeleton context (reports/data layout).

Deprecated for active production daily flow.
Active route: `python -m v3.entry daily --seller <seller>`.
Kept only for backward compatibility of legacy modules.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
from datetime import date

from .utils import load_simple_yaml, ensure_list_container

@dataclass(frozen=True)
class SellerPaths:
    seller_root: str
    raw_root: str
    reports_root: str
    snapshots_root: str
    staging_root: str
    audit_uploads_root: str
    manual_ads_root: str
    cogs_path: str

    def for_date(self, run_date: str) -> "SellerRunPaths":
        reports_dir = os.path.join(self.reports_root, run_date)
        raw_dir = os.path.join(self.raw_root, run_date)
        staging_dir = os.path.join(self.staging_root, run_date)
        return SellerRunPaths(
            reports_dir=reports_dir,
            raw_dir=raw_dir,
            staging_dir=staging_dir,
        )

@dataclass(frozen=True)
class SellerRunPaths:
    reports_dir: str
    raw_dir: str
    staging_dir: str

@dataclass(frozen=True)
class SellerContext:
    seller_id: str
    seller_name: str
    timezone: str
    tax_rate: float
    email_reports_to: List[str]
    token_ref: str
    run_date: str  # YYYY-MM-DD
    mode: str      # daily | audit
    paths: SellerPaths

    @staticmethod
    def from_repo(repo_root: str, seller_id: str, run_date: str, mode: str) -> "SellerContext":
        cfg_path = os.path.join(repo_root, "cabinets", seller_id, "config.yaml")
        cfg = load_simple_yaml(cfg_path)

        ensure_list_container(cfg, "email_reports_to")

        seller_root = os.path.join(repo_root, "cabinets", seller_id)
        paths = SellerPaths(
            seller_root=seller_root,
            raw_root=os.path.join(seller_root, "data", "raw"),
            reports_root=os.path.join(seller_root, "reports"),
            snapshots_root=os.path.join(seller_root, "data", "snapshots"),
            staging_root=os.path.join(seller_root, "data", "staging"),
            audit_uploads_root=os.path.join(seller_root, "data", "audit_uploads"),
            manual_ads_root=os.path.join(seller_root, "data", "manual_ads"),
            cogs_path=os.path.join(seller_root, "cogs", "cogs.xlsx"),
        )

        wb = cfg.get("wb") or {}
        token_ref = ""
        if isinstance(wb, dict):
            token_ref = str(wb.get("token_ref") or "").strip()

        return SellerContext(
            seller_id=str(cfg.get("seller_id") or seller_id),
            seller_name=str(cfg.get("seller_name") or seller_id),
            timezone=str(cfg.get("timezone") or "Europe/Moscow"),
            tax_rate=float(cfg.get("tax_rate") or 0.06),
            email_reports_to=list(cfg.get("email_reports_to") or []),
            token_ref=token_ref,
            run_date=run_date,
            mode=mode,
            paths=paths,
        )

    def get_wb_token(self) -> str:
        """В v3 skeleton токен берём из ENV по token_ref.
        Если не задан — возвращаем пустую строку (pipeline не должен падать).
        """
        if not self.token_ref:
            return ""
        return (os.getenv(self.token_ref, "") or "").strip()
