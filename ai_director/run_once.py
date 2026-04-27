from __future__ import annotations

import argparse
import sys

try:
    from .create_task import TaskFileError, create_task
    from . import orchestrator, show_last_run
except ImportError:
    from create_task import TaskFileError, create_task
    import orchestrator
    import show_last_run


def main(argv: list[str] | None = None) -> int:
    _configure_output()

    parser = argparse.ArgumentParser(description="Create and run one planner-only AI Director task.")
    parser.add_argument("--title", required=True, help="Task title.")
    parser.add_argument("--prompt", required=True, help="Task prompt/description.")
    parser.add_argument("--full", action="store_true", help="Print the full LLM response after the run.")
    args = parser.parse_args(argv)

    try:
        task = create_task(title=args.title, prompt=args.prompt, mode="planner_only")
    except TaskFileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    task_id = str(task["id"])
    print(f"Created planner_only task: {task_id}")
    print("")

    orchestrator_code = orchestrator.main(task_id=task_id)
    print("")

    show_args = ["--full"] if args.full else []
    show_code = show_last_run.main(show_args)
    return orchestrator_code or show_code


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
