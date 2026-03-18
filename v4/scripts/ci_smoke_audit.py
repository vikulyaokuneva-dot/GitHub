"""CI smoke helper for v4 audit mode.

Runs:
1) unittest discover
2) compileall
3) audit smoke run
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


MINIMAL_DAILY_CSV = """Обоснование для оплаты,Кол-во,Дата продажи,Дата заказа покупателем,Цена розничная,Код номенклатуры,Вайлдберриз реализовал Товар (Пр),К перечислению Продавцу за реализованный Товар
Продажа,1,2026-03-15,2026-03-15,100,12345,95,80
"""


def _run(cmd: list[str]) -> int:
    print("RUN:", " ".join(cmd))
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def _prepare_minimal_audit_input(base_dir: Path) -> Path:
    input_dir = base_dir / "audit_input"
    input_dir.mkdir(parents=True, exist_ok=True)
    (input_dir / "daily_report.csv").write_text(MINIMAL_DAILY_CSV, encoding="utf-8")
    return input_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 CI smoke helper for audit mode")
    parser.add_argument("--input-path", dest="input_path", required=False)
    parser.add_argument("--seller", default="seller_001")
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    args = parser.parse_args(argv)

    steps = [
        [sys.executable, "-m", "unittest", "discover", "v4/tests"],
        [sys.executable, "-m", "compileall", "v4"],
    ]

    if args.input_path:
        smoke_input = Path(str(args.input_path))
        temp_ctx = None
    else:
        temp_ctx = tempfile.TemporaryDirectory(prefix="v4_ci_audit_smoke_")
        smoke_input = _prepare_minimal_audit_input(Path(temp_ctx.name))

    try:
        smoke_cmd = [
            sys.executable,
            "v4/scripts/smoke_run_audit.py",
            "--input-path",
            str(smoke_input),
            "--seller",
            str(args.seller),
        ]
        if args.run_date:
            smoke_cmd.extend(["--date", str(args.run_date)])
        if args.output_dir:
            smoke_cmd.extend(["--output-dir", str(args.output_dir)])
        steps.append(smoke_cmd)

        for step in steps:
            code = _run(step)
            if code != 0:
                return code
        return 0
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
