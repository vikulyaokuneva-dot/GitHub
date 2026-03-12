import argparse

from research_engine.config import ResearchInputValidationError
from research_engine.pipeline import ResearchPipelineRunner


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AI Product Research Engine pipeline.")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Optional path to scenario JSON config. Defaults to config/scenarios/default_research_scenario.json.",
    )
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    runner = ResearchPipelineRunner(scenario_path=args.scenario)

    try:
        result = runner.run()
    except ResearchInputValidationError as exc:
        print(f"Input configuration error: {exc}")
        raise SystemExit(2) from None

    print(f"Research run completed at: {result.generated_at.isoformat()}")
    print(f"Total generated candidates: {result.total_candidates}")
    print(f"Filtered candidates: {result.filtered_candidates}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f" - {warning}")
    print("Artifacts:")
    for name, path in result.artifact_paths.items():
        print(f" - {name}: {path}")


if __name__ == "__main__":
    main()
