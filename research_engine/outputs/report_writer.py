from pathlib import Path

from research_engine.domain.models import ResearchResult


class ReportWriter:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def write_text_report(self, result: ResearchResult) -> str:
        path = self.artifacts_dir / "research_report.txt"
        lines = [
            f"generated_at: {result.generated_at.isoformat()}",
            f"candidates_count: {result.candidates_count}",
            f"shortlisted_count: {result.shortlisted_count}",
            "top_shortlist:",
        ]
        for scored in result.shortlist:
            lines.append(f"- {scored.candidate.niche_id} | {scored.candidate.title} | score={scored.final_score}")
        with path.open("w", encoding="utf-8") as report_file:
            report_file.write("\n".join(lines))
        return str(path)
