import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from research_engine.domain.contracts import ResearchContext


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


class ArtifactWriter:
    def __init__(self, artifacts_dir: Path):
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, filename: str, payload: Any) -> Path:
        path = self.artifacts_dir / filename
        with path.open("w", encoding="utf-8") as output_file:
            json.dump(_to_jsonable(payload), output_file, ensure_ascii=False, indent=2)
        return path

    def write_research_artifacts(self, context: ResearchContext) -> dict[str, str]:
        if context.job is None or context.input_data is None:
            raise ValueError("Cannot write artifacts before input/job stage has completed.")

        summary_payload = context.result if context.result is not None else {
            "job_id": context.job.job_id,
            "warnings": context.warnings,
        }
        candidates_payload = context.candidate_pool if context.candidate_pool is not None else {
            "generated_at": None,
            "scenario_name": context.input_data.scenario_name,
            "total_candidates": 0,
            "filtered_candidates": 0,
            "candidates": [],
            "warnings": context.warnings,
        }

        outputs = {
            "research_job": self.write_json("research_job.json", context.job),
            "research_input": self.write_json("research_input.json", context.input_data),
            "research_candidates": self.write_json("research_candidates.json", candidates_payload),
            "research_summary": self.write_json("research_summary.json", summary_payload),
        }
        return {key: str(path) for key, path in outputs.items()}
