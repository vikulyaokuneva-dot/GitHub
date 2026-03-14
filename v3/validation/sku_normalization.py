from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping


_MISSING_LITERALS = {"", "none", "null", "nan", "n/a", "na", "-", "unknown"}
_ZERO_LITERALS = {"0", "0.0", "00", "000"}
_VALID_TOKEN_RE = re.compile(r"^[\w.\-]+$", flags=re.UNICODE)

_PRIMARY_FIELDS = {
    "nm_id",
    "nmid",
    "nmid_wb",
    "nm_id_wb",
    "article",
    "article_wb",
    "wb_article",
    "wb_nm_id",
    "code_nomenclature",
    "nomenclature_code",
    "kod_nomenklatury",
}
_FALLBACK_FIELDS = {
    "supplierarticle",
    "supplier_article",
    "vendorcode",
    "vendor_code",
    "seller_sku",
    "supplier_sku",
    "barcode",
    "offer_id",
    "product_id",
    "sku",
}


def _field_key(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_sku_with_reason(value: Any) -> tuple[str | None, str]:
    if value is None:
        return None, "missing_field"

    text = str(value).strip()
    if not text:
        return None, "missing_field"

    lowered = text.lower()
    if lowered in _MISSING_LITERALS:
        return None, "missing_field"
    if lowered in _ZERO_LITERALS:
        return None, "missing_field"

    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None, "missing_field"

    if re.fullmatch(r"\d+(\.0+)?", compact):
        digits = compact.split(".", 1)[0]
        if digits in _ZERO_LITERALS:
            return None, "missing_field"
        return digits, "ok"

    if not _VALID_TOKEN_RE.fullmatch(compact):
        return None, "parser_error"

    return compact, "ok"


def normalize_sku(value: Any) -> str | None:
    normalized, _ = normalize_sku_with_reason(value)
    return normalized


def _first_present(row: Mapping[str, Any], keys: Iterable[str]) -> tuple[Any, str]:
    for key in keys:
        if key in row:
            return row.get(key), key
    lowered_map: Dict[str, str] = {str(k).strip().lower(): str(k) for k in row.keys()}
    for key in keys:
        real_key = lowered_map.get(key.lower())
        if real_key is not None:
            return row.get(real_key), real_key
    return None, ""


def _field_kind(field: str) -> str:
    token = _field_key(field)
    if token in _PRIMARY_FIELDS:
        return "primary"
    if token in _FALLBACK_FIELDS:
        return "fallback"
    return "unknown"


def resolve_row_sku(row: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(row, Mapping):
        return {
            "sku": None,
            "reason": "parser_error",
            "source_field": "",
            "source_kind": "unknown",
            "fallback_used": False,
        }

    source_hint = str(row.get("_sku_source_field") or "").strip()

    primary_candidates = (
        "nm_id",
        "nmId",
        "nmid",
        "nmID",
        "article",
        "article_wb",
        "wb_article",
        "code_nomenclature",
        "nomenclature_code",
        "kod_nomenklatury",
    )
    fallback_candidates = (
        "sku",
        "seller_sku",
        "supplier_sku",
        "supplierArticle",
        "vendorCode",
        "barcode",
        "offer_id",
        "product_id",
    )

    checked_any = False
    last_reason = "missing_field"

    def _try_candidates(keys: Iterable[str], *, preferred_field: str = "") -> Dict[str, Any] | None:
        nonlocal checked_any, last_reason
        for key in keys:
            raw_value, real_key = _first_present(row, (key,))
            field_name = preferred_field or real_key or key
            parsed, reason = normalize_sku_with_reason(raw_value)
            if raw_value is not None and str(raw_value).strip():
                checked_any = True
            if parsed is None:
                last_reason = reason
                continue
            kind = _field_kind(field_name)
            return {
                "sku": parsed,
                "reason": "ok",
                "source_field": field_name,
                "source_kind": kind,
                "fallback_used": kind == "fallback",
            }
        return None

    primary = _try_candidates(primary_candidates)
    if primary is not None:
        return primary

    if source_hint:
        hinted, reason = normalize_sku_with_reason(row.get("sku"))
        if hinted is not None:
            kind = _field_kind(source_hint)
            return {
                "sku": hinted,
                "reason": "ok",
                "source_field": source_hint,
                "source_kind": kind,
                "fallback_used": kind == "fallback",
            }
        last_reason = reason

    fallback = _try_candidates(fallback_candidates)
    if fallback is not None:
        return fallback

    return {
        "sku": None,
        "reason": "parser_error" if checked_any and last_reason != "missing_field" else "missing_field",
        "source_field": source_hint,
        "source_kind": _field_kind(source_hint),
        "fallback_used": _field_kind(source_hint) == "fallback",
    }

