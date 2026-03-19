"""Shadow-mode orchestration for controlled v4 production adoption."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..cabinets.paths import path_label
from ..pipeline.runners.daily_runner import run_daily_pipeline
from .comparator import compare_results
from .contracts import ShadowRunDiagnostics


def _to_serializable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_serializable(asdict(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _to_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_serializable(v) for v in value]
    return value


def _run_legacy_daily(
    *,
    seller_id: str,
    run_date: str,
    output_dir: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    try:
        from v3.entry import run_daily_batch  # type: ignore
    except Exception as exc:
        warnings.append(f"legacy pipeline is unavailable: {exc}")
        return (None, warnings)

    repo_root = str(Path(__file__).resolve().parents[2])
    try:
        result = run_daily_batch(repo_root=repo_root, seller_id=seller_id, run_date=run_date)
    except Exception as exc:
        warnings.append(f"legacy pipeline failed: {exc}")
        return (None, warnings)

    output_dir.mkdir(parents=True, exist_ok=True)
    legacy_result_path = output_dir / "legacy_result.json"
    legacy_result_path.write_text(
        json.dumps(_to_serializable(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return (_to_serializable(result), warnings)


def run_shadow_daily(
    seller_id: str,
    run_date: str,
    output_root: str,
    run_v4: bool = True,
    run_legacy: bool = False,
) -> dict:
    root = Path(str(output_root)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    v4_dir = root / "v4"
    legacy_dir = root / "legacy"

    warnings: list[str] = []
    v4_result: dict[str, Any] | None = None
    legacy_result: dict[str, Any] | None = None

    if run_v4:
        v4_dir.mkdir(parents=True, exist_ok=True)
        v4_result = run_daily_pipeline(
            run_context={
                "seller_id": str(seller_id).strip(),
                "run_date": str(run_date).strip(),
            },
            output_dir=str(v4_dir),
        )
    else:
        warnings.append("v4 run is disabled by run_v4=False")

    if run_legacy:
        legacy_result, legacy_warnings = _run_legacy_daily(
            seller_id=str(seller_id).strip(),
            run_date=str(run_date).strip(),
            output_dir=legacy_dir,
        )
        warnings.extend(legacy_warnings)

    comparison = compare_results(v4_result, legacy_result)
    comparison_path = root / "comparison.json"
    comparison_path.write_text(
        json.dumps(_to_serializable(comparison), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    diagnostics = ShadowRunDiagnostics(
        run_v4=run_v4,
        run_legacy=run_legacy,
        output_root=str(root),
        output_labels={
            "output_root_label": str(path_label(root) or ""),
            "v4_output_label": str(path_label(v4_dir) or ""),
            "legacy_output_label": str(path_label(legacy_dir) or ""),
            "comparison_label": str(path_label(comparison_path) or ""),
        },
        warnings=warnings,
    ).to_dict()

    return {
        "v4_result": v4_result,
        "legacy_result": legacy_result,
        "comparison": comparison,
        "diagnostics": diagnostics,
    }


__all__ = ["run_shadow_daily"]

