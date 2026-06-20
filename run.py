"""Entry point for audit modes. Use python -m v3.entry daily for daily pipeline."""

from __future__ import annotations

import argparse


def main() -> int:
    """Parse CLI args and run audit pipeline."""
    parser = argparse.ArgumentParser(description="Run audit pipeline.")
    parser.add_argument("--seller", default="seller_001", help="Seller id")
    parser.add_argument("--mode", default="audit", help="Pipeline mode: audit | audit_ozon")
    parser.add_argument("--source", default="wb", help="Audit source: wb | ozon")
    parser.add_argument("--audit-input-dir", default="", help="Audit input dir override")
    parser.add_argument("--audit-out-dir", default="", help="Audit output dir override")
    parser.add_argument("--period", default="", help="Optional period label for audit mode")
    parser.add_argument("--input", default="", help="Input file path for --mode audit_ozon")
    parser.add_argument("--output-dir", default="out", help="Output dir for --mode audit_ozon")
    args = parser.parse_args()

    if str(args.mode).strip().lower() == "audit_ozon":
        if not str(args.input or "").strip():
            print("Error: --input is required for --mode audit_ozon")
            return 1
        from audit.audit_ozon.runner import run_ozon_audit

        result = run_ozon_audit(
            input_path=str(args.input),
            output_dir=str(args.output_dir or "out"),
        )
        if not bool(result.get("ok")):
            print(f"Ozon audit completed with warnings: {result.get('error')}")
        print(f"Ozon markdown: {result.get('md_path')}")
        print(f"Ozon pdf: {result.get('pdf_path')}")
        return 0

    if str(args.mode).strip().lower() == "audit":
        from audit.run_audit import run_audit_mode

        run_audit_mode(
            seller=args.seller,
            input_dir=args.audit_input_dir,
            out_dir=args.audit_out_dir,
            source=args.source,
            period=args.period,
            send_email=False,
        )
        return 0

    print(f"Unknown mode: {args.mode}. Use 'python -m v3.entry daily' for daily pipeline.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
