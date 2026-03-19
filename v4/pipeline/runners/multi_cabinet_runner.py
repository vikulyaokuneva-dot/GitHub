"""Thin multi-cabinet orchestration over existing single-seller runners."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...cabinets.paths import get_audit_output_dir, get_daily_output_dir, path_label
from ...cabinets.registry import get_cabinet_by_seller, resolve_single_or_multiple_sellers
from ...config.features import resolve_feature_flags
from ...config.sellers import SellerConfig
from .audit_runner import run_audit_pipeline
from .daily_runner import run_daily_pipeline


def _ensure_dir(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _normalize_seller_ids(seller_ids: list[str] | str | None) -> list[str] | None:
    if seller_ids is None:
        return None
    if isinstance(seller_ids, str):
        values = [part.strip() for part in seller_ids.split(",")]
        return [value for value in values if value]
    result: list[str] = []
    for value in seller_ids:
        text = str(value or "").strip()
        if text:
            result.append(text)
    return result


def _status_from_result(result: dict[str, Any]) -> str:
    summary = result.get("diagnostics", {}).get("summary", {})
    partial_flag = bool(summary.get("partial_flag"))
    return "partial" if partial_flag else "succeeded"


def _run_context_for_seller(
    *,
    seller: SellerConfig,
    run_date: str | None,
    timezone: str,
    dry_run: bool,
    mode_text: str,
    output_dir: str,
    run_feature_overrides: dict[str, bool] | None = None,
    input_path: str | None = None,
) -> dict[str, Any]:
    mode_for_flags = "audit_file_mode" if mode_text == "audit" else "daily_api_mode"
    feature_flags = resolve_feature_flags(
        run_context={"mode": mode_for_flags},
        seller_config=seller,
        run_overrides=run_feature_overrides or {},
    )
    path_labels: dict[str, str] = {"output_dir_label": str(path_label(output_dir) or "")}
    if input_path:
        path_labels["input_path_label"] = str(path_label(input_path) or "")

    return {
        "seller_id": seller.seller_id,
        "run_date": run_date,
        "cabinet_id": seller.cabinet_id,
        "cabinet_name": seller.cabinet_name,
        "timezone": timezone,
        "dry_run": bool(dry_run),
        "feature_flags": feature_flags,
        "path_labels": path_labels,
        "input_path_label": path_labels.get("input_path_label"),
        "output_dir": output_dir,
    }


def run_daily_for_sellers(
    seller_ids: list[str] | str | None = None,
    run_date: str | None = None,
    output_root: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
    feature_overrides: dict[str, bool] | None = None,
) -> dict[str, Any]:
    requested_ids = _normalize_seller_ids(seller_ids)
    if requested_ids:
        sellers: list[SellerConfig] = []
        missing_ids: list[str] = []
        for seller_id in requested_ids:
            config = get_cabinet_by_seller(seller_id)
            if config is None or not config.is_enabled:
                missing_ids.append(seller_id)
                continue
            sellers.append(config)
    else:
        sellers = resolve_single_or_multiple_sellers(seller_ids=None)
        missing_ids = []

    results: dict[str, Any] = {}
    output_dirs: dict[str, str] = {}
    succeeded_sellers: list[str] = []
    partial_sellers: list[str] = []
    failed_sellers: list[str] = []
    warnings: list[str] = []

    for missing in missing_ids:
        failed_sellers.append(missing)
        results[missing] = {"error": f"Unknown or disabled seller_id: {missing}"}
        warnings.append(f"{missing}: unknown or disabled seller")

    for seller in sellers:
        output_dir = _ensure_dir(
            get_daily_output_dir(
                seller_id=seller.seller_id,
                cabinet_id=seller.cabinet_id,
                run_date=run_date,
                output_root=output_root,
                output_subdir=seller.output_subdir,
            )
        )
        output_dirs[seller.seller_id] = output_dir

        context_payload = _run_context_for_seller(
            seller=seller,
            run_date=run_date,
            timezone=timezone,
            dry_run=dry_run,
            mode_text="daily",
            output_dir=output_dir,
            run_feature_overrides=feature_overrides,
        )
        try:
            result = run_daily_pipeline(run_context=context_payload, output_dir=output_dir)
            results[seller.seller_id] = result
            status = _status_from_result(result)
            if status == "partial":
                partial_sellers.append(seller.seller_id)
            else:
                succeeded_sellers.append(seller.seller_id)
            warnings.extend([str(w) for w in result.get("warnings", [])])
        except Exception as exc:
            failed_sellers.append(seller.seller_id)
            results[seller.seller_id] = {"error": str(exc)}
            warnings.append(f"{seller.seller_id}: {exc}")

    return {
        "mode": "daily",
        "requested_seller_ids": requested_ids or [seller.seller_id for seller in sellers],
        "succeeded_sellers": succeeded_sellers,
        "partial_sellers": partial_sellers,
        "failed_sellers": failed_sellers,
        "output_dirs": output_dirs,
        "warnings": warnings,
        "results": results,
    }


def run_audit_for_sellers(
    input_map: dict[str, str],
    run_date: str | None = None,
    output_root: str | None = None,
    timezone: str = "Europe/Moscow",
    dry_run: bool = False,
    seller_ids: list[str] | str | None = None,
    feature_overrides: dict[str, bool] | None = None,
) -> dict[str, Any]:
    requested_ids = _normalize_seller_ids(seller_ids)
    if requested_ids:
        input_payload = {sid: input_map[sid] for sid in requested_ids if sid in input_map}
    else:
        input_payload = dict(input_map)

    results: dict[str, Any] = {}
    output_dirs: dict[str, str] = {}
    succeeded_sellers: list[str] = []
    partial_sellers: list[str] = []
    failed_sellers: list[str] = []
    warnings: list[str] = []

    for seller_id in sorted(input_payload.keys()):
        input_path = str(input_payload[seller_id])
        seller = get_cabinet_by_seller(seller_id)
        if seller is None:
            failed_sellers.append(seller_id)
            results[seller_id] = {"error": f"Unknown seller_id: {seller_id}"}
            warnings.append(f"{seller_id}: unknown seller")
            continue
        if not seller.is_enabled:
            failed_sellers.append(seller_id)
            results[seller_id] = {"error": f"Seller is disabled: {seller_id}"}
            warnings.append(f"{seller_id}: disabled seller")
            continue

        output_dir = _ensure_dir(
            get_audit_output_dir(
                seller_id=seller.seller_id,
                cabinet_id=seller.cabinet_id,
                run_date=run_date,
                output_root=output_root,
                output_subdir=seller.output_subdir,
            )
        )
        output_dirs[seller.seller_id] = output_dir

        context_payload = _run_context_for_seller(
            seller=seller,
            run_date=run_date,
            timezone=timezone,
            dry_run=dry_run,
            mode_text="audit",
            output_dir=output_dir,
            run_feature_overrides=feature_overrides,
            input_path=input_path,
        )
        try:
            result = run_audit_pipeline(
                input_path=input_path,
                run_context=context_payload,
                output_dir=output_dir,
            )
            results[seller.seller_id] = result
            status = _status_from_result(result)
            if status == "partial":
                partial_sellers.append(seller.seller_id)
            else:
                succeeded_sellers.append(seller.seller_id)
            warnings.extend([str(w) for w in result.get("warnings", [])])
        except Exception as exc:
            failed_sellers.append(seller.seller_id)
            results[seller.seller_id] = {"error": str(exc)}
            warnings.append(f"{seller.seller_id}: {exc}")

    return {
        "mode": "audit",
        "requested_seller_ids": sorted(input_payload.keys()),
        "succeeded_sellers": succeeded_sellers,
        "partial_sellers": partial_sellers,
        "failed_sellers": failed_sellers,
        "output_dirs": output_dirs,
        "warnings": warnings,
        "results": results,
    }


__all__ = ["run_daily_for_sellers", "run_audit_for_sellers"]
