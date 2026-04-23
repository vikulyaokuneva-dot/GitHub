from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .builders.report_payload_builder import build_report_payload_v2
from .renderers.email_renderer_v2 import write_email_files
from .renderers.pdf_renderer_v2 import write_report_pdf_v2


def _load_json_dict(path: str | Path, *, required: bool) -> dict[str, Any] | None:
    target = Path(path)
    if not target.is_file():
        if required:
            raise FileNotFoundError(f"JSON file not found: {target}")
        return None
    with open(target, "r", encoding="utf-8-sig") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {target}")
    return payload


def build_report_v2_from_files(
    *,
    snapshot_path: str | Path,
    debug_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    payload_path: str | Path | None = None,
    pdf_path: str | Path | None = None,
) -> dict[str, Any]:
    snapshot_target = Path(snapshot_path)
    snapshot = _load_json_dict(snapshot_target, required=True)
    debug = _load_json_dict(debug_path, required=False) if debug_path else None

    resolved_out_dir = Path(out_dir) if out_dir else snapshot_target.resolve().parent
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    payload_target = Path(payload_path) if payload_path else resolved_out_dir / "report_payload_v2.json"
    pdf_target = Path(pdf_path) if pdf_path else resolved_out_dir / "report_v2.pdf"

    payload = build_report_payload_v2(snapshot or {}, debug=debug)

    with open(payload_target, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    renderer_info = write_report_pdf_v2(pdf_target, payload)
    email_info = write_email_files(payload, resolved_out_dir)
    return {
        "payload": payload,
        "payload_path": str(payload_target),
        "pdf_path": str(pdf_target),
        "email_html_path": str(email_info["html_path"]),
        "email_txt_path": str(email_info["txt_path"]),
        "renderer_info": renderer_info,
        "email_info": email_info,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build report_payload_v2.json and report_v2.pdf from wb_api_core snapshot.")
    parser.add_argument("--snapshot", required=True, help="Path to snapshot.json")
    parser.add_argument("--debug", default="", help="Optional path to debug.json")
    parser.add_argument("--out-dir", default="", help="Output directory for payload and PDF")
    parser.add_argument("--payload-out", default="", help="Optional explicit payload output path")
    parser.add_argument("--pdf-out", default="", help="Optional explicit PDF output path")
    args = parser.parse_args()

    result = build_report_v2_from_files(
        snapshot_path=args.snapshot,
        debug_path=args.debug or None,
        out_dir=args.out_dir or None,
        payload_path=args.payload_out or None,
        pdf_path=args.pdf_out or None,
    )
    print(
        json.dumps(
            {
                "payload_path": result["payload_path"],
                "pdf_path": result["pdf_path"],
                "email_html_path": result["email_html_path"],
                "email_txt_path": result["email_txt_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
