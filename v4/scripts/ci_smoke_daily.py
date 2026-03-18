"""CI smoke helper for v4 daily-core.

Runs:
1) unittest discover
2) compileall
3) daily smoke run
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def _run(cmd: list[str]) -> int:
    print("RUN:", " ".join(cmd))
    completed = subprocess.run(cmd, check=False)
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v4 CI smoke helper")
    parser.add_argument("--seller", default="seller_001")
    parser.add_argument("--date", dest="run_date", required=False)
    parser.add_argument("--output-dir", dest="output_dir", required=False)
    args = parser.parse_args(argv)

    steps = [
        [sys.executable, "-m", "unittest", "discover", "v4/tests"],
        [sys.executable, "-m", "compileall", "v4"],
    ]
    smoke_cmd = [sys.executable, "v4/scripts/smoke_run_daily.py", "--seller", str(args.seller)]
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


if __name__ == "__main__":
    raise SystemExit(main())

