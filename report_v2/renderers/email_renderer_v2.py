from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _format_count(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return "unavailable"


def _format_money(value: Any) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return "unavailable"


def _format_text(value: Any) -> str:
    text = str(value or "").strip()
    return text or "unavailable"


def _html_table(title: str, rows: list[tuple[str, str]]) -> str:
    header = (
        "<tr>"
        "<th style=\"padding:10px 12px;border:1px solid #d1d5db;background:#f3f4f6;text-align:left;"
        "font-size:13px;color:#111827;\">Metric</th>"
        "<th style=\"padding:10px 12px;border:1px solid #d1d5db;background:#f3f4f6;text-align:left;"
        "font-size:13px;color:#111827;\">Value</th>"
        "</tr>"
    )
    body = "".join(
        (
            "<tr>"
            f"<td style=\"padding:9px 12px;border:1px solid #e5e7eb;font-size:13px;color:#111827;\">{escape(label)}</td>"
            f"<td style=\"padding:9px 12px;border:1px solid #e5e7eb;font-size:13px;color:#111827;\">{escape(value)}</td>"
            "</tr>"
        )
        for label, value in rows
    )
    return (
        f"<h2 style=\"margin:24px 0 10px 0;font-size:18px;line-height:24px;color:#111827;\">{escape(title)}</h2>"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" "
        "style=\"border-collapse:collapse;width:100%;background:#ffffff;\">"
        f"{header}{body}</table>"
    )


def _section_rows(section: dict[str, Any], fallback_rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    rows = section.get("rows")
    if not isinstance(rows, list) or not rows:
        return fallback_rows

    rendered: list[tuple[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        label = _format_text(item.get("label"))
        value = _format_text(item.get("value"))
        status = _format_text(item.get("status"))
        note = str(item.get("note") or "").strip()
        if note:
            value = f"{value} ({status}; {note})"
        else:
            value = f"{value} ({status})"
        rendered.append((label, value))

    return rendered or fallback_rows


def render_email_html(payload: dict) -> str:
    meta = _safe_dict(payload.get("meta"))
    commerce = _safe_dict(payload.get("cabinet_commerce"))
    commerce_section = _safe_dict(payload.get("commerce_section"))
    finance = _safe_dict(payload.get("finance_final"))
    live = _safe_dict(payload.get("live_operational"))
    warnings = payload.get("warnings", [])

    live_orders = _safe_dict(live.get("orders"))
    live_sales = _safe_dict(live.get("sales"))
    live_stocks = _safe_dict(live.get("stocks"))

    commerce_rows = _section_rows(
        commerce_section,
        [
            ("orders_count", _format_count(commerce.get("orders_count"))),
            ("orders_amount", _format_money(commerce.get("orders_amount"))),
            ("buyouts_count", _format_count(commerce.get("buyouts_count"))),
            ("buyouts_amount", _format_money(commerce.get("buyouts_amount"))),
        ],
    )
    finance_rows = [
        ("gross_revenue", _format_money(finance.get("gross_revenue"))),
        ("seller_payout", _format_money(finance.get("seller_payout"))),
        ("wb_commission", _format_money(finance.get("wb_commission"))),
        ("logistics", _format_money(finance.get("logistics"))),
        ("storage", _format_money(finance.get("storage"))),
        ("acquiring", _format_money(finance.get("acquiring"))),
    ]
    live_rows = [
        ("live orders", f"{_format_count(live_orders.get('count'))} / {_format_money(live_orders.get('amount'))}"),
        ("live sales", f"{_format_count(live_sales.get('count'))} / {_format_money(live_sales.get('amount'))}"),
        ("live stocks", _format_count(live_stocks.get("total_units"))),
    ]

    warnings_html = "<p style=\"margin:0;font-size:13px;line-height:20px;color:#111827;\">No warnings.</p>"
    if isinstance(warnings, list) and warnings:
        items = []
        for item in warnings:
            if isinstance(item, dict):
                block = _format_text(item.get("block"))
                message = _format_text(item.get("message"))
                items.append(
                    f"<li style=\"margin:0 0 6px 0;\">[{escape(block)}] {escape(message)}</li>"
                )
            else:
                items.append(f"<li style=\"margin:0 0 6px 0;\">{escape(_format_text(item))}</li>")
        warnings_html = (
            "<ul style=\"margin:0;padding-left:20px;font-size:13px;line-height:20px;color:#7c2d12;\">"
            + "".join(items)
            + "</ul>"
        )

    return (
        "<!DOCTYPE html>"
        "<html><body style=\"margin:0;padding:0;background:#f5f5f5;\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\" "
        "style=\"width:100%;background:#f5f5f5;border-collapse:collapse;\">"
        "<tr><td align=\"center\" style=\"padding:24px 12px;\">"
        "<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"720\" "
        "style=\"width:720px;max-width:720px;background:#ffffff;border-collapse:collapse;\">"
        "<tr><td style=\"padding:28px 28px 24px 28px;font-family:Arial,Helvetica,sans-serif;background:#ffffff;\">"
        "<h1 style=\"margin:0 0 14px 0;font-size:24px;line-height:30px;color:#111827;\">WB Core Report v2</h1>"
        f"<p style=\"margin:0 0 4px 0;font-size:14px;line-height:20px;color:#374151;\">seller_id: {escape(_format_text(meta.get('seller_id')))}</p>"
        f"<p style=\"margin:0 0 4px 0;font-size:14px;line-height:20px;color:#374151;\">report_date: {escape(_format_text(meta.get('report_date')))}</p>"
        f"<p style=\"margin:0;font-size:14px;line-height:20px;color:#374151;\">operational_date: {escape(_format_text(meta.get('operational_date')))}</p>"
        f"{_html_table('Commerce', commerce_rows)}"
        f"{_html_table('Finance', finance_rows)}"
        f"{_html_table('Live', live_rows)}"
        "<h2 style=\"margin:24px 0 10px 0;font-size:18px;line-height:24px;color:#111827;\">Warnings</h2>"
        f"{warnings_html}"
        "</td></tr></table></td></tr></table></body></html>"
    )


def render_email_text(payload: dict) -> str:
    meta = _safe_dict(payload.get("meta"))
    commerce = _safe_dict(payload.get("cabinet_commerce"))
    commerce_section = _safe_dict(payload.get("commerce_section"))
    finance = _safe_dict(payload.get("finance_final"))
    live = _safe_dict(payload.get("live_operational"))
    warnings = payload.get("warnings", [])

    live_orders = _safe_dict(live.get("orders"))
    live_sales = _safe_dict(live.get("sales"))
    live_stocks = _safe_dict(live.get("stocks"))

    commerce_rows = _section_rows(
        commerce_section,
        [
            ("Orders", _format_count(commerce.get("orders_count"))),
            ("Orders amount", _format_money(commerce.get("orders_amount"))),
            ("Buyouts", _format_count(commerce.get("buyouts_count"))),
            ("Buyouts amount", _format_money(commerce.get("buyouts_amount"))),
        ],
    )

    lines = [
        "WB Core Report v2",
        _format_text(meta.get("seller_id")),
        f"Date: {_format_text(meta.get('report_date'))}",
        f"Operational date: {_format_text(meta.get('operational_date'))}",
        "",
        "Commerce:",
        *[f"{label}: {value}" for label, value in commerce_rows],
        "",
        "Finance:",
        f"Gross revenue: {_format_money(finance.get('gross_revenue'))}",
        f"Seller payout: {_format_money(finance.get('seller_payout'))}",
        f"WB commission: {_format_money(finance.get('wb_commission'))}",
        f"Logistics: {_format_money(finance.get('logistics'))}",
        f"Storage: {_format_money(finance.get('storage'))}",
        f"Acquiring: {_format_money(finance.get('acquiring'))}",
        "",
        "Live:",
        f"Live orders: {_format_count(live_orders.get('count'))} / {_format_money(live_orders.get('amount'))}",
        f"Live sales: {_format_count(live_sales.get('count'))} / {_format_money(live_sales.get('amount'))}",
        f"Live stocks: {_format_count(live_stocks.get('total_units'))}",
        "",
        "Warnings:",
    ]
    if isinstance(warnings, list) and warnings:
        for item in warnings:
            if isinstance(item, dict):
                lines.append(f"- [{_format_text(item.get('block'))}] {_format_text(item.get('message'))}")
            else:
                lines.append(f"- {_format_text(item)}")
    else:
        lines.append("- No warnings.")
    return "\n".join(lines).strip() + "\n"


def write_email_files(payload: dict, out_dir: str | Path) -> dict[str, str]:
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    html_text = render_email_html(payload)
    text_body = render_email_text(payload)
    html_path = target_dir / "email_v2.html"
    txt_path = target_dir / "email_v2.txt"

    html_path.write_text(html_text, encoding="utf-8")
    txt_path.write_text(text_body, encoding="utf-8")

    return {
        "html_path": str(html_path),
        "txt_path": str(txt_path),
    }
