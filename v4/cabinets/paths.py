"""Deterministic cabinet-aware path builders for v4 runtime."""

from __future__ import annotations

from pathlib import Path

from ..config.settings import get_default_output_root, get_temp_root


def _safe_segment(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in text)
    normalized = normalized.strip("._")
    return normalized or fallback


def _resolve_root(root: str | Path | None, *, default_root: str) -> Path:
    if root is None:
        return Path(default_root).resolve()
    return Path(str(root)).resolve()


def ensure_within_root(root: Path, target: Path) -> Path:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"Path escapes configured root: {target_resolved}") from exc
    return target_resolved


def _build_seller_cabinet_dir(
    *,
    root: Path,
    seller_id: str,
    cabinet_id: str | None,
    output_subdir: str | None = None,
) -> Path:
    seller_segment = _safe_segment(output_subdir or seller_id, fallback="seller")
    cabinet_segment = _safe_segment(cabinet_id, fallback="cabinet_default")
    target = root / seller_segment / cabinet_segment
    return ensure_within_root(root, target)


def _date_label(run_date: str | None) -> str:
    text = str(run_date or "").strip()
    return _safe_segment(text[:10], fallback="date_unspecified")


def get_seller_output_dir(
    *,
    seller_id: str,
    cabinet_id: str | None = None,
    output_root: str | Path | None = None,
    output_subdir: str | None = None,
) -> Path:
    root = _resolve_root(output_root, default_root=get_default_output_root())
    return _build_seller_cabinet_dir(
        root=root,
        seller_id=seller_id,
        cabinet_id=cabinet_id,
        output_subdir=output_subdir,
    )


def get_daily_output_dir(
    *,
    seller_id: str,
    cabinet_id: str | None = None,
    run_date: str | None = None,
    output_root: str | Path | None = None,
    output_subdir: str | None = None,
) -> Path:
    seller_dir = get_seller_output_dir(
        seller_id=seller_id,
        cabinet_id=cabinet_id,
        output_root=output_root,
        output_subdir=output_subdir,
    )
    target = seller_dir / "daily" / _date_label(run_date)
    return ensure_within_root(seller_dir, target)


def get_audit_output_dir(
    *,
    seller_id: str,
    cabinet_id: str | None = None,
    run_date: str | None = None,
    output_root: str | Path | None = None,
    output_subdir: str | None = None,
) -> Path:
    seller_dir = get_seller_output_dir(
        seller_id=seller_id,
        cabinet_id=cabinet_id,
        output_root=output_root,
        output_subdir=output_subdir,
    )
    target = seller_dir / "audit" / _date_label(run_date)
    return ensure_within_root(seller_dir, target)


def get_temp_dir(
    *,
    seller_id: str,
    cabinet_id: str | None = None,
    mode: str = "daily",
    temp_root: str | Path | None = None,
) -> Path:
    root = _resolve_root(temp_root, default_root=get_temp_root())
    seller_segment = _safe_segment(seller_id, fallback="seller")
    cabinet_segment = _safe_segment(cabinet_id, fallback="cabinet_default")
    mode_segment = _safe_segment(mode, fallback="mode")
    target = root / seller_segment / cabinet_segment / mode_segment
    return ensure_within_root(root, target)


def build_artifact_subpaths(output_dir: str | Path) -> dict[str, str]:
    root = Path(str(output_dir)).resolve()
    facts = ensure_within_root(root, root / "facts.json")
    decisions = ensure_within_root(root, root / "decisions.json")
    outputs_summary = ensure_within_root(root, root / "outputs_summary.json")
    email_preview = ensure_within_root(root, root / "email_preview.json")
    report_pdf = ensure_within_root(root, root / "report.pdf")
    return {
        "facts": str(facts),
        "decisions": str(decisions),
        "outputs_summary": str(outputs_summary),
        "email_preview": str(email_preview),
        "report_pdf": str(report_pdf),
    }


def path_label(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).name or text


__all__ = [
    "ensure_within_root",
    "get_seller_output_dir",
    "get_daily_output_dir",
    "get_audit_output_dir",
    "get_temp_dir",
    "build_artifact_subpaths",
    "path_label",
]

