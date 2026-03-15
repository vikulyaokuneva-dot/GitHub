from __future__ import annotations
from typing import Any, Dict, List, Optional
import os
from pathlib import Path

from .job_runner import run_job

_FALLBACK_SELLER_ID = "__missing_seller__"
_ALLOW_FALLBACK_ENV = "WB_ALLOW_MISSING_SELLER"


def _candidate_cabinets_dirs(repo_root: str) -> List[Path]:
    return [Path(repo_root) / "cabinets"]


def _is_valid_seller_cabinet(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name.startswith(".") or path.name.startswith("_"):
        return False
    file_markers = ("config.json", "config.yaml")
    dir_markers = ("input", "data", "artifacts", "history")
    has_config = any((path / marker).is_file() for marker in file_markers)
    has_structure = any((path / marker).is_dir() for marker in dir_markers)
    return has_config or has_structure


def _discover_seller_locations(repo_root: str) -> Dict[str, str]:
    locations: Dict[str, str] = {}
    for cabinets_dir in _candidate_cabinets_dirs(repo_root):
        if not cabinets_dir.is_dir():
            continue
        effective_repo_root = str(cabinets_dir.parent)
        for child in sorted(cabinets_dir.iterdir(), key=lambda item: item.name):
            if not _is_valid_seller_cabinet(child):
                continue
            locations.setdefault(child.name, effective_repo_root)
    return locations


def discover_sellers(repo_root: Optional[str] = None) -> List[str]:
    resolved_repo_root = repo_root or str(Path(__file__).resolve().parents[1])
    return sorted(_discover_seller_locations(resolved_repo_root).keys())


def list_sellers(repo_root: str) -> List[str]:
    return discover_sellers(repo_root)


def _resolve_seller_repo_root(repo_root: str, seller_id: str) -> str:
    locations = _discover_seller_locations(repo_root)
    if seller_id in locations:
        return locations[seller_id]

    discovered = sorted(locations.keys())
    if seller_id == _FALLBACK_SELLER_ID:
        allow_fallback = str(os.getenv(_ALLOW_FALLBACK_ENV, "")).strip() == "1"
        if allow_fallback:
            print(
                f"[warn] fallback seller '{_FALLBACK_SELLER_ID}' enabled via {_ALLOW_FALLBACK_ENV}=1; "
                "using debug fallback cabinet paths."
            )
            return repo_root
        if discovered:
            raise ValueError(
                f"Refusing fallback seller '{_FALLBACK_SELLER_ID}' because real sellers exist: {', '.join(discovered)}. "
                f"Set {_ALLOW_FALLBACK_ENV}=1 to force debug fallback."
            )
        print(
            f"[warn] using fallback seller '{_FALLBACK_SELLER_ID}' because no real sellers were discovered in "
            f"{Path(repo_root) / 'cabinets'}."
        )
        return repo_root

    if discovered:
        raise FileNotFoundError(f"Seller '{seller_id}' not found. Discovered sellers: {', '.join(discovered)}")
    print(
        f"[warn] seller '{seller_id}' not discovered; running in bootstrap mode because no sellers exist in "
        f"{Path(repo_root) / 'cabinets'}."
    )
    return repo_root


def run_for_seller(repo_root: str, seller_id: str, run_date: str) -> Dict[str, Any]:
    try:
        seller_repo_root = _resolve_seller_repo_root(repo_root, seller_id)
        print(f"[{seller_id}] pipeline started")
        result = run_job(seller_repo_root, seller_id, run_date, mode="daily")
        if str(result.get("status") or "") == "success":
            print(f"[{seller_id}] pipeline finished successfully")
        else:
            print(f"[{seller_id}] pipeline failed: {result.get('error')}")
        return result
    except Exception as exc:
        print(f"[{seller_id}] pipeline failed: {exc}")
        return {
            "seller_id": seller_id,
            "mode": "daily",
            "run_date": run_date,
            "status": "failed",
            "error": str(exc),
        }


def _batch_summary(run_date: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    safe_results = [row for row in results if isinstance(row, dict)]
    non_fallback_results = [row for row in safe_results if str(row.get("seller_id") or "") != _FALLBACK_SELLER_ID]
    effective_results = non_fallback_results if non_fallback_results else safe_results
    success_count = sum(1 for row in effective_results if str(row.get("status") or "") == "success")
    failed_count = len(effective_results) - success_count
    return {
        "run_date": run_date,
        "total_sellers": len(effective_results),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": effective_results,
    }


def run_for_all_sellers(repo_root: str, run_date: str) -> Dict[str, Any]:
    sellers = [seller for seller in discover_sellers(repo_root) if seller != _FALLBACK_SELLER_ID]
    print(f"[batch] discovered {len(sellers)} sellers")
    if sellers:
        print(f"[batch] discovered sellers: {' '.join(sellers)}")
    else:
        print("[warn] no valid seller cabinets found")
    results: List[Dict[str, Any]] = []
    for current_seller in sellers:
        results.append(run_for_seller(repo_root, current_seller, run_date))
    summary = _batch_summary(run_date, results)
    print("[batch] completed")
    print(f"success: {summary['success_count']}")
    print(f"failed: {summary['failed_count']}")
    return summary


def run_daily_batch(repo_root: str, seller_id: Optional[str], run_date: str) -> Dict[str, Any]:
    if seller_id:
        print(f"[batch] explicit seller: {seller_id}")
        result = run_for_seller(repo_root, seller_id, run_date)
        summary = _batch_summary(run_date, [result])
        print("[batch] completed")
        print(f"success: {summary['success_count']}")
        print(f"failed: {summary['failed_count']}")
        return summary
    return run_for_all_sellers(repo_root, run_date)

def run_daily(repo_root: str, seller_id: Optional[str], run_date: str) -> List[Dict[str, Any]]:
    if seller_id:
        return [run_for_seller(repo_root, seller_id, run_date)]
    summary = run_for_all_sellers(repo_root, run_date)
    return [row for row in summary.get("results", []) if isinstance(row, dict)]

def run_audit(repo_root: str, seller_id: str, run_date: str, audit_input: str) -> List[Dict[str, Any]]:
    return [run_job(repo_root, seller_id, run_date, mode="audit", audit_input=audit_input)]
