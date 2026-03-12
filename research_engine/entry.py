from research_engine.pipeline import ResearchPipelineRunner


def main() -> None:
    runner = ResearchPipelineRunner()
    result = runner.run()

    print(f"Research run completed at: {result.generated_at.isoformat()}")
    print(f"Candidates analyzed: {result.candidates_count}")
    print(f"Shortlisted: {result.shortlisted_count}")
    print("Top niches:")
    for scored in result.shortlist:
        candidate = scored.candidate
        print(f" - {candidate.niche_id}: {candidate.title} (score={scored.final_score})")
    print("Artifacts:")
    for name, path in result.artifact_paths.items():
        print(f" - {name}: {path}")


if __name__ == "__main__":
    main()
