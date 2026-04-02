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
    args = parser.parse_args()

    seller_root = Path("runtime") / "cabinets" / args.seller
    if not seller_root.exists() or not seller_root.is_dir():
        print(f"Error: seller '{args.seller}' not found at runtime/cabinets/{args.seller}")
        return 1

    run_pipeline(seller=args.seller, mode=args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
