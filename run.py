"""Project entry point for the new modular pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.runner import run_pipeline


def main() -> int:
    """Parse CLI args and run pipeline."""
    parser = argparse.ArgumentParser(description="Run modular runtime pipeline.")
    parser.add_argument("--seller", default="seller_001", help="Seller id in runtime/cabinets/")
    parser.add_argument("--mode", default="daily", help="Pipeline mode (default: daily)")
    parser.add_argument("--audit-input-dir", default="audit/input", help="Audit input dir (for --mode audit)")
    parser.add_argument("--audit-out-dir", default="audit/output", help="Audit output dir (for --mode audit)")
    parser.add_argument("--period", default="", help="Optional period label for audit mode")
    args = parser.parse_args()

    if str(args.mode).strip().lower() == "audit":
        from audit.run_audit import run_audit_mode

        run_audit_mode(
            input_dir=args.audit_input_dir,
            out_dir=args.audit_out_dir,
            period=args.period,
            send_email=False,
        )
        return 0

    seller_root = Path("runtime") / "cabinets" / args.seller
    if not seller_root.exists() or not seller_root.is_dir():
        print(f"Error: seller '{args.seller}' not found at runtime/cabinets/{args.seller}")
        return 1

    run_pipeline(seller=args.seller, mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
